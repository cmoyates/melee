from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from melee_agent.async_policy import AsyncPolicy, Delivery, LABELS, Reply, bind, rejection
from melee_agent.budget import SpendLedger
from melee_agent.cli import main
from melee_agent.engine import ACTION_PACKETS, FrameExecutor
from melee_agent.fake import RecordingSink
from melee_agent.incidents import RecordedClock, canonical, contract_hashes, export_incident, replay_incident, sha
from melee_agent.live_provider import DESCRIPTIONS, ProviderBackend
from melee_agent.policy_evidence import inspect_policy
from melee_agent.provider import VERIFIED_MODEL
from melee_agent.semantic import compact_observation
from test_async_policy import ManualBridge
from test_combat_integration import ground


class GroundedTacticsTests(unittest.TestCase):
    def fixture(self, name='jab', interrupted=False):
        bridge, clock = ManualBridge(), RecordedClock()
        now = [0]
        policy = AsyncPolicy('synthetic', bridge, clock=lambda: now[0]+1000)
        executor = FrameExecutor(policy, RecordingSink(), clock)
        rows = []
        motion = {'jab': 44, 'dtilt': 57, 'grab': 212}[name]
        source = None
        for frame in range(8):
            now[0] = 1_000_000_000+frame*16_666_667
            action = motion if frame in (5, 6) else 15 if frame in (1, 2) else 14
            if frame == 6 and interrupted:
                action = 79
            elif frame == 6 and name == 'grab':
                action = 216
            observation = replace(ground(frame, action,
                hitstun_frames_derived=14 if frame == 6 and interrupted else 0,
                self_velocity_x=1. if frame in (1, 2) else 0.,
                input_neutral_derived=frame not in (1, 2, 5)), observed_ns=now[0])
            observation = replace(observation, bot=replace(observation.bot, x=0. if frame == 0 else 1. if frame == 1 else 6.))
            if frame == 6 and name == 'grab' and not interrupted:
                observation = replace(observation, opponent=replace(observation.opponent,
                    details=replace(observation.opponent.details, action_id=223)))
            if frame == 4:
                candidates = tuple(rows[3]['skill']['semantic_state']['mechanical']['legal_candidates'])
                context = bind('synthetic', source, 1, rows[3]['skill']['generation'], candidates,
                    sha(rows[3]['skill']['semantic_state']))
                bridge.replies = [Delivery(context, candidates, Reply(context, name, now[0]-1))]
            clock.values = [now[0]+500, now[0]+2000]
            control = executor.step(observation)
            players = {}
            for port, fighter in (('1', observation.bot), ('2', observation.opponent)):
                players[port] = {'raw_post': {'action_id': fighter.details.action_id, 'x': fighter.x,
                    'y': fighter.y, 'airborne': int(not fighter.grounded), 'percent': fighter.details.percent,
                    'hurtbox_state': fighter.details.hurtbox_state, 'state_flags_2': 0,
                    'state_flags_4': 0, 'hitlag_raw': 0., 'misc_as_raw': 0.,
                    'available': {key: True for key in ('hurtbox_state','state_flags_2','state_flags_4','hitlag_raw','misc_as_raw')}}}
            rows.append({'schema_version': 4, 'run_id': 'synthetic', 'menu': 'IN_GAME',
                'episode': observation.episode, 'frame': frame, 'control': control, 'skill': policy.trace(),
                'raw_observation': {'players': players}, 'input_provenance': {
                    'observed': ACTION_PACKETS['wait'].wire(), 'latest_completed_flush': None}})
            if frame == 3:
                source = observation
        summary = {'schema_version': 1, 'run_id': 'synthetic', 'status': 'captured', 'episodes': [],
            'async_policy': {'policy': dict(policy.counts), 'bridge': {
                'workers_alive': 0, 'inflight': 0, 'worker_limit': 1}}}
        return rows, summary

    def save(self, rows, summary):
        root = Path(tempfile.mkdtemp(prefix='jev-grounded-tactics-')).resolve()
        run = root/'build/jev/runs/synthetic'
        run.mkdir(parents=True)
        launch = {'run_id': 'synthetic', 'policy': 'delayed-fake', 'synthetic_fixture': True,
            'stage_id': 31, 'starting_stocks': 4, 'match_time_limit_seconds': 480,
            'source_sha256': contract_hashes()}
        (run/'launch.json').write_bytes(canonical(launch))
        (run/'summary.json').write_bytes(canonical(summary))
        (run/'frames.jsonl').write_bytes(b''.join(canonical(r)+b'\n' for r in rows))
        return root, run

    def audit(self, rows, summary):
        return inspect_policy(self.save(rows, summary)[1])

    def test_accepted_attacks_have_native_acknowledgement_and_exact_incident_replay(self):
        self.assertEqual(tuple(DESCRIPTIONS), LABELS)
        for name in ('jab', 'dtilt', 'grab'):
            rows, summary = self.fixture(name)
            root, run = self.save(rows, summary)
            report = inspect_policy(run)
            self.assertEqual(report['status'], 'pass', report)
            self.assertEqual(report['combat_outcomes']['motion_started:'+name], 1)
            self.assertEqual(report['combat_outcomes']['completed:'+name], 1)
            self.assertEqual(report['combat_outcomes']['captures:'+name], int(name == 'grab'))
            self.assertEqual(report['acknowledgements']['observed:'+name], 1)
            with patch('socket.socket', side_effect=AssertionError('network forbidden')), \
                    patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
                exported = export_incident(root, run, frame=7, after_frames=0)
                replay = replay_incident(root, root/'build/jev/incidents'/exported['incident_id'])
            self.assertEqual(replay['status'], 'pass', replay)
            self.assertEqual(replay['replayed_records'], 8)

    def test_interrupted_native_start_is_separate_from_completion(self):
        rows, summary = self.fixture(interrupted=True)
        report = self.audit(rows, summary)
        self.assertEqual(report['status'], 'pass', report)
        self.assertEqual(report['combat_outcomes']['motion_started:jab'], 1)
        self.assertEqual(report['combat_outcomes']['completed:jab'], 0)
        self.assertEqual(report['acknowledgements'], {'aborted': 1})

    def test_claimed_attack_success_requires_press_native_motion_and_observed_release(self):
        rows, summary = self.fixture()
        for variant in range(3):
            changed = deepcopy(rows)
            if variant == 0:
                changed[4]['control']['packet'] = ACTION_PACKETS['wait'].wire()
            elif variant == 1:
                changed[5]['raw_observation']['players']['1']['raw_post']['action_id'] = 14
            else:
                changed[7]['input_provenance']['observed']['buttons']['A'] = True
            self.assertEqual(self.audit(changed, summary)['status'], 'fail')

    def test_capture_requires_both_fighters_and_cannot_be_inferred_from_grab_choice(self):
        rows, summary = self.fixture('grab')
        rows[6]['raw_observation']['players']['2']['raw_post']['action_id'] = 14
        report = self.audit(rows, summary)
        self.assertIn('combat_capture_not_observed', report['errors'])
        self.assertEqual(report['combat_outcomes']['captures:grab'], 0)

    def test_malformed_primitive_report_is_an_audit_failure(self):
        rows, summary = self.fixture()
        rows[-1]['skill']['transitions'][-1]['combat'] = 'invalid'
        report = self.audit(rows, summary)
        self.assertEqual(report['status'], 'fail')
        self.assertIn('combat_event_schema', report['errors'])

    def test_reply_attack_is_rechecked_for_range_invulnerability_and_unsupported_label(self):
        source = ground()
        candidates = tuple(DESCRIPTIONS)
        context = bind('test', source, 1, 0, candidates)
        delivery = Delivery(context, candidates, Reply(context, 'jab', source.observed_ns+1))
        current = replace(ground(1), opponent=replace(source.opponent, x=30.))
        self.assertEqual(rejection(delivery, current, 'test', 0, 0, 1_100_000_000, False), 'illegal_now:out_of_range')
        current = replace(ground(1), opponent=replace(source.opponent,
            details=replace(source.opponent.details, hurtbox_state=2)))
        self.assertEqual(rejection(delivery, current, 'test', 0, 0, 1_100_000_000, False),
            'illegal_now:opponent_invulnerable_or_unknown')
        self.assertEqual(rejection(replace(delivery, reply=replace(delivery.reply, action='sh_nair')),
            ground(1), 'test', 0, 0, 1_100_000_000, False), 'invalid_candidate')

    def test_provider_transmits_only_the_bound_combat_candidates(self):
        root = Path(tempfile.mkdtemp(prefix='jev-grounded-provider-')).resolve()
        SpendLedger.create(root, 'build/jev/budget', deadline_utc=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        observation = replace(ground(), observed_ns=time.monotonic_ns())
        labels = ('neutral', 'jab', 'dtilt', 'grab')
        semantic = compact_observation(observation, labels)
        context = bind('test', observation, 1, 0, labels, semantic.sha256)
        def transport(payload, timeout):
            request = json.loads(payload)
            self.assertEqual(tuple(request['questions']['action']['criteria']), labels)
            self.assertEqual(request['state'], semantic.wire())
            return 200, {}, json.dumps({'model': VERIFIED_MODEL, 'provider': 'TypeSafe', 'answers': {
                'action': {'type': 'choice', 'choice': 'jab', 'probabilities': {label: int(label == 'jab') for label in labels}}},
                'usage': {'cost': .00001, 'input_tokens': 100, 'output_tokens': 10}}).encode()
        backend = ProviderBackend(root, 'build/jev/budget', 1, time.monotonic_ns()+10_000_000_000, transport=transport)
        try:
            reply = backend.call(observation, context, labels, threading.Event(), semantic=semantic)[0]
            self.assertEqual(reply.action, 'jab')
            self.assertEqual(reply.metadata['semantic_sha256'], semantic.sha256)
        finally:
            self.assertEqual(backend.close()['http_calls'], 1)

    def test_full_match_cli_forwards_explicit_paid_bounds(self):
        with patch('melee_agent.matches.launch', return_value=0) as launch:
            self.assertEqual(main(['match', '--policy', 'jev', '--duration', '540', '--episodes', '1',
                '--budget', 'build/jev/existing', '--max-requests', '60']), 0)
        self.assertEqual(launch.call_args.args[1:], (540, 1, 'jev'))
        self.assertEqual(launch.call_args.kwargs, {'budget_directory': 'build/jev/existing', 'max_requests': 60})
