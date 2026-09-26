"""Conserved ledger checkpoints and sealed replay for explicit paid cohorts."""

from datetime import datetime
import hashlib
import json

from .budget import SpendLedger
from .config import owned_path
from .incidents import export_incident, replay_incident
from .live_provider import policy_config_hash, preflight
from .policy_evidence import inspect_policy
from .provider import RESERVE_INPUT_TOKENS, RESERVE_NANO_USD


def checkpoint(root, directory):
    ledger = SpendLedger(owned_path(root, directory)/'spend.jsonl')
    with ledger._locked() as handle:
        records = ledger._read(handle)
        header, reserved, settled, cost, tokens, overrun = ledger._state(records)
        handle.seek(0)
        raw = handle.read()
    report = {**header, 'requests':len(reserved), 'unsettled_requests':len(reserved)-len(settled),
        'accounted_nano_usd':cost, 'reported_nano_usd':sum(r['cost_nano_usd'] for r in settled.values()),
        'accounted_input_tokens':tokens, 'reservation_exceeded':overrun,
        **({'sealed':True,'continuation':records[-1]} if records[-1]['kind']=='seal' else {})}
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'report':report}


def admit(root, contract):
    report = preflight(root, 'jev', contract['budget_directory'], contract['max_requests'])
    if (report['requests'] >= report['max_requests'] or
            report['accounted_input_tokens']+RESERVE_INPUT_TOKENS > report['max_input_tokens'] or
            report['accounted_nano_usd']+RESERVE_NANO_USD > report['limit_nano_usd']):
        raise ValueError('Paid cohort has no available reservation capacity')
    if contract['config_sha256'] != policy_config_hash(contract['profile']):
        raise ValueError('Paid cohort provider configuration changed')


def make_contract(root, policies, profile, budget, max_requests, deadline):
    if 'jev' not in policies:
        if budget is not None or max_requests is not None:
            raise ValueError('Paid options require an explicit Jev slot')
        return None
    if not budget or type(max_requests) is not int or not 1 <= max_requests <= 200:
        raise ValueError('Paid cohorts require an existing ledger and 1-200 requests per match')
    directory = str(owned_path(root, budget).relative_to(root))
    contract = {'budget_directory':directory,'max_requests':max_requests,
        'profile':profile,'config_sha256':policy_config_hash(profile)}
    admit(root, contract)
    contract['initial_ledger'] = checkpoint(root, directory)
    if deadline > datetime.fromisoformat(contract['initial_ledger']['report']['deadline_utc']).timestamp():
        raise ValueError('Batch deadline exceeds its conserved ledger deadline')
    return contract


def verify_checkpoint(root, contract, expected, *, exact):
    path = owned_path(root, contract['budget_directory'])/'spend.jsonl'
    if type(expected['bytes']) is not int or not 1 <= expected['bytes'] <= 8_000_000:
        raise ValueError('Invalid ledger checkpoint bound')
    with path.open('rb') as handle:
        prefix = handle.read(expected['bytes'])
    if len(prefix) != expected['bytes'] or hashlib.sha256(prefix).hexdigest() != expected['sha256']:
        raise ValueError('Recorded ledger prefix changed')
    current = checkpoint(root, contract['budget_directory'])
    if exact and current != expected:
        raise ValueError('Unexpected ledger changes between cohort matches')
    return current


def audit_spending(root, contract, before, launch, summary, policy):
    after = verify_checkpoint(root, contract, before, exact=policy!='jev')
    if policy != 'jev':
        return {'before':before,'after':after,'reserved_requests':0}
    provider = summary['async_policy']['bridge']['provider']
    if (launch['provider_budget_before'] != before['report'] or
            provider['budget_before'] != before['report'] or provider['budget_after'] != after['report'] or
            launch['budget_directory'] != contract['budget_directory'] or
            launch['max_provider_requests'] != contract['max_requests'] or
            provider['max_requests'] != contract['max_requests'] or
            provider['config_sha256'] != contract['config_sha256'] or
            provider['candidate_profile'] != contract['profile']):
        raise ValueError('Paid child differs from frozen spending contract')
    path = owned_path(root, contract['budget_directory'])/'spend.jsonl'
    with path.open('rb') as handle:
        handle.seek(before['bytes'])
        tail = handle.read(8_000_001)
    if len(tail) > 8_000_000:
        raise ValueError('Ledger append exceeds bound')
    records = [json.loads(line) for line in tail.splitlines()]
    ids = [r['id'] for r in records if r['kind']=='reserve']
    attempts = provider['attempts']
    traced = [r['request_id'] for r in attempts if 'request_id' in r]
    if (len(attempts) > contract['max_requests'] or len(ids) != len(set(ids)) or
            len(traced) != len(set(traced)) or set(ids) != set(traced) or
            any(r['kind'] not in ('reserve','settle') or r['id'] not in ids for r in records) or
            after['report']['requests']-before['report']['requests'] != len(ids) or
            after['report'].get('sealed') or after['report']['reservation_exceeded']):
        raise ValueError('Ledger changes do not belong exactly to recorded child attempts')
    return {'before':before,'after':after,'reserved_requests':len(ids),
        'accounted_cost_nano_usd':after['report']['accounted_nano_usd']-before['report']['accounted_nano_usd'],
        'http_calls':provider['http_calls'],'attempts':len(attempts),
        'validated':sum(r['status']=='validated' for r in attempts),
        'remaining_uncertain_requests':after['report']['unsettled_requests'],
        'provider_shutdown':provider['http_active']==0 and all(v==0 for v in provider['client_shutdown'].values())}


def audit_replay(root, folder, slot, run, summary):
    # The pointer is durable before the parent audit. Adoption reuses the same
    # sealed incident rather than creating a new UUID and changing the audit.
    from .policy_batch import file_hash, read_json, write_new
    marker = folder/f'paid-replay-{slot:02}.json'
    if marker.exists():
        pointer = read_json(marker)
    else:
        last = summary['episodes'][-1]
        exported = export_incident(root, run, episode=last['episode'],frame=last['last_frame'],after_frames=0)
        pointer = {'run_id':run.name,'incident_id':exported['incident_id']}
        write_new(marker, pointer)
    incident_id = pointer['incident_id']
    if (pointer['run_id'] != run.name or not isinstance(incident_id,str) or
            len(incident_id)!=41 or not incident_id.startswith('incident-') or
            any(c not in '0123456789abcdef' for c in incident_id[9:])):
        raise ValueError('Invalid paid replay pointer')
    incident = owned_path(root,'build/jev/incidents/'+incident_id)
    if read_json(incident/'manifest.json')['run_id'] != run.name:
        raise ValueError('Sealed replay belongs to another child')
    replay = replay_incident(root, incident)
    policy = inspect_policy(run)
    passed = (replay['status']==policy['status']=='pass' and
        replay['replayed_records']==sum(e['observations'] for e in summary['episodes']) and
        policy['outcomes'].get('accepted',0)>0)
    files = ('manifest.json','focus.json','prefix.jsonl')
    return {'status':'pass' if passed else 'fail','sealed_replay':replay,'policy_evidence':policy,
        'incident_sha256':{name:file_hash(incident/name) for name in files},
        'incident_bytes':sum((incident/name).stat().st_size for name in files)}


def verify_replay_artifacts(root, evidence):
    from .policy_batch import file_hash
    incident_id = evidence['sealed_replay']['incident_id']
    if (len(incident_id)!=41 or not incident_id.startswith('incident-') or
            any(c not in '0123456789abcdef' for c in incident_id[9:])):
        raise ValueError('Invalid paid replay identity')
    folder = owned_path(root,'build/jev/incidents/'+incident_id)
    if (set(evidence['incident_sha256']) != {'manifest.json','focus.json','prefix.jsonl'} or
            any(file_hash(folder/name)!=digest for name,digest in evidence['incident_sha256'].items())):
        raise ValueError('Sealed paid replay artifacts changed')
