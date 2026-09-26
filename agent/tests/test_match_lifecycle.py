from dataclasses import replace
import unittest

from melee_agent.async_policy import Delivery, Reply, bind, rejection
from melee_agent.engine import MatchProgress, ScriptedPolicy
from melee_agent.match_lifecycle import (MatchBoundaryError, record_observation,
    replay_layout_valid, start_segment, verify_sudden_death)
from melee_agent.replay import game_settings, summarize_raw
from melee_agent.semantic import compact_observation
from test_combat_integration import ground
from test_matches import replay_fixture


def settings(sudden=False):
    event = bytearray(replay_fixture()[8:8+0xf0])
    if sudden:
        event[5] &= ~2
        event[0x67] = event[0x8b] = 1
    return game_settings(event)


def replay(sudden=False):
    result = summarize_raw(replay_fixture(method=2 if sudden else 1))
    result.update(settings=settings(sudden),sha256=('b' if sudden else 'a')*64)
    return result


class MatchLifecycleTests(unittest.TestCase):
    def previous(self):
        segment = start_segment(1,1,'regulation',-123,0.,1,settings())
        record_observation(segment,28800,[4,4],480.)
        return segment

    def test_only_verified_time_to_native_sudden_death_resets_the_frame_context(self):
        prior = self.previous()
        verify_sudden_death(prior,replay(),settings(True),-123,[1,1],[300.,300.],2)
        variants = [dict(frame=0),dict(stocks=[1,4]),dict(percents=[0.,300.]),
            dict(start_index=1),dict(settings=settings()),dict(replay={**replay(),'outcome':'unknown'}),
            dict(previous={**prior,'last_stocks':[3,4]}),dict(previous={**prior,'last_frame':28799})]
        arguments = dict(previous=prior,replay=replay(),settings=settings(True),frame=-123,
            stocks=[1,1],percents=[300.,300.],start_index=2)
        for changes in variants:
            with self.assertRaises(MatchBoundaryError):
                verify_sudden_death(**{**arguments,**changes})
        self.assertEqual(prior['observations'],1)
        self.assertEqual(prior['last_frame'],28800)

    def test_start_requires_real_rules_and_new_game_start_identity(self):
        for changes in ({'stage_id':32},{'timer_enabled':True},{'items':2}):
            with self.assertRaises(MatchBoundaryError):
                start_segment(2,1,'sudden_death',-123,481.,2,{**settings(True),**changes})
        for field,value in (('stocks',4),('character_external',8),('type',1)):
            invalid = settings(True)
            invalid['players'][0][field] = value
            with self.assertRaises(MatchBoundaryError):
                start_segment(2,1,'sudden_death',-123,481.,2,invalid)

    def test_two_segments_are_one_completed_match_and_time_placement_is_not_final(self):
        first, second = replay(),replay(True)
        a = {**self.previous(),'result_event_verified':True,'continued_as_sudden_death':True,
            'match_completed':False,'winner_port':None,'replay_sha256':first['sha256']}
        b = start_segment(2,1,'sudden_death',-123,481.,2,settings(True))
        record_observation(b,60,[0,1],485.)
        self.assertTrue(replay_layout_valid([a,b],[first,{**second,'outcome':'unknown'}]))
        self.assertFalse(replay_layout_valid([a,b],[first,second],complete=True,expected_matches=1))
        b.update(result_event_verified=True,match_completed=True,winner_port=2,replay_sha256=second['sha256'])
        self.assertTrue(replay_layout_valid([a,b],[first,second],complete=True,expected_matches=1))
        self.assertFalse(replay_layout_valid([a,b],[first,second],complete=True,expected_matches=2))
        for changed in ({**a,'winner_port':1},{**a,'match_completed':True},{**a,'continued_as_sudden_death':False}):
            self.assertFalse(replay_layout_valid([changed,b],[first,second],complete=True,expected_matches=1))
        self.assertFalse(replay_layout_valid([a,{**b,'match_number':2}],[first,second],complete=True,expected_matches=1))
        self.assertFalse(replay_layout_valid([a],[first]))

    def test_untimed_state_has_no_fake_countdown_and_old_responses_cannot_cross(self):
        old = ground()
        sudden = replace(old,schema_version=5,episode=2,frame=-123,
            bot=replace(old.bot,stocks_remaining=1),opponent=replace(old.opponent,stocks_remaining=1),
            match=MatchProgress.from_frame(-123,None,1))
        payload = compact_observation(sudden,()).wire()
        self.assertEqual(payload['kind'],'CompactObservationV2')
        self.assertEqual(payload['match']['phase'],'sudden_death')
        self.assertEqual(payload['match']['elapsed_scope'],'current_segment')
        self.assertFalse(payload['match']['timer_enabled'])
        self.assertIsNone(payload['match']['time_limit_seconds'])
        self.assertIsNone(payload['match']['remaining_seconds_estimated'])
        with self.assertRaises(ValueError):
            replace(sudden,schema_version=4)
        context = bind('fixture',old,1,0,('neutral','approach'))
        delivery = Delivery(context,('neutral','approach'),Reply(context,'approach',old.observed_ns))
        self.assertEqual(rejection(delivery,sudden,'fixture',0,0,old.observed_ns,False),'wrong_episode')

    def test_neutral_probe_never_moves_even_offstage_or_in_sudden_death(self):
        policy = ScriptedPolicy('neutral-probe')
        for frame in (-123,0,480,28800):
            state = ground(frame)
            for x,y in ((0,0),(-90,-30),(90,20)):
                sample = replace(state,bot=replace(state.bot,x=x,y=y))
                self.assertEqual(policy.decide(sample).action,'wait')
            sudden = replace(state,schema_version=5,match=MatchProgress.from_frame(frame,None,4))
            self.assertEqual(policy.decide(sudden).action,'wait')
