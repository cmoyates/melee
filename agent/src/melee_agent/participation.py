"""Observed opportunity bins for read-only policy participation reporting."""

from collections import Counter, defaultdict

from .tactical_choices import legal_candidates


DEFINITIONS = {
    'inactive': 'Countdown, zero stock, death or respawn motion for either fighter.',
    'own_hitstun': 'Fox has observed hitstun; this takes priority over hitlag.',
    'own_hitlag': 'Fox has observed hitlag, including retained attack hitlag.',
    'airborne': 'Fox is airborne without the preceding conditions.',
    'grounded_atomic_combat': 'At least one locally legal jab, down tilt or grab.',
    'grounded_option_only': 'Approach-jab is legal but no atomic combat action is legal.',
    'grounded_other': 'Other grounded state.',
    'unavailable_source': 'The source observation is unavailable in the retained recording or bounded delivery audit window.',
}


def opportunity_phase(observation,profile):
    a,b=observation.bot,observation.opponent
    if observation.frame<0 or min(a.stocks_remaining,b.stocks_remaining)==0 or min(a.details.action_id,b.details.action_id)<=13:
        return 'inactive'
    if a.details.hitstun_frames_derived:
        return 'own_hitstun'
    if a.details.hitlag_frames_derived:
        return 'own_hitlag'
    if not a.grounded:
        return 'airborne'
    candidates=legal_candidates(observation,profile)
    if any(label in candidates for label in ('jab','dtilt','grab')):
        return 'grounded_atomic_combat'
    if 'approach_jab' in candidates:
        return 'grounded_option_only'
    return 'grounded_other'


class Participation:
    def __init__(self,provider):
        self.frames=defaultdict(Counter)
        self.sources=defaultdict(Counter)
        self.applications=defaultdict(Counter)
        self.attempts_available=provider is not None
        self.attempts=defaultdict(list)
        for attempt in (provider or {}).get('attempts',[]):
            self.attempts[attempt['episode'],attempt['source_frame']].append(attempt)

    def observe(self,observation,phase,owner):
        self.frames[phase]['observed']+=1
        self.frames[phase]['provider_owned']+=int(owner=='provider')
        for attempt in self.attempts.pop((observation.episode,observation.frame),[]):
            self._attempt(phase,attempt)

    def _attempt(self,phase,attempt):
        bucket=self.sources[phase]
        bucket['backend_attempts']+=1
        if attempt['status']=='validated':
            bucket['validated_responses']+=1
            bucket['selected:'+attempt['result']['action']]+=1

    def delivery(self,source_phase,application_phase,accepted):
        self.sources[source_phase]['delivered_responses']+=1
        if accepted:
            self.sources[source_phase]['accepted_choices']+=1
            self.applications[application_phase]['accepted_choices']+=1

    def terminal(self,trial,outcome):
        self.sources[trial['source_phase']][outcome]+=1
        self.applications[trial['application_phase']][outcome]+=1

    def report(self):
        for attempts in self.attempts.values():
            for attempt in attempts:
                self._attempt('unavailable_source',attempt)
        self.attempts.clear()
        return {'schema_version':1,'phase_definitions':DEFINITIONS,
            'backend_attempts_available':self.attempts_available,
            'frames':{k:dict(v) for k,v in self.frames.items()},
            'request_sources':{k:dict(v) for k,v in self.sources.items()},
            'applications':{k:dict(v) for k,v in self.applications.items()},
            'interpretation':'Mutually exclusive observed opportunity bins, not tactical correctness or causal attribution. Frame ownership uses current state; request outcomes and verified completions use the original request source; application outcomes use the delivery state. Delivered responses count frame-loop deliveries, excluding shutdown-only returns. Backend attempts may stop before HTTP. Missing simulated backend attempts are unavailable, not zero. Counts are evidence only when the encompassing audit passes.'}
