"""Bounded deterministic replay of local selectors on retained observations."""

import hashlib
from pathlib import Path

from .engine import FrameExecutor, Observation
from .incidents import PacketDigest, RecordedClock, contract_hashes, read_json, stream_records
from .local_combat_policy import LOCAL_MODES, LocalCombatPolicy
from .trace_limits import MAX_SOURCE_BYTES


def inspect_local_policy(run):
    summary, launch = read_json(run/'summary.json'), read_json(run/'launch.json')
    report = summary['local_policy']
    mode, seed = report['mode'], report['seed']
    if mode not in LOCAL_MODES or launch['policy'] != mode or summary['policy'] != mode:
        raise ValueError('Local policy identity mismatch')
    expected = {**contract_hashes(), 'local_combat_policy.py':
        hashlib.sha256((Path(__file__).parent/'local_combat_policy.py').read_bytes()).hexdigest()}
    if any(launch['source_sha256'].get(name) != digest for name, digest in expected.items()):
        raise ValueError('Local policy replay requires the launch source checkout')
    policy, clock, packets = LocalCombatPolicy(mode, seed), RecordedClock(), PacketDigest()
    executor = FrameExecutor(policy, packets, clock)
    records, selections, divergence = 0, 0, None
    digest = hashlib.sha256()
    for line, row in stream_records(run/'frames.jsonl', MAX_SOURCE_BYTES):
        digest.update(line)
        if row['menu'] != 'IN_GAME':
            continue
        control = row['control']
        clock.values = [control['executor_started_ns'], control['queued_ns']]
        actual = executor.step(Observation.parse(control['observation']))
        records += 1
        selections += row['skill'].get('local_selection') is not None
        if (actual['decision'] != control['decision'] or actual['packet'] != control['packet'] or
                policy.trace() != row['skill']):
            divergence = {'episode':row['episode'], 'frame':row['frame']}
            break
    summary_matches = divergence is None and policy.close() == report
    return {'schema_version':1, 'run_id':launch['run_id'], 'mode':mode, 'seed':seed,
        'status':'pass' if records and divergence is None and summary_matches else 'fail',
        'replayed_records':records, 'selections':selections, 'divergence':divergence,
        'summary_matches':summary_matches, 'packets_sha256':packets.digest.hexdigest(),
        'frames_sha256':digest.hexdigest() if divergence is None else None,
        'provider_contacted':False, 'emulator_launched':False, 'controller_written':False,
        'interpretation':'Exact local control replay on retained observations; run the separate integrity audit for raw input, rules and result evidence. No counterfactual physics claim.'}
