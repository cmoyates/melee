"""Raw-state evidence for the bounded natural-knockback recovery experiment."""

from collections import Counter
import hashlib
import json

from .engine import ACTION_PACKETS
from .incidents import stream_records
from .player_roles import raw_fighter, record_bot_port, validate_bot_port
from .raw_observation import combat_counters
from .stage import support_surface
from .trace_limits import MAX_SOURCE_BYTES


def audit_rows(rows):
    errors, trials, seen = Counter(), [], set()
    active = previous = None
    for row in rows:
        if row.get('menu') != 'IN_GAME':
            continue
        try:
            a = raw_fighter(row)
            port = record_bot_port(row)
            life = row['raw_observation']['players'][str(port)]['life_generation_derived']
            frame, episode = row['frame'], row['episode']
            reflex = row['skill']['reflex']
            current = (episode,frame,life)
            if active is not None:
                if previous is None or current != (previous[0],previous[1]+1,previous[2]):
                    active.update(outcome='identity_or_frame_interruption',end_frame=frame)
                    active = None
                elif combat_counters(a)[1]:
                    active.update(outcome='hitstun_interruption',end_frame=frame)
                    active = None
            start = reflex.get('horizontal_start')
            if start is not None:
                key = (start['episode'],start['frame'],start['life'])
                if key not in seen:
                    seen.add(key)
                    if active is not None:
                        errors['overlapping_horizontal_admission'] += 1
                        active.update(outcome='overwritten',end_frame=frame)
                    packet = row['control']['packet']
                    inward = 'right' if a['x'] < 0 else 'left'
                    valid = (key == (episode,frame,life) and frame >= 0 and a['stocks'] > 0 and
                        a['airborne'] == 1 and a['action_id'] == 38 and a['jumps'] == 1 and
                        130 < abs(a['x']) <= 180 and 0 <= a['y'] <= 140 and a['speed_y_self'] <= 0 and
                        combat_counters(a) == (0,0) and start['x'] == a['x'] and start['y'] == a['y'] and
                        start['jumps'] == 1 and start['motion'] == 38 and
                        not any(row['input_provenance']['observed']['buttons'][b] for b in ('X','Y')) and
                        packet == ACTION_PACKETS['jump_'+inward].wire())
                    if not valid:
                        errors['horizontal_admission_not_observed'] += 1
                    active = {'episode':episode,'frame':frame,'life':life,
                        'side':'left' if a['x'] < 0 else 'right','x':a['x'],'y':a['y'],
                        'admission_verified':bool(valid),'jump_ack_frame':None,
                        'outcome':'pending','end_frame':None}
                    trials.append(active)
            if active is not None and frame > active['frame']:
                packet = row['control']['packet']
                if packet['buttons']['X'] or packet['buttons']['Y']:
                    errors['horizontal_repeated_jump_input'] += 1
                if active['jump_ack_frame'] is None and a['jumps'] == 0 and a['action_id'] in (27,28) and a['speed_y_self'] > 0:
                    if frame-active['frame'] > 8:
                        errors['horizontal_late_jump_ack'] += 1
                    active['jump_ack_frame'] = frame
                surface = support_surface(a['x'],a['y'],not a['airborne'])
                if a['action_id'] in (252,253) or (not a['airborne'] and surface in ('ground','left','right','top')):
                    active.update(outcome='observed_ledge_return' if a['action_id'] in (252,253) else 'observed_stage_return',end_frame=frame)
                    active = None
                elif a['stocks'] == 0 or a['action_id'] <= 13:
                    active.update(outcome='death_or_respawn',end_frame=frame)
                    active = None
                elif reflex['failed']:
                    active.update(outcome='reported_failure',end_frame=frame,
                        reported_reason=(reflex.get('event') or {}).get('reason'))
                    active = None
                elif start is None:
                    errors['horizontal_admission_disappeared'] += 1
                    active.update(outcome='unreported_end',end_frame=frame)
                    active = None
            previous = current
        except (KeyError,TypeError,ValueError):
            errors['horizontal_raw_evidence_unavailable'] += 1
            if active is not None:
                active.update(outcome='unavailable_evidence')
                active = None
            previous = None
    groups = {}
    for side in ('left','right'):
        values = [trial for trial in trials if trial['side'] == side]
        groups[side] = {'admissions':len(values),
            'verified_admissions':sum(t['admission_verified'] for t in values),
            'jump_acknowledgements':sum(t['jump_ack_frame'] is not None for t in values),
            'outcomes':dict(Counter(t['outcome'] for t in values))}
    return {'status':'pass' if not errors else 'fail','errors':dict(errors),'sides':groups,'trials':trials,
        'interpretation':'Observed natural-knockback encounters, not seeded setups or counterfactual recoverability. Zero encounters is not coverage. Reported controller failures are separate from raw jump acknowledgements and stage/ledge returns.'}


def inspect_horizontal_recovery(run):
    launch = json.loads((run/'launch.json').read_text())
    summary = json.loads((run/'summary.json').read_text())
    port = validate_bot_port(launch.get('bot_port',1))
    if validate_bot_port(summary.get('bot_port',1)) != port or summary.get('opponent_control','cpu3') != 'cpu3':
        raise ValueError('Horizontal recovery requires consistent CPU3 player roles')
    digest = hashlib.sha256()
    def rows():
        for line,row in stream_records(run/'frames.jsonl',MAX_SOURCE_BYTES):
            digest.update(line)
            if row.get('menu') == 'IN_GAME':
                record_bot_port(row,port)
            yield row
    return {**audit_rows(rows()),'run_id':launch['run_id'],'bot_port':port,
        'frames_sha256':digest.hexdigest(),'provider_contacted':False,'emulator_launched':False,
        'required_companion_audits':'Frame integrity, rules/result, exact control replay and cleanup; this report alone does not certify the run.'}
