"""Raw movement and attack evidence for the bounded approach-jab probe."""

from .approach_jab import MAX_MOVES, MAX_FRAMES, MAX_DISPLACEMENT, can_start_approach_jab
from .combat_evidence import audit_combat_trace
from .engine import ACTION_PACKETS, Observation
from .skills import GROUND_ACTIONS, SkillSpec, can_start


def audit_option(report,rows,errors):
    evidence = {'moves_acknowledged':0,'jab_acknowledged':False,'completed':False,'contacts':0}
    try:
        skill = report['skill']
        if skill != rows[-1]['scenario']['skill']:
            errors['option_report_trace_mismatch'] += 1
        option = (skill.get('event') or {}).get('option')
        if not option:
            errors['option_report_missing'] += 1
            return evidence
        indexed = {r['frame']:r for r in rows}
        source = Observation.parse(indexed[option['source_frame']]['control']['observation'])
        if can_start_approach_jab(option['direction'],source) is not None:
            errors['option_source_invalid'] += 1
        if option['end_frame'] != rows[-1]['frame'] or option['end_frame']-option['source_frame'] > MAX_FRAMES:
            errors['option_deadline_or_end_mismatch'] += 1
        children = option['children']
        moves = [c for c in children if c['skill']=='move']
        jabs = [c for c in children if c['skill']=='jab']
        if len(moves)>MAX_MOVES or len(jabs)>1 or len(children)!=len(moves)+len(jabs) or option['movement_count']!=len(moves):
            errors['option_child_count'] += 1
        previous = option['source_frame']-1
        for child in children:
            start,end = child['source_frame'],child['frame']
            if start <= previous or end < start or child['direction'] != option['direction']:
                errors['option_child_order'] += 1
            previous=end
            initial=Observation.parse(indexed[start]['control']['observation'])
            if can_start(SkillSpec(child['skill'],child['direction']),initial) is not None:
                errors['option_child_precondition'] += 1
            if abs(initial.bot.x-option['start_x'])>MAX_DISPLACEMENT:
                errors['option_child_travel_bound'] += 1
            window=[indexed[f] for f in range(start,end+1)]
            if child['skill']=='jab':
                combat=child['combat']
                measured=audit_combat_trace('jab',combat,window,errors,completed=child['status']=='succeeded')
                evidence['jab_acknowledged']=measured['motion_acknowledged']
                evidence['contacts']=measured['contact_events']
                if option['combat']!=combat:
                    errors['option_combat_report_mismatch'] += 1
            elif child['ack_frame'] is not None:
                ack=indexed[child['ack_frame']]
                raw=ack['raw_observation']['players']['1']['raw_post']
                direction=child['direction']
                action='right' if direction>0 else 'left'
                valid=(start<child['ack_frame']<=end and not raw['airborne'] and
                    (raw['x']-initial.bot.x)*direction>=6 and raw['action_id'] in GROUND_ACTIONS and
                    raw['speed_ground_x_self']*direction>0 and all(
                        indexed[f]['control']['packet']==ACTION_PACKETS[action].wire()
                        for f in range(start,child['ack_frame'])))
                if not valid:
                    errors['option_movement_not_observed'] += 1
                evidence['moves_acknowledged']+=int(valid)
                terminal=Observation.parse(indexed[end]['control']['observation'])
                if child['status']=='succeeded' and (not terminal.bot.details.input_neutral_derived or
                        indexed[end]['control']['packet']!=ACTION_PACKETS['wait'].wire()):
                    errors['option_movement_release_not_observed'] += 1
            elif child['status']=='succeeded':
                errors['option_movement_ack_missing'] += 1
        if report['result']['status']=='succeeded':
            evidence['completed']=(option['status']=='succeeded' and bool(moves) and
                evidence['moves_acknowledged']==len(moves) and evidence['jab_acknowledged'] and
                bool(jabs) and children[-1]['skill']=='jab' and children[-1]['status']=='succeeded')
            if not evidence['completed']:
                errors['option_completion_not_observed'] += 1
    except (KeyError,TypeError,ValueError,IndexError):
        errors['option_evidence_unavailable'] += 1
    return evidence


def option_acceptance(results,repeats):
    from .scenarios import OPTION_SUITE
    groups={}
    for spec in OPTION_SUITE:
        trials=[r for r in results if r['scenario']==spec.name]
        complete=sum(r['status']=='pass' and r.get('option',{}).get('completed',False) for r in trials)
        groups[spec.name]={'trials':len(trials),'completed':complete,
            'passed':len(trials)==repeats and complete>0 and all(r['status']=='pass' for r in trials)}
    return {'passed':all(g['passed'] for g in groups.values()),'scenarios':groups,
        'required':'At least one raw-audited complete approach and jab per direction; all requested trials retained with valid traces. This pilot gate does not establish reliability or playing strength.'}
