from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch

from melee_agent.aerial_audit import audit_aerial
from melee_agent.cli import main
from melee_agent.combat_evidence import audit_combat_trace
from melee_agent.corpus import generate_cases, compiler_hashes
from melee_agent.incidents import canonical, export_incident, replay_incident
from melee_agent.integrity import inspect_integrity
from melee_agent.live_control import observe
from melee_agent.match_lifecycle import record_observation, replay_layout_valid, start_segment
from melee_agent.matches import launch, supervise
from melee_agent.player_roles import raw_fighter, record_bot_port, validate_bot_port
from melee_agent.policy_evidence import inspect_policy
from melee_agent.replay import expected_settings
from test_aerial_audit import recorded_aerial
from test_combat_audit import evidence
from test_match_lifecycle import settings
import test_option_profile as option_fixtures
import test_worker_lifecycle as worker_fixtures


def swap_settings(original):
    value=deepcopy(original);a,b=value['players'][:2]
    value['players'][:2]=[{**b,'port':1},{**a,'port':2}]
    return value


def swap_rows(original):
    rows=deepcopy(original)
    for row in rows:
        row.update(schema_version=5,bot_port=2)
        players=row['raw_observation']['players']
        old_bot,old_opponent=players['1'],players.get('2',{'raw_post':{'action_id':14}})
        players['1'],players['2']=old_opponent,old_bot
        for port in ('1','2'):
            if 'port' in players[port]['raw_post']:
                players[port]['raw_post']['port']=int(port)
    return rows


class PlayerRolesTests(unittest.TestCase):
    def test_invalid_or_ambiguous_roles_refuse_before_any_launch_or_provider_preflight(self):
        for port in (True,False,0,3,1.,'2',None):
            with self.assertRaises(ValueError): validate_bot_port(port)
            with patch('melee_agent.matches.subprocess.Popen',side_effect=AssertionError('launch forbidden')):
                with self.assertRaises(ValueError): launch(Path('/tmp'),60,1,'jev',bot_port=port)
        for policy in ('scenario','skill-check','faults'):
            with patch('melee_agent.live_provider.preflight',side_effect=AssertionError('provider forbidden')):
                with self.assertRaises(ValueError): supervise(Path('/tmp'),60,1,policy,bot_port=2)
        for row in ({'schema_version':5}, {'schema_version':4,'bot_port':2},
                {'schema_version':5.,'bot_port':2}, {'schema_version':5,'bot_port':True}):
            with self.assertRaises(ValueError): record_bot_port(row)
        self.assertEqual(record_bot_port({'schema_version':4}),1)
        with self.assertRaises(ValueError): record_bot_port({'schema_version':5,'bot_port':2},1)

    def test_live_adapter_selects_asymmetric_stocks_actions_counters_and_inputs(self):
        def player(x,stocks,motion,pressed):
            return NS(position=NS(x=x,y=0.),on_ground=True,jumps_left=2,
                action=NS(value=motion,name='fixture'),action_frame=1,stock=stocks,
                percent=x+50.,facing=x>0,speed_ground_x_self=x/10,speed_air_x_self=0.,
                speed_y_self=0.,speed_x_attack=0.,speed_y_attack=0.,shield_strength=60.,
                controller_state=NS(button={},main_stick=(1. if pressed else .5,.5),
                    c_stick=(.5,.5),l_shoulder=0.,r_shoulder=0.))
        state=NS(stage=NS(name='BATTLEFIELD'),frame=60,players={1:player(-20.,3,179,True),2:player(10.,2,14,False)})
        raw={str(port):{'raw_post':{'state_flags_2':32 if port==1 else 0,'state_flags_4':0,
            'misc_as_raw':0.,'hitlag_raw':3.,'hurtbox_state':port-1,
            'available':{key:True for key in ('state_flags_2','state_flags_4','misc_as_raw','hitlag_raw','hurtbox_state')}}} for port in (1,2)}
        old=observe(state,1,NS(now_ns=lambda:100),raw)
        current=observe(state,1,NS(now_ns=lambda:100),raw,bot_port=2)
        self.assertEqual(current.bot,old.opponent)
        self.assertEqual(current.opponent,old.bot)
        self.assertEqual((current.bot.stocks_remaining,current.opponent.stocks_remaining),(2,3))
        self.assertEqual((current.bot.details.action_id,current.opponent.details.action_id),(14,179))
        self.assertTrue(current.bot.details.input_neutral_derived)
        self.assertFalse(current.opponent.details.input_neutral_derived)
        self.assertEqual((current.bot.details.hitlag_frames_derived,current.opponent.details.hitlag_frames_derived),(0,3))

    def test_replay_rules_and_native_winner_are_anchored_to_declared_side(self):
        native=swap_settings(settings())
        self.assertTrue(expected_settings(native,bot_port=2))
        self.assertFalse(expected_settings(native))
        segment=start_segment(1,1,'regulation',-123,0.,1,native,bot_port=2)
        record_observation(segment,100,[0,3],2.)
        segment.update(result_event_verified=True,match_completed=True,winner_port=1,replay_sha256='a'*64)
        replay={'settings':native,'outcome':'game','winner_port':1,'sha256':'a'*64}
        self.assertTrue(replay_layout_valid([segment],[replay],complete=True,expected_matches=1,bot_port=2))
        self.assertFalse(replay_layout_valid([segment],[replay],complete=True,expected_matches=1))
        self.assertFalse(replay_layout_valid([{**segment,'bot_port':1}],[replay],bot_port=2))
        self.assertFalse(replay_layout_valid([segment],[{**replay,'winner_port':2}],bot_port=2))

    def test_combat_and_aerial_audits_use_native_bot_port_not_port_one(self):
        report,rows=evidence();rows=swap_rows(rows);errors=Counter()
        result=audit_combat_trace('jab',report['skill']['event']['combat'],rows,errors,completed=True)
        self.assertTrue(result['completed']);self.assertFalse(errors)
        rows[1]['raw_observation']['players']['2']['raw_post']['action_id']=14
        rows[1]['raw_observation']['players']['1']['raw_post']['action_id']=44
        errors=Counter();audit_combat_trace('jab',report['skill']['event']['combat'],rows,errors,completed=True)
        self.assertIn('combat_motion_not_observed',errors)
        report,rows=recorded_aerial();rows=swap_rows(rows);errors=Counter()
        self.assertTrue(audit_aerial('sh_nair',report,rows,errors)['completed'])
        self.assertFalse(errors)
        self.assertEqual(raw_fighter(rows[4])['action_id'],65)
        self.assertEqual(raw_fighter(rows[4],opponent=True)['action_id'],14)

    def test_port_two_option_audit_and_sealed_replay_preserve_canonical_decisions(self):
        root,run,rows=option_fixtures.OptionProfileTests().fixture()
        for name in ('launch.json','summary.json'):
            path=run/name;value=json.loads(path.read_text());value['bot_port']=2;path.write_bytes(canonical(value))
        rows=swap_rows(rows)
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        result=inspect_policy(run)
        self.assertEqual(result['status'],'pass',result)
        self.assertEqual(result['acknowledgements']['observed:approach_jab'],1)
        exported=export_incident(root,run,episode=1,frame=42,after_frames=0)
        folder=root/'build/jev/incidents'/exported['incident_id']
        self.assertEqual(json.loads((folder/'manifest.json').read_text())['declared_provenance']['bot_port'],2)
        self.assertEqual(replay_incident(root,folder)['status'],'pass')
        rows[0].pop('bot_port')
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        with self.assertRaises(ValueError): inspect_policy(run)
        with self.assertRaises(ValueError): export_incident(root,run,episode=1,frame=42,after_frames=0)

    def test_native_role_integrity_rejects_swapped_normalized_actor_and_provenance(self):
        fixture=worker_fixtures.WorkerLifecycleTests();outcome,rows=fixture.exercise(True,bot_port=2)
        run=fixture.last_run
        (run/'summary.json').write_text(json.dumps({**outcome,'bot_port':2,'elapsed_seconds':1.}))
        self.assertEqual(inspect_integrity(run)['status'],'pass')
        for mutate in (lambda r:r['control']['observation']['bot'].update(x=-20.),
                lambda r:r['players']['2'].update(observed_main=[1.,.5])):
            changed=deepcopy(rows);mutate(changed[0])
            (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in changed))
            self.assertEqual(inspect_integrity(run)['status'],'fail')
        rows[0].pop('bot_port')
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        with self.assertRaises(ValueError): inspect_integrity(run)

    def test_cli_and_supervisor_command_keep_explicit_bot_port(self):
        with patch('melee_agent.matches.launch',return_value=0) as call:
            self.assertEqual(main(['match','--policy','random-tactical','--bot-port','2']),0)
        self.assertEqual(call.call_args.kwargs['bot_port'],2)
        child=MagicMock();child.wait.return_value=0
        with patch('melee_agent.matches.subprocess.Popen',return_value=child) as spawn:
            self.assertEqual(launch(Path('/tmp'),60,1,'random-tactical',bot_port=2),0)
        self.assertEqual(spawn.call_args.args[0][-1],'2')
        self.assertNotIn('OPENROUTER_API_KEY',spawn.call_args.kwargs['env'])

    def test_corpus_records_actual_side_without_changing_canonical_policy_state(self):
        root,run,rows=option_fixtures.OptionProfileTests().fixture()
        summary=json.loads((run/'summary.json').read_text());summary['policy']='delayed-fake'
        (run/'summary.json').write_bytes(canonical(summary))
        with patch('melee_agent.corpus.locate_run',return_value=run):
            original=list(generate_cases(root,['synthetic'],10,profile='approach-jab-v1'))
        summary['bot_port']=2
        (run/'summary.json').write_bytes(canonical(summary))
        rows=swap_rows(rows)
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        with patch('melee_agent.corpus.locate_run',return_value=run):
            mirrored=list(generate_cases(root,['synthetic'],10,profile='approach-jab-v1'))
        self.assertEqual([r['state'] for r in mirrored],[r['state'] for r in original])
        self.assertTrue(all(r['source']['bot_port']==2 for r in mirrored))
        self.assertIn('player_roles.py',compiler_hashes())
        rows[0]['bot_port']=1
        (run/'frames.jsonl').write_bytes(b''.join(canonical(row)+b'\n' for row in rows))
        with patch('melee_agent.corpus.locate_run',return_value=run),self.assertRaises(ValueError):
            list(generate_cases(root,['synthetic'],10,profile='approach-jab-v1'))


if __name__ == '__main__':
    unittest.main()
