"""Frozen policy cohorts; each child retains the watchdog and explicit funding."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from .config import load_config, owned_path
from .integrity import inspect_integrity
from .local_policy_evidence import inspect_local_policy
from .match_lifecycle import replay_layout_valid
from .matches import artifact_bytes, isolated_environment, locate_run
from .tactical_choices import PROFILE, profile_labels
from . import paid_cohort

MODES = ('random-tactical', 'heuristic-tactical')
ALL_MODES = (*MODES, 'jev')
CHILD_GRACE = 30


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity(root):
    config = root/'agent/local.toml'
    return {'modules': {p.name: file_hash(p) for p in sorted((root/'agent/src/melee_agent').glob('*.py'))},
        'local_config': file_hash(config) if config.exists() else None}


def bounded(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def validate_plan(policies, repeats, match_seconds, duration, profile, bot_ports=None):
    profile_labels(profile)
    if (not policies or len(set(policies)) != len(policies) or any(p not in ALL_MODES for p in policies) or
            not bounded(repeats, 1, 10) or not bounded(match_seconds, 30, 600) or
            not bounded(duration, match_seconds+CHILD_GRACE, 43200)):
        raise ValueError('Invalid bounded policy batch')
    if bot_ports is None:
        return [{'round': number, 'policy': policy} for number in range(1, repeats+1) for policy in policies]
    if (not isinstance(bot_ports,(list,tuple)) or not bot_ports or len(bot_ports)>2 or
            any(type(port) is not int or port not in (1,2) for port in bot_ports) or
            len(set(bot_ports)) != len(bot_ports)):
        raise ValueError('Invalid batch player ports')
    return [{'round':number,'policy':policy,'bot_port':port}
        for number in range(1,repeats+1) for port in bot_ports for policy in policies]


def manifest_plan(manifest):
    version = manifest['schema_version']
    if type(version) is not int or version not in (1,2):
        raise ValueError('Unknown batch schema')
    if (version == 1 and 'bot_ports' in manifest or
            version == 2 and manifest.get('bot_ports') is None):
        raise ValueError('Batch schema and player ports disagree')
    return validate_plan(manifest['policies'],manifest['matches_per_policy'],
        manifest['match_seconds'],manifest['duration_seconds'],manifest['candidate_profile'],
        manifest.get('bot_ports'))


def child_port(manifest, slot):
    return manifest['schedule'][slot].get('bot_port',1)


def write_new(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, sort_keys=True, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def append_event(folder, event):
    with (folder/'events.jsonl').open('a') as handle:
        handle.write(json.dumps(event, sort_keys=True, allow_nan=False)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def batch_lock(folder, name='batch.lock'):
    fd = os.open(folder/name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Batch already has an owner') from None
        yield


def read_json(path):
    if path.stat().st_size > 4*1024*1024:
        raise ValueError('Batch metadata exceeds bound')
    return json.loads(path.read_text())


def locate_batch(root, batch_id):
    if not isinstance(batch_id, str) or not re.fullmatch(r'batch-[0-9a-f]{32}', batch_id):
        raise ValueError('Invalid batch identity')
    return owned_path(root, 'build/jev/batches/'+batch_id)


def artifact_path(run, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not (run/path).resolve().is_relative_to(run):
        raise ValueError('Artifact path escapes owned run')
    return run/path


def load_batch(root, folder):
    manifest = read_json(folder/'manifest.json')
    provider = manifest.get('provider')
    expected = manifest_plan(manifest)
    if (manifest['batch_id'] != folder.name or
            manifest['schedule'] != expected or manifest['provider_enabled'] != ('jev' in manifest['policies']) or
            bool(provider) != manifest['provider_enabled'] or
            (provider is not None and (provider['profile'] != manifest['candidate_profile'] or
                provider['config_sha256'] != paid_cohort.policy_config_hash(provider['profile']))) or
            manifest['source_identity'] != source_identity(root)):
        raise ValueError('Batch identity or source changed; start a separate cohort')
    events_path = folder/'events.jsonl'
    if events_path.exists() and events_path.stat().st_size > 65536:
        raise ValueError('Batch journal exceeds bound')
    events = [] if not events_path.exists() else [json.loads(line) for line in events_path.read_text().splitlines()]
    if not events or events[0] != {'kind':'created','manifest_sha256':file_hash(folder/'manifest.json')}:
        raise ValueError('Batch manifest changed or creation journal missing')
    results, pending = [], None
    ledger = provider['initial_ledger'] if provider else None
    for event in events[1:]:
        slot = len(results)
        if (event.get('kind') == 'launch' and pending is None and event.get('slot') == slot and slot < len(expected)
                and all(row['passed'] for row in results)):
            if event.get('ledger_before') != ledger:
                raise ValueError('Launch spending checkpoint changed')
            pending = event
        elif event.get('kind') == 'audited' and pending is not None and event.get('slot') == slot:
            audit_path = folder/f'audit-{slot:02}.json'
            if file_hash(audit_path) != event['audit_sha256']:
                raise ValueError('Batch audit changed')
            audit = read_json(audit_path)
            run = locate_run(root, audit['run_id'])
            if (audit['slot'] != slot or audit['policy'] != expected[slot]['policy'] or
                    (manifest['schema_version']==2 and any('bot_port' not in value for value in (audit,audit['summary']))) or
                    any(type(value) is not int or value != child_port(manifest,slot) for value in
                        (audit.get('bot_port',1),audit['summary'].get('bot_port',1))) or
                    audit['run_id'] in {row['run_id'] for row in results} or
                    not {'launch.json','summary.json','frames.jsonl'}.issubset(audit['artifact_sha256']) or
                    any(file_hash(artifact_path(run,name)) != digest for name,digest in audit['artifact_sha256'].items())):
                raise ValueError('Prior match artifacts changed')
            if provider:
                if audit['spending']['before'] != ledger:
                    raise ValueError('Audited spending chain changed')
                ledger = audit['spending']['after']
                paid_cohort.verify_checkpoint(root,provider,ledger,exact=False)
            if audit['policy']=='jev':
                paid_cohort.verify_replay_artifacts(root,audit['control_replay'])
            results.append(audit)
            pending = None
        else:
            raise ValueError('Ambiguous batch journal')
    if provider:
        paid_cohort.verify_checkpoint(root,provider,ledger,exact=pending is None)
    return manifest, results, pending


def audit_child(root, folder, manifest, slot, *, ledger_before=None):
    if source_identity(root) != manifest['source_identity']:
        raise ValueError('Batch source changed during child run')
    log = folder/f'match-{slot:02}.log'
    if not log.exists() or log.stat().st_size > 4*1024*1024:
        raise ValueError('Missing or oversized child log; automatic retry forbidden')
    starts = []
    for line in log.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('event') == 'started':
            starts.append(event['run_id'])
    if len(starts) != 1:
        raise ValueError('Ambiguous child identity; automatic retry forbidden')
    run = locate_run(root, starts[0])
    launch, summary = read_json(run/'launch.json'), read_json(run/'summary.json')
    policy = manifest['schedule'][slot]['policy']
    port = child_port(manifest,slot)
    if (launch['run_id'] != run.name or summary['run_id'] != run.name or
            (manifest['schema_version']==2 and any('bot_port' not in value for value in (launch,summary))) or
            type(launch.get('bot_port',1)) is not int or type(summary.get('bot_port',1)) is not int or
            launch.get('bot_port',1) != port or summary.get('bot_port',1) != port or
            launch['policy'] != policy or summary['policy'] != policy or
            launch.get('candidate_profile', PROFILE) != manifest['candidate_profile'] or
            launch['source_sha256'] != manifest['source_identity']['modules'] or
            launch['duration_seconds'] != manifest['match_seconds'] or launch['episodes'] != 1 or
            launch['provider_enabled'] != (policy=='jev') or
            (policy!='jev' and launch.get('budget_directory') is not None) or
            launch['runtime_sha256'] != manifest['runtime_sha256']):
        raise ValueError('Child differs from frozen batch')
    spending = (paid_cohort.audit_spending(root,manifest['provider'],ledger_before,launch,summary,policy)
        if manifest.get('provider') else None)
    integrity = inspect_integrity(run)
    control = (paid_cohort.audit_replay(root,folder,slot,run,summary) if policy=='jev' else inspect_local_policy(run))
    provider_ok = (summary['provider_contacted'] and spending['http_calls']>0 and spending['validated']>0
        and spending['provider_shutdown']) if policy=='jev' else not summary['provider_contacted']
    rules = replay_layout_valid(summary['episodes'], summary['replays'], complete=True, expected_matches=1,bot_port=port)
    passed = (summary['status'] == 'complete' and summary.get('completed_matches') == 1 and
        integrity['status'] == control['status'] == 'pass' and rules and provider_ok and
        all(summary[k] for k in ('neutralized','worker_stopped','emulator_stopped')) and summary['state_receiver']['stopped'])
    files = ['launch.json', 'summary.json', 'frames.jsonl', *['replays/'+r['file'] for r in summary['replays']]]
    return {'schema_version':1, 'slot':slot, 'run_id':run.name, 'policy':policy,'bot_port':port,
        'passed':bool(passed), 'summary':summary, 'integrity':integrity, 'control_replay':control, 'spending':spending,
        'rules_and_result':rules, 'artifact_bytes':artifact_bytes(run)+control.get('incident_bytes',0),
        'artifact_sha256':{name:file_hash(artifact_path(run,name)) for name in files}}


def record_audit(root, folder, manifest, slot, *, ledger_before=None):
    audit = audit_child(root, folder, manifest, slot,ledger_before=ledger_before)
    if audit['run_id'] in {read_json(folder/f'audit-{n:02}.json')['run_id'] for n in range(slot)}:
        raise ValueError('Child identity reused across slots')
    path = folder/f'audit-{slot:02}.json'
    # A crash after the immutable audit write can be adopted only if it still
    # matches a fresh inspection of the same recorded child.
    if path.exists():
        if read_json(path) != audit:
            raise ValueError('Unjournaled audit differs from child')
    else:
        write_new(path, audit)
    append_event(folder, {'kind':'audited', 'slot':slot, 'audit_sha256':file_hash(path)})
    return audit


def report_batch(manifest, results, pending=None):
    groups = {}
    for policy in manifest['policies']:
        rows = [row for row in results if row['policy'] == policy]
        valid = [row for row in rows if row['passed']]
        groups[policy] = {'attempts':len(rows), 'verified_matches':len(valid),
            'wins':sum(row['summary']['episodes'][-1].get('winner_port') == row.get('bot_port',1) for row in valid),
            'losses':sum(row['summary']['episodes'][-1].get('winner_port') == 3-row.get('bot_port',1) for row in valid),
            'failed_attempts':len(rows)-len(valid)}
        groups[policy]['by_port'] = {}
        for port in manifest.get('bot_ports',[1]):
            attempts = [row for row in rows if row.get('bot_port',1)==port]
            checked = [row for row in attempts if row['passed']]
            groups[policy]['by_port'][str(port)] = {'attempts':len(attempts),
                'verified_matches':len(checked),'failed_attempts':len(attempts)-len(checked),
                'wins':sum(row['summary']['episodes'][-1].get('winner_port')==port for row in checked),
                'losses':sum(row['summary']['episodes'][-1].get('winner_port')==3-port for row in checked)}
    status = ('ambiguous_child' if pending is not None else 'stopped' if any(not r['passed'] for r in results)
        else 'complete' if len(results) == len(manifest['schedule']) else 'checkpointed')
    return {'schema_version':1, 'batch_id':manifest['batch_id'], 'status':status,
        'bot_ports':manifest.get('bot_ports',[1]),'schedule_schema_version':manifest['schema_version'],
        'candidate_profile':manifest['candidate_profile'], 'expected_matches':len(manifest['schedule']),
        'audited_attempts':len(results), 'policies':groups,
        'pending_slot':pending['slot'] if pending else None,
        'provider_contacted':True if any(row['summary']['provider_contacted'] for row in results) else None if pending else False,
        'paid_request_cap_per_match':(manifest.get('provider') or {}).get('max_requests'),
        'paid_ledger_checkpoint':(results[-1]['spending']['after'] if results else manifest['provider']['initial_ledger']) if manifest.get('provider') else None,
        'game_rng_seed':None, 'interpretation':'One frozen cohort. Failed attempts remain visible; source revisions require a separate cohort. No causal strength claim.'}


def run_child(root, folder, manifest, slot):
    policy = manifest['schedule'][slot]['policy']
    provider = manifest.get('provider') if policy=='jev' else None
    from .live_provider import provider_environment
    command = [sys.executable, '-B', '-m', 'melee_agent.matches', str(root),
        str(manifest['match_seconds']), '1', policy, '0', '20', provider['budget_directory'] if provider else '',
        str(provider['max_requests']) if provider else '0', '', '', manifest['candidate_profile']]
    if child_port(manifest,slot) != 1:
        command.append(str(child_port(manifest,slot)))
    with (folder/f'match-{slot:02}.log').open('x') as log:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=provider_environment(policy) if provider else isolated_environment())
        try:
            try:
                child.wait(timeout=manifest['match_seconds']+15)
            except subprocess.TimeoutExpired:
                pass  # Close stdin before waiting for owned cleanup below.
        finally:
            # EOF triggers the supervisor's existing owned-child cleanup.
            child.stdin.close()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                raise ValueError('Child cleanup deadline exceeded; retain pending identity without retry') from None


def resume_batch(root, batch_id, *, max_new_matches=20):
    if not bounded(max_new_matches, 1, 20):
        raise ValueError('Invalid checkpoint size')
    folder = locate_batch(root, batch_id)
    with batch_lock(folder):
        manifest, results, pending = load_batch(root, folder)
        if pending is not None:
            # Never adopt a child while an existing supervisor can still own it.
            with batch_lock(root/'build/jev', name='match.lock'):
                pass
            results.append(record_audit(root, folder, manifest, len(results),ledger_before=pending.get('ledger_before')))
        reason = None
        for _ in range(max_new_matches):
            if len(results) == len(manifest['schedule']) or any(not r['passed'] for r in results):
                break
            if source_identity(root) != manifest['source_identity']:
                raise ValueError('Batch source changed')
            if time.time()+manifest['match_seconds']+CHILD_GRACE > manifest['deadline_unix']:
                reason = 'batch_deadline'
                break
            from .incidents import MAX_PREFIX_BYTES
            extra = MAX_PREFIX_BYTES+2*1024**2 if manifest['schedule'][len(results)]['policy']=='jev' else 0
            if (shutil.disk_usage(root).free < 8*1024**3 or
                    sum(r['artifact_bytes'] for r in results)+manifest['max_match_bytes']+extra > 12*1024**3):
                raise ValueError('Batch storage floor or capacity reached')
            slot = len(results)
            provider = manifest.get('provider')
            ledger = None
            if provider:
                ledger = results[-1]['spending']['after'] if results else provider['initial_ledger']
                paid_cohort.verify_checkpoint(root,provider,ledger,exact=True)
                if manifest['schedule'][slot]['policy']=='jev':
                    paid_cohort.admit(root,provider)
            append_event(folder, {'kind':'launch', 'slot':slot,'ledger_before':ledger})
            run_child(root, folder, manifest, slot)
            results.append(record_audit(root, folder, manifest, slot,ledger_before=ledger))
            print(json.dumps({'event':'batch_match_audited', 'batch_id':batch_id,
                'slot':slot, 'run_id':results[-1]['run_id'], 'passed':results[-1]['passed']}), flush=True)
        return {**report_batch(manifest, results), 'stop_reason':reason}


def start_batch(root, *, policies=MODES, matches_per_policy=10, match_seconds=600,
        duration=14400, profile=PROFILE, max_new_matches=20, previous_batch=None,
        budget=None, max_requests=None, bot_ports=None):
    schedule = validate_plan(policies, matches_per_policy, match_seconds, duration, profile,bot_ports)
    if not bounded(max_new_matches, 1, 20):
        raise ValueError('Invalid checkpoint size')
    config = load_config(root)
    if match_seconds > config.limits.max_run_seconds:
        raise ValueError('Match exceeds configured run limit')
    deadline = time.time()+duration
    provider = paid_cohort.make_contract(root,policies,profile,budget,max_requests,deadline)
    previous = None
    if previous_batch is not None:
        prior = locate_batch(root, previous_batch)/'manifest.json'
        if read_json(prior)['batch_id'] != previous_batch:
            raise ValueError('Invalid previous cohort')
        previous = {'batch_id':previous_batch, 'manifest_sha256':file_hash(prior)}
    batch_id = 'batch-'+uuid.uuid4().hex
    folder = locate_batch(root, batch_id)
    folder.mkdir(parents=True)
    manifest = {'schema_version':1 if bot_ports is None else 2, 'batch_id':batch_id, 'policies':list(policies),
        'matches_per_policy':matches_per_policy, 'match_seconds':match_seconds,
        'duration_seconds':duration, 'deadline_unix':deadline,
        'candidate_profile':profile, 'schedule':schedule, 'source_identity':source_identity(root),
        'runtime_sha256':config.runtime_sha256, 'max_match_bytes':config.limits.max_artifact_bytes,
        'provider_enabled':provider is not None, 'provider':provider, 'previous_cohort':previous}
    if bot_ports is not None:
        manifest['bot_ports'] = list(bot_ports)
    write_new(folder/'manifest.json', manifest)
    append_event(folder, {'kind':'created', 'manifest_sha256':file_hash(folder/'manifest.json')})
    print(json.dumps({'event':'batch_started', 'batch_id':batch_id}), flush=True)
    return resume_batch(root, batch_id, max_new_matches=max_new_matches)
