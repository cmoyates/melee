"""One settled main-floor full jump to a fixed Battlefield side platform."""

from .stage import PLATFORMS, support_surface

MAX_FRAMES = 90
TAKEOFF_FRAMES = 8


def target_platform(direction):
    if type(direction) is not int or direction not in (-1,1):
        raise ValueError('Invalid platform side')
    return next(p for p in PLATFORMS if p['id']==('left' if direction<0 else 'right'))


def can_start_platform_jump(direction,observation):
    try:
        target=target_platform(direction)
    except ValueError:
        return 'unknown_platform_side'
    a,d=observation.bot,observation.bot.details
    if observation.frame<0 or not a.stocks_remaining or d.action_id<=13:
        return 'inactive'
    if d.hitlag_frames_derived or d.hitstun_frames_derived:
        return 'own_damage_or_hitlag'
    if support_surface(a.x,a.y,a.grounded)!='ground' or d.action_id!=14:
        return 'requires_standing_main_floor'
    if not target['left']+8<=a.x<=target['right']-8:
        return 'outside_platform_launch_corridor'
    if abs(d.self_velocity_x)>=.05:
        return 'requires_settled_ground'
    if a.jumps!=2 or d.input_jump_held or not d.input_neutral_derived:
        return 'requires_fresh_ground_jump'
    return None


class PlatformJump:
    def __init__(self,direction,observation):
        from .skills import SkillArbiter
        reason=can_start_platform_jump(direction,observation)
        if reason:
            raise ValueError(reason)
        self.direction,self.target=direction,dict(target_platform(direction))
        self.started,self.start_x,self.start_y=observation.frame,observation.bot.x,observation.bot.y
        self.identity=(observation.episode,observation.bot.details.life_generation_derived)
        self.child=SkillArbiter()
        self.child_started=False
        self.children=[]
        self.previous_frame=self.knee_frame=self.ack_frame=self.landing_frame=self.end_frame=None
        self.takeoff_velocity_y=None
        self.peak_height=0.
        self.phase='jump'
        self.status=self.reason=None
        self.last_action='wait'

    def finish(self,observation,status,reason):
        if self.child.active is not None:
            self.child.abort(observation,reason)
            self.children.append(dict(self.child.last_event))
        self.status,self.reason,self.end_frame=status,reason,observation.frame
        self.phase,self.last_action='finished','wait'
        return 'wait'

    def step(self,observation):
        from .skills import SkillSpec
        a,d,frame=observation.bot,observation.bot.details,observation.frame
        if self.status is not None:
            return 'wait'
        if (observation.episode,d.life_generation_derived)!=self.identity or not a.stocks_remaining or d.action_id<=13:
            return self.finish(observation,'aborted','life_or_episode_changed')
        if self.previous_frame is not None and frame!=self.previous_frame+1:
            return self.finish(observation,'aborted','observation_discontinuity')
        self.previous_frame=frame
        if d.hitlag_frames_derived or d.hitstun_frames_derived:
            return self.finish(observation,'aborted','own_damage_or_hitlag')
        if frame-self.started>=MAX_FRAMES:
            return self.finish(observation,'timeout','platform_completion_deadline')
        if (abs(a.x-self.start_x)>2 or not self.target['left']+4<=a.x<=self.target['right']-4 or
                a.y < -12 or a.y > self.target['height']+20):
            return self.finish(observation,'aborted','unsupported_transfer_geometry')
        self.peak_height=max(self.peak_height,a.y-self.start_y)
        if not self.child_started:
            reason=can_start_platform_jump(self.direction,observation)
            if reason:
                return self.finish(observation,'aborted','prepress:'+reason)
            reason=self.child.request(SkillSpec('jump'),observation)
            if reason:
                return self.finish(observation,'aborted','child_precondition:'+reason)
            self.child_started=True
        elif self.ack_frame is None:
            if frame-self.started>=TAKEOFF_FRAMES:
                return self.finish(observation,'timeout','takeoff_not_observed')
            if a.grounded and d.action_id==24:
                if not d.input_jump_held:
                    return self.finish(observation,'aborted','jump_released_before_takeoff')
                if self.knee_frame is None:self.knee_frame=frame
            elif not a.grounded:
                if self.knee_frame is None or d.action_id not in (25,26) or a.jumps!=1 or d.self_velocity_y<=0:
                    return self.finish(observation,'aborted','unconfirmed_full_jump')
                self.ack_frame,self.takeoff_velocity_y=frame,d.self_velocity_y
                self.phase='airborne_release'
            elif d.action_id!=14:
                return self.finish(observation,'aborted','unexpected_jumpsquat_motion')
        if self.ack_frame is not None:
            if a.grounded:
                if support_surface(a.x,a.y,True)!=self.target['id']:
                    return self.finish(observation,'aborted','wrong_landing_surface')
                if a.jumps!=2 or d.action_id not in (14,42):
                    return self.finish(observation,'aborted','unexpected_platform_landing')
                if self.landing_frame is None:self.landing_frame=frame
                self.phase='landing_release'
                if d.action_id==14 and d.input_neutral_derived and frame>self.landing_frame and self.child.active is None:
                    return self.finish(observation,'succeeded','target_platform_and_neutral_observed')
            elif a.jumps!=1 or d.action_id not in (25,26,29,30,31):
                return self.finish(observation,'aborted','unexpected_transfer_motion_or_resource')
        action='wait'
        if self.child.active is not None:
            action=self.child.step(observation).action
            if self.child.active is None:
                event=dict(self.child.last_event);self.children.append(event)
                if event['status']!='succeeded':
                    return self.finish(observation,event['status'],'child:'+event['reason'])
        self.last_action=action
        return action

    def trace(self):
        return {'schema_version':1,'skill':'platform_jump','direction':self.direction,
            'target':self.target['id'],'source_frame':self.started,'start_x':self.start_x,
            'phase':self.phase,'knee_frame':self.knee_frame,'ack_frame':self.ack_frame,
            'takeoff_velocity_y':self.takeoff_velocity_y,'peak_height':self.peak_height,
            'landing_frame':self.landing_frame,'end_frame':self.end_frame,'status':self.status,
            'reason':self.reason,'last_action':self.last_action,'children':list(self.children),
            'active_child':self.child.trace()['active'],
            'limits':{'frames':MAX_FRAMES,'takeoff_frames':TAKEOFF_FRAMES,'horizontal_drift':2}}
