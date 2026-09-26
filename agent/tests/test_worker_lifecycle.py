"""Exercise the actual worker across an in-game frame reset, without a runtime."""

from enum import Enum
import json
from pathlib import Path
import signal
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from melee_agent import match_worker
from melee_agent.engine import BUTTONS
from test_match_lifecycle import replay
from test_matches import replay_fixture


class WorkerLifecycleTests(unittest.TestCase):
    def exercise(self, verified_start, menu_scene=None, *, scenario=False):
        buttons = Enum('Button',{ 'BUTTON_'+name:i for i,name in enumerate((*BUTTONS,'MAIN','C'))})
        characters = Enum('Character',{'FOX':1,'MARIO':0})
        stages = Enum('Stage',{'BATTLEFIELD':31})
        menus = Enum('Menu',{'IN_GAME':1,'SLIPPI_ONLINE_CSS':2,'POSTGAME_SCORES':3,'CHARACTER_SELECT':4,'UNKNOWN_MENU':5})
        sequence = iter([(-123,False),(28800,False),(-123,True),
            *([('menu',True)] if menu_scene is not None else []),(-122,True),(0,True),(None,True)])
        if scenario:
            sequence = iter([(-123,False),(0,False),(2,False),(3,False)])
        events = []

        class Console:
            def __init__(self,**kwargs):
                self.controllers = []
                self.eventsize = {0x38:0x4d,0x36:0xf0}
                self.zero_indices = {0:{14},1:{14}}
                self.slp_version_tuple = (3,18,0)
                self._Console__post_frame = lambda state,event:None
                self._Console__game_start = lambda state,event:None
                self._Console__handle_slippstream_menu_event = lambda event,state:None
            def connect(self): return True
            def stop(self): events.append('stopped')
            def step(self):
                frame,sudden = next(sequence)
                for controller in self.controllers:
                    controller.flush()
                if frame is None:
                    return NS(frame=0,menu_state=menus.CHARACTER_SELECT)
                if frame == 'menu':
                    self._Console__handle_slippstream_menu_event(b'\x3e'+struct.pack('>H',menu_scene),None)
                    return NS(frame=-123,menu_state=menus.UNKNOWN_MENU)
                if frame == -123 and (not sudden or verified_start):
                    header = bytearray(replay_fixture()[8:8+0xf0])
                    if sudden:
                        header[5] &= ~2
                        header[0x67] = header[0x8b] = 1
                    self._Console__game_start(None,header)
                players = {}
                for port in (1,2):
                    character = characters.FOX if port == 1 else characters.MARIO
                    stocks = (0 if frame == 0 and port == 1 else 1) if sudden else 4
                    percent = 300. if sudden else 0.
                    data = bytearray(0x4d)
                    data[0] = 0x38
                    struct.pack_into('>i',data,1,frame)
                    data[5:8] = bytes([port-1,0,character.value])
                    struct.pack_into('>H',data,8,14)
                    struct.pack_into('>f',data,0x16,percent)
                    data[0x21] = stocks
                    self._Console__post_frame(None,data)
                    players[port] = NS(character=character,cpu_level=0 if port == 1 else 3,
                        stock=stocks,percent=percent,position=NS(x=0.,y=0.),on_ground=True,jumps_left=2,
                        action=NS(value=14,name='STANDING'),action_frame=1,hitstun_frames_left=0,
                        hitlag_left=0,invulnerable=False,facing=True,speed_ground_x_self=0.,
                        speed_air_x_self=0.,speed_y_self=0.,speed_x_attack=0.,speed_y_attack=0.,
                        shield_strength=60.,controller_state=NS(main_stick=(.5,.5),c_stick=(.5,.5),
                            l_shoulder=0.,r_shoulder=0.,button={buttons['BUTTON_'+name]:False for name in BUTTONS}))
                return NS(frame=frame,players=players,stage=stages.BATTLEFIELD,is_teams=False,menu_state=menus.IN_GAME)

        class Controller:
            def __init__(self,console,port): console.controllers.append(self)
            def connect(self): pass
            def release_all(self): events.append('neutral')
            def flush(self): pass
            def disconnect(self): events.append('disconnected')
            def tilt_analog(self,*args): pass
            def press_shoulder(self,*args): pass
            def press_button(self,*args): pass

        run = Path(tempfile.mkdtemp(prefix='jev-worker-lifecycle-'))
        (run/'launch.json').write_text(json.dumps({'runtime':'fixture','port':51441,'run_id':'fixture',
            'policy':'scenario' if scenario else 'scripted','scenario_name':'offstage-left',
            'max_frame_bytes':1000000,'episodes':1}))
        fake = NS(Console=Console,Controller=Controller,Button=buttons,MenuHelper=lambda:None,
            Menu=menus,Character=characters,Stage=stages)
        previous = {s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
        try:
            with patch.dict('sys.modules',{'melee':fake}), patch.object(match_worker,'completed_replay',
                    side_effect=[replay(),replay(True)]):
                match_worker.run(run)
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)
        outcome = json.loads((run/'worker-result.json').read_text())
        rows = [json.loads(line) for line in (run/'frames.jsonl').read_text().splitlines()]
        self.assertTrue(outcome['neutralized'])
        self.assertEqual(events[-1],'stopped')
        self.assertEqual(outcome['recorder']['unwritten'],0)
        return outcome,rows

    def test_verified_reset_records_two_segments_and_one_final_match(self):
        outcome,rows = self.exercise(True)
        self.assertEqual(outcome['status'],'matches_complete')
        self.assertEqual(outcome['completed_matches'],1)
        self.assertEqual([r['episode'] for r in rows],[1,1,2,2,2])
        first,second = outcome['episodes']
        self.assertEqual((first['observations'],first['last_frame'],first['rollbacks']),(2,28800,0))
        self.assertIsNone(first['winner_port'])
        self.assertFalse(first['match_completed'])
        self.assertEqual((second['observations'],second['winner_port'],second['match_number']),(3,2,1))
        for row in rows[2:]:
            observation = row['control']['observation']
            self.assertIsNone(observation['match']['time_limit_seconds'])
            self.assertIsNone(observation['match']['remaining_seconds_derived'])
            self.assertEqual(observation['match']['starting_stocks'],1)
        self.assertEqual(rows[2]['control']['observation']['bot']['details']['life_generation_derived'],1)
        self.assertEqual(rows[2]['control']['packet']['main'],[.5,.5])

    def test_unverified_rollback_stops_without_counting_the_rejected_frame(self):
        outcome,rows = self.exercise(False)
        self.assertEqual(outcome['status'],'error')
        self.assertEqual(outcome['failure_reason'],'unverified_sudden_death_boundary')
        self.assertEqual(outcome['completed_matches'],0)
        self.assertEqual(len(rows),2)
        self.assertEqual(len(outcome['episodes']),1)
        self.assertEqual(outcome['episodes'][0]['observations'],2)
        self.assertEqual(outcome['episodes'][0]['last_frame'],28800)
        self.assertEqual(outcome['episodes'][0]['rollbacks'],0)

    def test_worker_records_release_observation_after_the_scenario_result(self):
        outcome,rows = self.exercise(True,scenario=True)
        self.assertEqual(outcome['status'],'scenario_complete')
        self.assertEqual([r['frame'] for r in rows],[-123,0,2,3])
        report = outcome['scenario']
        self.assertEqual(report['result']['status'],'setup_failed')
        self.assertEqual(report['result']['reason'],'observation_discontinuity')
        self.assertEqual(report['result']['end_frame'],2)
        self.assertEqual(report['terminal_release']['last_frame'],3)
        self.assertEqual(report['terminal_release']['status'],'observed')
        self.assertEqual(rows[-1]['control']['decision']['action'],'wait')

    def test_native_sudden_death_menu_preserves_segment_without_invoking_menu_helpers(self):
        outcome,rows = self.exercise(True,0x0302)
        self.assertEqual(outcome['status'],'matches_complete')
        self.assertEqual(outcome['completed_matches'],1)
        menu_rows = [r for r in rows if r['menu'] == 'UNKNOWN_MENU']
        self.assertEqual(len(menu_rows),1)
        self.assertEqual(menu_rows[0]['raw_menu']['scene'],0x0302)
        self.assertNotIn('control',menu_rows[0])
        self.assertEqual(outcome['episodes'][1]['observations'],3)
        self.assertEqual(outcome['episodes'][1]['last_frame'],0)

    def test_other_unknown_scene_still_fails_without_claiming_a_result(self):
        outcome,rows = self.exercise(True,0x0402)
        self.assertEqual(outcome['status'],'error')
        self.assertEqual(outcome['failure_reason'],'unverified_sudden_death_menu')
        self.assertEqual(outcome['completed_matches'],0)
