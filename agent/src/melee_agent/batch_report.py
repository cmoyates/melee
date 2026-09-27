"""Historical cohort evidence, without replaying code or authorizing execution."""

import hashlib
import io
import json
import math
import re

from .budget import SpendLedger
from .config import owned_path
from .policy_batch import artifact_path, file_hash, locate_batch, locate_run, read_json, validate_plan
from .paid_cohort import verify_replay_artifacts


def require(condition):
    if not condition:
        raise ValueError('Retained batch evidence is inconsistent')


def count(value):
    require(type(value) is int and value >= 0)
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value))
    return value


def ledger_prefix(root, contract, checkpoint):
    size = count(checkpoint['bytes'])
    require(0 < size <= 8_000_000)
    with (owned_path(root, contract['budget_directory'])/'spend.jsonl').open('rb') as handle:
        raw = handle.read(size)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest(checkpoint['sha256']))
    rows = SpendLedger._read(io.BytesIO(raw))
    header, reserved, settled, cost, tokens, overrun = SpendLedger._state(rows)
    report = {**header, 'requests':len(reserved), 'unsettled_requests':len(reserved)-len(settled),
        'accounted_nano_usd':cost, 'reported_nano_usd':sum(r['cost_nano_usd'] for r in settled.values()),
        'accounted_input_tokens':tokens, 'reservation_exceeded':overrun}
    require(checkpoint['report'] == report)
    return report


def snapshot(root, batch_id):
    """Verify historical hashes; current source/ledger suffix need not be identical."""
    folder = locate_batch(root, batch_id)
    manifest = read_json(folder/'manifest.json')
    require(manifest['schema_version'] == 1 and manifest['batch_id'] == batch_id)
    plan = validate_plan(manifest['policies'], manifest['matches_per_policy'],
        manifest['match_seconds'], manifest['duration_seconds'], manifest['candidate_profile'])
    require(manifest['schedule'] == plan)
    contract = manifest.get('provider')
    require(bool(contract) == manifest['provider_enabled'] == ('jev' in manifest['policies']))
    journal = (folder/'events.jsonl').read_bytes()
    require(len(journal) <= 65536 and journal.endswith(b'\n'))
    events = [json.loads(line) for line in journal.splitlines()]
    manifest_hash = file_hash(folder/'manifest.json')
    require(events[0] == {'kind':'created', 'manifest_sha256':manifest_hash})
    rows, pending, identities = [], None, set()
    checkpoint = contract['initial_ledger'] if contract else None
    if contract:
        require(contract['profile'] == manifest['candidate_profile'])
        ledger_prefix(root, contract, checkpoint)
    for event in events[1:]:
        slot = len(rows)
        require(event['slot'] == slot and slot < len(plan))
        if event['kind'] == 'launch':
            require(pending is None and all(row['passed'] for row in rows))
            require(event.get('ledger_before') == checkpoint)
            pending = event
            continue
        require(event['kind'] == 'audited' and pending is not None)
        path = folder/f'audit-{slot:02}.json'
        require(file_hash(path) == digest(event['audit_sha256']))
        audit = read_json(path)
        require(audit['schema_version'] == 1 and type(audit['passed']) is bool)
        require(audit['slot'] == slot and audit['policy'] == plan[slot]['policy'])
        require(audit['run_id'] not in identities)
        identities.add(audit['run_id'])
        run = locate_run(root, audit['run_id'])
        require({'launch.json','summary.json','frames.jsonl'} <= audit['artifact_sha256'].keys())
        for name, expected in audit['artifact_sha256'].items():
            require(file_hash(artifact_path(run, name)) == digest(expected))
        summary, launch = read_json(run/'summary.json'), read_json(run/'launch.json')
        require(summary == audit['summary'])
        require(summary['run_id'] == launch['run_id'] == audit['run_id'])
        require(summary['policy'] == launch['policy'] == audit['policy'])
        require(launch['source_sha256'] == manifest['source_identity']['modules'])
        require(launch['runtime_sha256'] == manifest['runtime_sha256'])
        require(launch['candidate_profile'] == manifest['candidate_profile'])
        for replay in summary['replays']:
            require(audit['artifact_sha256']['replays/'+replay['file']] == replay['sha256'])
        if contract:
            spending = audit['spending']
            require(spending['before'] == checkpoint)
            after = spending['after']
            ledger_prefix(root, contract, after)
            require(after['bytes'] >= checkpoint['bytes'])
            require(after['report']['requests']-checkpoint['report']['requests'] == count(spending['reserved_requests']))
            if audit['policy'] != 'jev':
                require(after == checkpoint and spending['reserved_requests'] == 0)
            else:
                require(after['report']['accounted_nano_usd']-checkpoint['report']['accounted_nano_usd'] == count(spending['accounted_cost_nano_usd']))
            checkpoint = after
        if audit['policy'] == 'jev':
            verify_replay_artifacts(root, audit['control_replay'])
        rows.append(audit)
        pending = None
    # Read-only snapshot: never repair/adopt a child, and never suppress a race.
    require((folder/'events.jsonl').read_bytes() == journal)
    require(file_hash(folder/'manifest.json') == manifest_hash)
    return manifest, rows, pending, hashlib.sha256(journal).hexdigest(), manifest_hash


def wilson(wins, matches):
    if matches == 0:
        return None
    z = 1.959963984540054
    rate, denominator = wins/matches, 1+z*z/matches
    center = (rate+z*z/(2*matches))/denominator
    radius = z*math.sqrt(rate*(1-rate)/matches+z*z/(4*matches*matches))/denominator
    return [0.0 if wins == 0 else max(0.0, center-radius),
        1.0 if wins == matches else min(1.0, center+radius)]


def counters(value):
    require(isinstance(value, dict))
    result = {}
    for key, number in value.items():
        require(re.fullmatch('[a-z][a-z0-9_:]*', key) is not None and len(key) <= 100)
        result[key] = count(number)
    return result


def distribution(value):
    if value is None:
        return None
    result = {'count':count(value['count'])}
    for key in ('p50','p95','p99','max'):
        number = value.get(key)
        require(number is None or type(number) in (int,float) and math.isfinite(number) and number >= 0)
        result[key] = number
    return result


def provider_identity(summary):
    backend = (summary.get('async_policy') or {}).get('bridge',{}).get('provider')
    if backend is None:
        return None
    observed = {}
    for attempt in backend['attempts']:
        if attempt['status'] != 'validated':
            continue
        result = attempt['result']
        identity = tuple(result.get(k) for k in ('requested_model','resolved_model','provider'))
        require(all(v is None or isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9~_.:/ -]{1,160}',v) for v in identity))
        observed[identity] = observed.get(identity,0)+1
    return [{**dict(zip(('requested_model','resolved_model','provider'),identity)), 'validated_responses':n}
        for identity,n in observed.items()]


def initialization_seed(path):
    try:
        import ubjson
    except ImportError:
        return None  # Runtime decoder is optional; hashes still verify independently.
    raw = ubjson.loadb(path.read_bytes())['raw']
    require(len(raw) >= 2 and raw[0] == 0x35 and (raw[1]-1) % 3 == 0)
    sizes = {raw[i]:int.from_bytes(raw[i+1:i+3], 'big')+1 for i in range(2, raw[1]+1, 3)}
    start = raw[raw[1]+1:raw[1]+1+sizes[0x36]]
    require(len(start) == sizes[0x36] and start[0] == 0x36)
    return int.from_bytes(start[0x13D:0x141], 'big') if len(start) >= 0x141 else None


def match_row(root, audit):
    summary, control = audit['summary'], audit['control_replay']
    episodes = summary['episodes']
    final = episodes[-1] if episodes else {}
    row = {'slot':audit['slot'], 'run_id':audit['run_id'], 'policy':audit['policy'],
        'passed':audit['passed'], 'winner_port':final.get('winner_port') if audit['passed'] else None,
        'final_stocks':final.get('last_stocks'), 'elapsed_seconds':summary['elapsed_seconds'],
        'game_frames':sum(count(e['observations']) for e in episodes),
        'integrity_passed':audit['integrity']['status']=='pass',
        'control_audit_passed':control['status']=='pass', 'rules_and_result':audit['rules_and_result'],
        'frames_sha256':digest(audit['artifact_sha256']['frames.jsonl']),
        'packets_sha256':None,
        'replays':[], 'provider':None}
    require(type(row['elapsed_seconds']) in (int,float) and math.isfinite(row['elapsed_seconds']) and row['elapsed_seconds'] >= 0)
    require(row['final_stocks'] is None or len(row['final_stocks']) == 2 and all(type(n) is int and 0 <= n <= 4 for n in row['final_stocks']))
    require(row['winner_port'] in (None,1,2))
    packets = (control.get('sealed_replay') or control).get('packets_sha256')
    if packets is not None:
        row['packets_sha256'] = digest(packets)
    if audit['passed']:
        require(summary['status'] == 'complete' and summary['completed_matches'] == 1 and
            row['integrity_passed'] and row['control_audit_passed'] and row['rules_and_result'] and
            row['winner_port'] in (1,2) and packets is not None)
    for replay in summary['replays']:
        path = artifact_path(locate_run(root,audit['run_id']), 'replays/'+replay['file'])
        try:
            seed = initialization_seed(path)
        except (ValueError,KeyError,IndexError,TypeError):
            if audit['passed']:
                raise
            seed = None
        row['replays'].append({'sha256':digest(replay['sha256']), 'observed_rng_seed':seed})
    if audit['policy'] == 'jev':
        evidence, spending = control['policy_evidence'], audit['spending']
        phases = evidence.get('participation')
        if phases:
            allowed = {'airborne','grounded_aerial_only','grounded_atomic_combat','grounded_option_only',
                'grounded_other','inactive','own_hitlag','own_hitstun','unavailable_source'}
            require(all(set(phases[kind]) <= allowed for kind in ('frames','request_sources','applications')))
        row['provider'] = {'reserved_requests':count(spending['reserved_requests']),
            'identities':provider_identity(summary),
            'attempts':count(spending['attempts']), 'http_calls':count(spending['http_calls']),
            'validated':count(spending['validated']), 'outcomes':counters(evidence['outcomes']),
            'raw_acknowledgements':counters(evidence['acknowledgements']),
            'owner_frames':counters(evidence['input_owner_frames']),
            'source_to_reply_ms':distribution(evidence.get('source_to_reply_ms')),
            'accepted_age_ms':distribution(evidence.get('accepted_age_ms')),
            'observed_to_queued_ms':distribution(evidence.get('observed_to_queued_ms')),
            'observed_to_flushed_ms':distribution(evidence.get('observed_to_flushed_ms')),
            'phases':{kind:{phase:counters(numbers) for phase,numbers in phases[kind].items()}
                for kind in ('frames','request_sources','applications')} if phases else None}
    return row


def build_report(root, batch_id):
    manifest, audits, pending, journal_hash, manifest_hash = snapshot(root,batch_id)
    rows = [match_row(root, audit) for audit in audits]
    groups = {}
    for policy in manifest['policies']:
        selected = [r for r in rows if r['policy'] == policy]
        valid = [r for r in selected if r['passed']]
        wins = sum(r['winner_port'] == 1 for r in valid)
        groups[policy] = {'audited':len(selected), 'verified_matches':len(valid), 'wins':wins,
            'losses':sum(r['winner_port'] == 2 for r in valid), 'failed_attempts':len(selected)-len(valid),
            'win_fraction':wins/len(valid) if valid else None, 'wilson_95':wilson(wins,len(valid)),
            'verified_game_frames':sum(r['game_frames'] for r in valid)}
    source = manifest['source_identity']
    modules = {name:digest(sha) for name,sha in source['modules'].items()}
    require(all(re.fullmatch(r'[a-z_]+\.py',name) for name in modules))
    provider = manifest.get('provider')
    spending = None
    if provider:
        initial = provider['initial_ledger']
        last = audits[-1]['spending']['after'] if audits else initial
        before, after = initial['report'], last['report']
        spending = {key:count(after[key]-before[key]) for key in
            ('requests','accounted_nano_usd','reported_nano_usd','unsettled_requests')}
        spending['uncertain_reserved_nano_usd'] = count(spending['accounted_nano_usd']-spending['reported_nano_usd'])
        spending['through_slot'] = len(rows)-1 if rows else None
        spending['ledger_prefix_sha256'] = digest(last['sha256'])
        spending['includes_pending_spending'] = False
    # Recheck the journal after replay metadata reads too.
    require(file_hash(locate_batch(root,batch_id)/'events.jsonl') == journal_hash)
    return {'schema_version':1, 'batch_id':batch_id,
        'status':'pending' if pending else 'failed' if any(not r['passed'] for r in rows)
            else 'complete' if len(rows)==len(manifest['schedule']) else 'checkpointed',
        'scheduled_matches':len(manifest['schedule']), 'audited_matches':len(rows),
        'pending_slot':pending['slot'] if pending else None,
        'unattempted_slots':len(manifest['schedule'])-len(rows)-int(pending is not None),
        'candidate_profile':manifest['candidate_profile'],
        'manifest_sha256':manifest_hash, 'journal_sha256':journal_hash,
        'recorded_modules_sha256':modules, 'runtime_sha256':digest(manifest['runtime_sha256']),
        'local_config_sha256':digest(source['local_config']) if source['local_config'] else None,
        'provider_config_sha256':digest(provider['config_sha256']) if provider else None,
        'policies':groups, 'spending':spending, 'matches':rows,
        'provider_contacted_by_report':False, 'emulator_launched_by_report':False,
        'interpretation':'Historical audits and retained artifact hashes verified; no controller replay rerun. '
            'Current checkout may differ and this report does not authorize resume. '
            'Wins use only passed matches; failures, pending and unattempted slots remain visible. '
            'Wilson intervals describe binomial sampling uncertainty only, not causal or held-out strength. '
            'Bot is port 1; game RNG was observed, not configured; games are not paired. '
            'Phase counters have the original participation semantics, not correctness labels. '
            'Latency distributions are per match, never averages of percentiles. '
            'Spending covers committed cohort audits only, excluding earlier experiments and pending calls. '
            'Unknown charges retain reservations. No self-destruct or counterfactual damage attribution.'}


def markdown(report):
    lines = [f"Batch `{report['batch_id']}`: **{report['status']}**.", '',
        f"{report['audited_matches']}/{report['scheduled_matches']} audited; "
        f"pending slot: {report['pending_slot']}; unattempted: {report['unattempted_slots']}.", '',
        '| Policy | Verified | Wins | Losses | Failed | Win fraction, Wilson 95% |',
        '| --- | ---: | ---: | ---: | ---: | --- |']
    for policy, group in report['policies'].items():
        interval = group['wilson_95']
        rate = 'unavailable' if interval is None else f"{group['win_fraction']:.3f} [{interval[0]:.3f}, {interval[1]:.3f}]"
        lines.append(f"| {policy} | {group['verified_matches']} | {group['wins']} | {group['losses']} | {group['failed_attempts']} | {rate} |")
    if report['spending']:
        spend = report['spending']
        lines.extend(['', f"Cohort accounted: ${spend['accounted_nano_usd']/1e9:.9f}; "
            f"reported: ${spend['reported_nano_usd']/1e9:.9f}; "
            f"uncertain reserved: ${spend['uncertain_reserved_nano_usd']/1e9:.9f}."])
    lines.extend(['', report['interpretation'], '', 'Exact public snapshot (including per-match metrics and provenance):',
        '', '```json', json.dumps(report,indent=2,allow_nan=False), '```', ''])
    return '\n'.join(lines)
