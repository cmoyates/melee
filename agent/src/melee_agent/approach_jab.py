"""One bounded grounded approach followed by a newly validated single jab."""

from .ground_combat import COMBAT, GUARD, CAPTOR, CAPTURED, START_ACTIONS, can_start_combat
from .stage import support_surface

MAX_FRAMES = 180
MAX_MOVES = 4
MAX_DISPLACEMENT = 30.
MAX_START_RANGE = 34.
MAX_CHASE_RANGE = 40.


def opportunity(observation, direction, surface=None, maximum_range=MAX_START_RANGE):
    a,b = observation.bot,observation.opponent
    if observation.frame < 0 or min(a.stocks_remaining,b.stocks_remaining) == 0 or min(a.details.action_id,b.details.action_id) <= 13:
        return 'inactive'
    if a.details.hitlag_frames_derived or a.details.hitstun_frames_derived:
        return 'own_damage_or_hitlag'
    current = support_surface(a.x,a.y,a.grounded)
    if current is None or current != support_surface(b.x,b.y,b.grounded) or (surface is not None and current != surface):
        return 'shared_support_changed'
    if direction not in (-1,1) or (b.x-a.x)*direction <= 0:
        return 'opponent_crossed'
    if abs(b.x-a.x) > maximum_range or abs(b.y-a.y) > 3:
        return 'opponent_out_of_range'
    if b.details.hurtbox_state != 0:
        return 'opponent_invulnerable_or_unknown'
    if b.details.action_id in (*GUARD,*CAPTOR,*CAPTURED):
        return 'opponent_guarding_or_captured'
    return None


def can_start_approach_jab(direction, observation):
    from .skills import SkillSpec, can_start, GROUND_ACTIONS
    reason = opportunity(observation,direction)
    if reason:
        return reason
    a,b = observation.bot,observation.opponent
    if a.details.action_id not in GROUND_ACTIONS or not a.details.input_neutral_derived:
        return 'requires_released_ground_input'
    if (1 if a.details.facing_right else -1) != direction:
        return 'wrong_facing'
    if abs(b.x-a.x) <= COMBAT['jab']['range']:
        return can_start_combat('jab',direction,observation)
    return can_start(SkillSpec('move',direction),observation)


class ApproachJab:
    def __init__(self,direction,observation):
        from .skills import SkillArbiter
        refusal = can_start_approach_jab(direction,observation)
        if refusal:
            raise ValueError(refusal)
        a,b = observation.bot,observation.opponent
        self.direction = direction
        self.identity = (observation.episode,a.details.life_generation_derived,b.details.life_generation_derived)
        self.surface = support_surface(a.x,a.y,a.grounded)
        self.started,self.start_x = observation.frame,a.x
        self.child = SkillArbiter()
        self.previous_frame = None
        self.phase = 'choose_child'
        self.moves = 0
        self.children = []
        self.combat = None
        self.ack_frame = self.end_frame = None
        self.status = self.reason = None
        self.last_action = 'wait'

    def retains_attack_hitlag(self,observation):
        return self.child.retains_attack_hitlag(observation)

    def finish(self,observation,status,reason):
        if self.child.active is not None:
            self.child.abort(observation,reason)
            self.children.append(dict(self.child.last_event))
            self.combat = self.child.last_event.get('combat') or self.combat
        self.status,self.reason,self.end_frame = status,reason,observation.frame
        self.phase,self.last_action = 'finished','wait'
        return 'wait'

    def step(self,observation):
        from .skills import SkillSpec, GROUND_ACTIONS
        a,b,frame = observation.bot,observation.opponent,observation.frame
        if self.status is not None:
            return 'wait'
        identity = (observation.episode,a.details.life_generation_derived,b.details.life_generation_derived)
        if identity != self.identity:
            return self.finish(observation,'aborted','life_or_episode_changed')
        if self.previous_frame is not None and frame != self.previous_frame+1:
            return self.finish(observation,'aborted','observation_discontinuity')
        self.previous_frame = frame
        if frame-self.started >= MAX_FRAMES:
            return self.finish(observation,'timeout','option_deadline')
        if a.details.hitstun_frames_derived:
            return self.finish(observation,'aborted','own_hitstun')
        # Once pressed, let the existing jab primitive measure hitlag, contact
        # and completion. Changed opponent geometry cannot retract that press.
        attacking = self.child.active is not None and self.child.active['spec'].name == 'jab'
        if not attacking:
            reason = opportunity(observation,self.direction,self.surface,MAX_CHASE_RANGE)
            if reason:
                return self.finish(observation,'aborted',reason)
            if abs(a.x-self.start_x) > MAX_DISPLACEMENT:
                return self.finish(observation,'aborted','travel_bound')
        if self.child.active is None:
            if a.details.action_id not in GROUND_ACTIONS:
                return self.finish(observation,'aborted','unexpected_setup_motion')
            if a.details.action_id in START_ACTIONS and a.details.input_neutral_derived:
                if (1 if a.details.facing_right else -1) != self.direction:
                    return self.finish(observation,'aborted','facing_changed')
                name = 'jab' if abs(b.x-a.x) <= COMBAT['jab']['range'] else 'move'
                if name == 'move' and self.moves >= MAX_MOVES:
                    return self.finish(observation,'aborted','movement_count_bound')
                refusal = self.child.request(SkillSpec(name,self.direction),observation)
                if refusal:
                    return self.finish(observation,'aborted','child_precondition:'+refusal)
                self.moves += int(name == 'move')
                self.phase = name
            else:
                self.phase = 'settle'
        before = self.child.active
        decision = self.child.step(observation)
        if before is not None and self.child.active is None:
            event = dict(self.child.last_event)
            self.children.append(event)
            self.combat = event.get('combat') or self.combat
            if event['status'] != 'succeeded':
                return self.finish(observation,event['status'],'child:'+event['reason'])
            if event['skill'] == 'jab':
                self.ack_frame = event['ack_frame']
                return self.finish(observation,'succeeded','approach_and_jab_completed')
            self.phase = 'settle'
        if self.child.active and 'combat' in self.child.active:
            self.combat = self.child.active['combat'].trace()
            self.ack_frame = self.combat['ack_frame']
        self.last_action = decision.action
        return self.last_action

    def trace(self):
        return {'schema_version':1,'skill':'approach_jab','direction':self.direction,
            'phase':self.phase,'source_frame':self.started,'support':self.surface,
            'start_x':self.start_x,'movement_count':self.moves,'children':list(self.children),
            'active_child':self.child.trace()['active'],'combat':self.combat,
            'ack_frame':self.ack_frame,'end_frame':self.end_frame,'status':self.status,
            'reason':self.reason,'last_action':self.last_action,
            'limits':{'frames':MAX_FRAMES,'moves':MAX_MOVES,'displacement':MAX_DISPLACEMENT}}
