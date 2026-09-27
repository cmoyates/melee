"""Independent native-state and packet checks for a declared platform transfer."""

import math

from .engine import ACTION_PACKETS, BUTTONS
from .platform_jump import target_platform
from .player_roles import raw_fighter
from .raw_observation import combat_counters
from .stage import support_surface


def neutral(packet):
    return (set(packet['buttons'])==set(BUTTONS) and
        all(type(v) is bool and not v for v in packet['buttons'].values()) and
        all(0<=packet[key]<=.025 for key in ('l','r')) and
        all(len(packet[key])==2 and all(abs(v-.5)<=.025 for v in packet[key]) for key in ('main','c')))


def held_jump(packet):
    return (packet['buttons'].get('X') is True and
        neutral({**packet,'buttons':{**packet['buttons'],'X':False}}))


def audit_platform(spec,report,rows,errors):
    evidence={'full_jump_observed':False,'target_platform':target_platform(spec.direction)['id'],
        'completed':False,'peak_height':None}
    try:
        skill=report['skill']
        if skill!=rows[-1]['scenario']['skill']:
            errors['platform_report_trace_mismatch']+=1
        trace=(skill.get('event') or {}).get('platform') or (skill.get('active') or {}).get('platform')
        if trace is None:
            errors['platform_trace_missing']+=1
            return evidence
        indexed={row['frame']:row for row in rows}
        def raw(frame):return raw_fighter(indexed[frame])
        def packet(frame):return indexed[frame]['control']['packet']
        target=target_platform(spec.direction)
        start,knee,ack,landing,end=(trace[key] for key in ('source_frame','knee_frame','ack_frame','landing_frame','end_frame'))
        if trace['target']!=target['id'] or trace['direction']!=spec.direction or start!=rows[0]['frame']:
            errors['platform_identity_mismatch']+=1
        if any(row['control']['packet'] not in (ACTION_PACKETS['jump'].wire(),ACTION_PACKETS['wait'].wire()) for row in rows):
            errors['platform_unexpected_input']+=1
        if len(trace['children'])>1 or any(c['skill']!='jump' or c['direction']!=0 for c in trace['children']):
            errors['platform_repeated_or_wrong_child']+=1
        if ack is not None:
            source=raw(start)
            evidence['full_jump_observed']=(start<knee<ack<start+8 and
                source['airborne']==0 and source['action_id']==14 and source['jumps']==2 and
                support_surface(source['x'],source['y'],True)=='ground' and
                target['left']+8<=source['x']<=target['right']-8 and
                abs(source['speed_ground_x_self'])<.05 and neutral(indexed[start]['input_provenance']['observed']) and
                all(packet(f)==ACTION_PACKETS['jump'].wire() for f in range(start,ack)) and
                all(raw(f)['action_id']==24 and raw(f)['airborne']==0 and
                    held_jump(indexed[f]['input_provenance']['observed']) for f in range(knee,ack)) and
                raw(ack)['action_id'] in (25,26) and raw(ack)['airborne']==1 and raw(ack)['jumps']==1 and
                raw(ack)['speed_y_self']>0 and math.isclose(raw(ack)['speed_y_self'],trace['takeoff_velocity_y'],abs_tol=1e-6) and
                all(packet(f)==ACTION_PACKETS['wait'].wire() for f in range(ack,rows[-1]['frame']+1)))
            if not evidence['full_jump_observed']:
                errors['platform_full_jump_not_observed']+=1
        if report['result']['status']=='succeeded':
            evidence['completed']=(evidence['full_jump_observed'] and trace['status']=='succeeded' and
                landing is not None and ack<landing<end==rows[-1]['frame'] and
                end-start<90 and
                len(trace['children'])==1 and trace['children'][0]['status']=='succeeded' and
                all(abs(raw(f)['x']-raw(start)['x'])<=2 and
                    target['left']+4<=raw(f)['x']<=target['right']-4 and
                    -12<=raw(f)['y']<=target['height']+20 for f in range(start,end+1)) and
                all(raw(f)['airborne']==1 and raw(f)['jumps']==1 and
                    raw(f)['action_id'] in (25,26,29,30,31) for f in range(ack,landing)) and
                all(raw(f)['airborne']==0 and support_surface(raw(f)['x'],raw(f)['y'],True)==target['id']
                    for f in range(landing,end+1)) and raw(end)['action_id']==14 and raw(end)['jumps']==2 and
                neutral(indexed[end]['input_provenance']['observed']) and
                all(combat_counters(raw(f))==(0,0) for f in range(start,end+1)))
            if not evidence['completed']:
                errors['platform_completion_not_observed']+=1
            else:
                peak=max(raw_fighter(row)['y']-raw(start)['y'] for row in rows)
                evidence['peak_height']=peak
                if not math.isclose(peak,trace['peak_height'],abs_tol=1e-6):
                    errors['platform_peak_mismatch']+=1
    except (KeyError,TypeError,ValueError,IndexError):
        errors['platform_evidence_unavailable']+=1
    return evidence


def platform_acceptance(results,repeats):
    groups={}
    for side in ('left','right'):
        name='calibration-platform-jump-'+side
        rows=[r for r in results if r['scenario']==name]
        valid=[r for r in rows if r['status']=='pass' and r.get('opponent_control')=='neutral-human-v1']
        acknowledged=sum(r.get('platform',{}).get('full_jump_observed',False) for r in valid)
        completed=sum(r.get('platform',{}).get('completed',False) and r['trial_status']=='succeeded' for r in valid)
        groups[name]={'trials':len(rows),'acknowledged':acknowledged,'completed':completed,
            'passed':repeats==20 and len(rows)==acknowledged==completed==20}
    unrecognized=len(results)-sum(g['trials'] for g in groups.values())
    return {'passed':unrecognized==0 and all(g['passed'] for g in groups.values()),'scenarios':groups,
        'unrecognized_trials':unrecognized,
        'required':'20/20 audited full jumps and standing neutral completions on each declared side platform; neutral fixture only.'}
