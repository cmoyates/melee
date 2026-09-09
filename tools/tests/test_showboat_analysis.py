#!/usr/bin/env python3
"""Synthetic SBREC-only tests; no captured match logs, emulator, or native build.

Run: python3 -m unittest discover -s tools/tests -p test_showboat_analysis.py
"""

from dataclasses import replace
import io
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import tracemalloc
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import analyze_showboat as analysis  # noqa: E402


LABELS = analysis.Labels(ROOT)


def base(kind, frame=100, segment=1, slot=1, **extra):
    return dict(v=1, type=kind, segment=segment, slot=slot, frame=frame, **extra)


def begin(frame=100, segment=1, slot=1, **extra):
    row = base('begin', frame, segment, slot, stage=31, mode=2, match_kind=1,
               target=0, interval=12)
    row.update(extra)
    return row


def fighter(spawn=10, kind=2, motion=14, percent=0, stocks=4, flags=0):
    return [spawn, kind, motion, 14, 0, 1, 0, 0, 0, percent, stocks, 60, flags]


def sample(frame=100, segment=1, slot=1, **extra):
    row = base('sample', frame, segment, slot, ego=50, action=0, owns=0,
               events=0, gap=0, self=fighter(), rival=fighter(spawn=20, kind=1),
               native=[1, 0, 0], input=[0, 0, 0, 0, 0, 0, 0])
    row.update(extra)
    return row


def gate(frame=112, segment=1, slot=1, tactic=0, reason=0, count=13, start=100, **extra):
    return base('gate', frame, segment, slot, tactic=tactic, reason=reason,
                count=count, **{'from': start}, **extra)


def flush(frame=112, start=100, count=13, **extra):
    return [gate(frame=frame, start=start, count=count, tactic=t, **extra) for t in range(5)]


def end(frame=112, segment=1, slot=1, observations=13, reason='suspend', **extra):
    return base('end', frame, segment, slot, observations=observations, reason=reason, **extra)


def complete(segment=1, slot=1, frame=100):
    return [begin(frame, segment, slot), sample(frame, segment, slot),
            sample(frame + 12, segment, slot)] + [
                gate(frame + 12, segment, slot, tactic=t, count=13, start=frame)
                for t in range(5)] + [end(frame + 12, segment, slot)]


def v2(rows):
    """Synthetic wire encoder; actual native-writer seam is tested separately."""
    result = []
    for source in rows:
        if not isinstance(source, dict) or source.get('v') == 2:
            result.append(source)
            continue
        row = dict(source, v=2)
        if row['type'] == 'sample':
            row['float_encoding'] = analysis.FLOAT_ENCODING
            for side in ('self', 'rival'):
                row[side] = list(row[side])
                for index in analysis.FLOAT_INDICES:
                    row[side][index] = struct.pack('>f', row[side][index]).hex()
        result.append(row)
    return result


def encoded(rows, prefix='00:00:01.000 Dolphin OSREPORT: '):
    return ''.join(prefix + 'SBREC ' + json.dumps(row) + '\n' if isinstance(row, dict)
                   else row for row in rows).encode('utf-8')


def analyze(rows, **kwargs):
    return analysis.analyze_stream(io.BytesIO(encoded(rows)), labels=LABELS, **kwargs)


def analyze_v2(rows, **kwargs):
    """Behavior fixtures exercise native v2 wire encoding, not legacy salvage."""
    return analyze(v2(rows), **kwargs)


def first(rows, **kwargs):
    return analyze_v2(rows, **kwargs)['segments'][0]


def assert_quarantined(test, seg):
    """All trusted sample fields must be absent/empty/unknown, never plausible totals."""
    test.assertEqual(seg['integrity']['sample_derived_statistics'], 'quarantined')
    test.assertEqual(seg['sample_quarantine']['status'], 'quarantined_not_for_statistics')
    for key in ('first_record_frame', 'last_record_frame',
                'continuity_supported_observations_lower_bound',
                'known_continuous_frames', 'explicit_gap_samples'):
        test.assertIsNone(seg['coverage'][key], key)
    for key in ('ego_range', 'owns_sample_count', 'timeline_omitted'):
        test.assertIsNone(seg[key], key)
    for key in ('native_priorities', 'custom_intents', 'acknowledgment_and_event_samples',
                'recovery_motion_context_samples'):
        test.assertEqual(seg[key], {}, key)
    for side in ('self', 'rival'):
        test.assertEqual(seg['motions'][side], {})
        test.assertEqual(seg['fighter_flag_samples'][side], {})
        test.assertIsNone(seg['position_ranges_at_samples'][side])
        test.assertTrue(all(v is None for v in seg['observed_changes'][side].values()))
    test.assertEqual(seg['timeline'], [])
    for row in seg['sample_quarantine']['diagnostic_raw_timeline']:
        test.assertEqual(row['type'], 'sample')
        test.assertIsInstance(row['self'], list)
        test.assertNotIn('continuous_from_previous', row)
        test.assertNotIn('reason_labels', row)


class ParsingTests(unittest.TestCase):
    def test_dolphin_prefix_and_exact_v1_shapes(self):
        report = analyze(['unrelated startup\n'] + complete())
        seg = report['segments'][0]
        self.assertEqual(report['scan']['accepted_records'], 9)
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(seg['coverage']['status'], 'legacy_transport_unvalidated')
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        self.assertEqual(seg['coverage']['recorder_reported_observations'], 13)
        self.assertEqual(seg['warnings']['counts'], {analysis.LEGACY_WARNING: 1})
        assert_quarantined(self, seg)
        raw = seg['sample_quarantine']['diagnostic_raw_timeline'][0]
        self.assertEqual(len(raw['input']), 7)
        self.assertEqual(len(raw['native']), 3)

    def test_unprefixed_and_varied_transport(self):
        for prefix in ('', '[CPU 1] ', '12:13:14.567 OSReport: ', 'Dolphin:'):
            with self.subTest(prefix=prefix):
                report = analysis.analyze_stream(io.BytesIO(encoded(complete(), prefix)), labels=LABELS)
                self.assertEqual(report['scan']['accepted_records'], 9)
        self.assertEqual(analyze(['NOT_SBREC {}\n'])['scan']['accepted_records'], 0)

    def test_all_array_lengths_and_numeric_types(self):
        for field, size in (('self', 13), ('rival', 13), ('native', 3), ('input', 7)):
            for bad in ([0] * (size - 1), [0] * (size + 1), 'not an array', [False] * size):
                with self.subTest(field=field, bad=bad):
                    report = analyze([begin(), sample(**{field: bad})])
                    self.assertEqual(report['scan']['rejected_records'], 1)
                    self.assertEqual(report['segments'][0]['coverage']['accepted_sample_records'], 0)

    def test_ids_reject_floats_strings_booleans_and_bounds(self):
        for field in ('v', 'segment', 'slot', 'frame', 'action', 'ego', 'gap', 'events'):
            for value in (True, '1', 1.0, 1.25, 2**32):
                with self.subTest(field=field, value=value):
                    report = analyze([sample(**{field: value})])
                    self.assertEqual(report['scan']['accepted_records'], 0)
        for field, indices in (('self', (0, 1, 2, 10, 12)), ('rival', (0, 1, 2, 10, 12)),
                               ('native', (0, 1, 2)), ('input', tuple(range(7)))):
            for index in indices:
                row = sample()
                row[field][index] = 1.0
                self.assertEqual(analyze([row])['scan']['accepted_records'], 0)

    def test_fractional_animation_frames_positions_percent_and_integer_channels(self):
        actor = fighter(percent=12.125)
        actor[3:9] = [3.25, -45.125, 1.5, -0.75, 1.25, 0.125]
        actor[11] = 54.5
        seg = first([begin(), sample(self=actor, input=[256, -127, 127, 0, 0, 80, 255])])
        self.assertEqual(seg['timeline'][0]['self']['anim'], 3.25)
        self.assertEqual(seg['timeline'][0]['self']['percent'], 12.125)
        self.assertEqual(seg['timeline'][0]['self']['shield'], 54.5)
        self.assertEqual(seg['timeline'][0]['input'], [256, -127, 127, 0, 0, 80, 255])

    def test_raw_axes_and_triggers_require_integer_native_bounds(self):
        valid = [0xFFFFFFFF, -128, 127, -128, 127, 0, 255]
        self.assertEqual(first([begin(), sample(input=valid)])['timeline'][0]['input'], valid)
        for index in range(1, 7):
            low, high = (-128, 127) if index < 5 else (0, 255)
            for value in (0.5, 0.0, True, '1', low - 1, high + 1):
                with self.subTest(index=index, value=value):
                    channels = valid.copy()
                    channels[index] = value
                    report = analyze([begin(), sample(input=channels)])
                    self.assertEqual(report['scan']['rejected_records'], 1)
                    self.assertEqual(report['segments'][0]['coverage']['accepted_sample_records'], 0)

    def test_full_finite_f32_text_range_and_signed_spawn(self):
        for maximum in (3.4028234663852886e38, 3.40282347e38, 3.4028235e38):
            actor = fighter(spawn=-0x80000000, percent=maximum)
            actor[3:9] = [maximum, -maximum, maximum, -maximum, maximum, -maximum]
            actor[11] = maximum
            report = analyze([begin(), sample(self=actor, rival=fighter(spawn=0x7FFFFFFF))])
            self.assertEqual(report['scan']['rejected_records'], 0)
            seg = report['segments'][0]
            assert_quarantined(self, seg)
            raw = seg['sample_quarantine']['diagnostic_raw_timeline'][0]
            self.assertEqual(raw['self'][0], -0x80000000)
            self.assertEqual(raw['rival'][0], 0x7FFFFFFF)
            self.assertEqual(raw['self'][4], -maximum)
            json.dumps(report, allow_nan=False)
        for spawn in (-0x80000001, 0x80000000, 0xFFFFFFFF, -1.0, True):
            for side in ('self', 'rival'):
                report = analyze([begin(), sample(**{side: fighter(spawn=spawn)})])
                self.assertEqual(report['scan']['rejected_records'], 1)

    def test_f32_overflow_rejected_even_in_ignored_fields(self):
        for value in (3.4028236e38, -3.4028236e38, 1e39, -1e100):
            row = sample()
            row['self'][4] = value
            for bad in (row, sample(ignored=value)):
                report = analyze([begin(), bad])
                self.assertEqual(report['scan']['rejected_records'], 1)
                self.assertIn('numeric_magnitude_limit', report['warnings']['counts'])

    def test_optional_sample_reason_shapes_and_types(self):
        for reasons in (None, 'active', {}, [0] * 4, [0] * 6,
                        [0, 0, 0, 0, True], [0, 0, 0, 0, 1.0],
                        [0, 0, 0, 0, -1], [0, 0, 0, 0, 2**32],
                        [0, 0, 0, 0, [1]]):
            with self.subTest(reasons=reasons):
                self.assertEqual(analyze([begin(), sample(reasons=reasons)])['scan']['rejected_records'], 1)
        report = analyze_v2([begin(), sample(reasons=[0, 3, 4, 15, 99])])
        self.assertEqual(report['scan']['rejected_records'], 0)
        seg = report['segments'][0]
        self.assertEqual(seg['timeline'][0]['reason_labels']['lcancel'], 'unknown_reason_99')
        self.assertIn('unknown_sample_reason_id', seg['warnings']['counts'])

    def test_optional_batch_requires_positive_uint(self):
        for batch in (None, 0, -1, True, 1.0, '1', [], {}, 2**32):
            with self.subTest(batch=batch):
                report = analyze([begin(), gate(batch=batch)])
                self.assertEqual(report['scan']['rejected_records'], 1)
        report = analyze([begin(), gate(batch=0xFFFFFFFF)])
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertIn('missing_gate_batches', report['segments'][0]['warnings']['counts'])

    def test_owns_boolean_and_integer_encodings(self):
        for owns in (True, False, 0, 1):
            self.assertEqual(first([begin(), sample(owns=owns)])['owns_sample_count'], int(owns))
        for owns in (2, 'true', 1.0, None):
            self.assertEqual(analyze([sample(owns=owns)])['scan']['rejected_records'], 1)

    def test_nonfinite_numbers_everywhere(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            for field in ('ego', 'frame', 'self'):
                row = sample()
                row[field] = '__BAD__' if field != 'self' else fighter(percent='__BAD__')
                text = json.dumps(row).replace('"__BAD__"', token)
                report = analyze(['SBREC ' + text + '\n'])
                self.assertEqual(report['scan']['accepted_records'], 0)
                self.assertIn('nonfinite_number', report['warnings']['counts'])

    def test_unknown_version_type_missing_field_and_truncated(self):
        rows = [dict(sample(), v=3), dict(sample(), type='result'),
                {key: val for key, val in sample().items() if key != 'rival'},
                'SBREC {"v":1,\n', 'SBREC \n']
        report = analyze(rows)
        self.assertEqual(report['scan']['rejected_records'], 5)
        self.assertIn('unknown_version', report['warnings']['counts'])
        self.assertIn('unknown_record_type', report['warnings']['counts'])
        self.assertIn('missing_fields', report['warnings']['counts'])
        self.assertIn('malformed_or_truncated_json', report['warnings']['counts'])

    def test_duplicate_json_keys_rejected_at_any_depth(self):
        for text in ('{"v":1,"v":1}', '{"a":{"x":1,"x":2}}'):
            report = analyze(['SBREC ' + text + '\n'])
            self.assertIn('duplicate_json_key', report['warnings']['counts'])
        raw = json.dumps(sample()).replace('"ego": 50', '"ego": 10, "ego": 90')
        self.assertEqual(analyze(['SBREC ' + raw + '\n'])['scan']['accepted_records'], 0)

    def test_huge_and_deep_fields_bounded(self):
        cases = [('"' + 'x' * 129 + '"', 'string_limit'),
                 ('12345678901234567890', 'integer_limit'),
                 ('1e100', 'numeric_magnitude_limit'),
                 ('[' * 9 + '0' + ']' * 9, 'json_depth_limit'),
                 (json.dumps([0] * 129), 'json_shape_limit'),
                 (json.dumps([[0] * 100] * 6), 'json_node_limit')]
        for text, code in cases:
            with self.subTest(code=code):
                report = analyze(['SBREC ' + text + '\n'])
                self.assertIn(code, report['warnings']['counts'])

    def test_invalid_utf8_and_unterminated_valid_record(self):
        report = analysis.analyze_stream(io.BytesIO(b'SBREC {"v": "\xff"}\n'), labels=LABELS)
        self.assertIn('invalid_utf8_record', report['warnings']['counts'])
        report = analysis.analyze_stream(io.BytesIO(encoded(complete()).rstrip(b'\n')), labels=LABELS)
        self.assertEqual(report['scan']['accepted_records'], 9)
        self.assertIn('unterminated_final_record_line', report['warnings']['counts'])

    def test_legacy_diagnostics_not_complete_statistics(self):
        report = analyze(['[OSReport] SHOWBOAT punch hits=999 wins=100\n',
                          'SHOWBOAT result: winner Falcon\n', 'other\n'])
        self.assertEqual(report['segments'], [])
        self.assertEqual(report['legacy']['logged_showboat_lines'], 2)
        self.assertEqual(report['legacy']['coverage'], 'unknown_not_complete')
        self.assertIn('no_structured_records_partial_legacy', report['warnings']['counts'])
        self.assertNotIn('hits=999', analysis.markdown(report))

    def test_forged_results_extra_fields_and_code_never_interpreted(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'executed'
            payload = "__import__('pathlib').Path(%r).touch()" % str(sentinel)
            rows = complete()
            rows[1]['result'] = {'winner': 'Falcon', 'damage': 9999}
            rows[-1].update(winner='Falcon', kills=999, result='victory')
            rows.append('SBREC ' + payload + '\n')
            report = analyze(rows)
            serialized = json.dumps(report)
            self.assertFalse(sentinel.exists())
            self.assertNotIn('Falcon', serialized)
            self.assertNotIn('victory', serialized)
            self.assertNotIn('9999', serialized)
            self.assertNotIn('winner', report['segments'][0])
            self.assertIn('unknown_fields_ignored_not_outcome_evidence', report['warnings']['counts'])
            self.assertIn('Sample summaries withheld', analysis.markdown(report))


class ProtocolV2Tests(unittest.TestCase):
    def test_exact_v2_shapes_normalize_to_same_numeric_analysis(self):
        rows = complete()
        rows[1]['reasons'] = [0, 3, 4, 15, 13]
        for row in rows:
            if row['type'] == 'gate':
                row['batch'] = 1
        legacy = analyze(rows)['segments'][0]
        assert_quarantined(self, legacy)
        wire = v2(rows)
        original = json.dumps(wire)
        report = analyze(wire)
        seg = report['segments'][0]
        self.assertEqual(report['analysis_schema'], 2)
        self.assertEqual(report['scan']['accepted_records'], 9)
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(seg['protocol_version'], 2)
        self.assertEqual(seg['coverage']['status'], 'count_consistent_recording')
        self.assertEqual(report['integrity']['status'], 'validated_v2_records_not_runtime_verified')
        self.assertFalse(report['warnings']['counts'])
        self.assertFalse(seg['warnings']['counts'])
        for source, record in zip(rows, wire):
            old, _ = analysis.validate(source)
            current, _ = analysis.validate(record)
            self.assertEqual({k: v for k, v in old.items() if k != 'v'},
                             {k: v for k, v in current.items() if k not in ('v', 'float_encoding')})
        self.assertEqual(seg['gates'], legacy['gates'])
        self.assertEqual(seg['coverage']['known_continuous_frames'], 12)
        self.assertEqual(seg['observed_changes']['self']['comparable_percent_pairs'], 1)
        self.assertEqual(seg['position_ranges_at_samples']['self']['x'], [0, 0])
        self.assertEqual(seg['motions']['self']['2:14:ftCo_MS_Wait']['known_frames'], 12)
        normalized, extras = analysis.validate(wire[1])
        self.assertFalse(extras)
        for side in ('self', 'rival'):
            self.assertEqual(len(normalized[side]), 13)
            for i, value in enumerate(normalized[side]):
                self.assertIs(type(value), float if i in analysis.FLOAT_INDICES else int)
        self.assertEqual(json.dumps(wire), original, 'validation must not mutate the wire record')
        self.assertNotIn('PROVISIONAL', analysis.markdown(report))

    def test_binary32_exact_bits_all_fields_both_fighters_and_signed_spawn(self):
        row = v2([sample()])[0]
        # -0, smallest/largest subnormal, smallest normal, both finite extrema,
        # adjacent-to-1 normal, negative subnormal; percent stays nonnegative.
        bits = ['80000000', '00000001', '007fffff', '00800000',
                '7f7fffff', 'ff7fffff', '3f800001', '80000001']
        for side, spawn in (('self', -0x80000000), ('rival', 0x7FFFFFFF)):
            row[side][0] = spawn
            for index, value in zip(analysis.FLOAT_INDICES, bits):
                row[side][index] = value
        normalized, _ = analysis.validate(row)
        for side in ('self', 'rival'):
            for index, value in zip(analysis.FLOAT_INDICES, bits):
                self.assertEqual(struct.pack('>f', normalized[side][index]).hex(), value)
        report = analyze(v2([begin()]) + [row])
        snap = report['segments'][0]['timeline'][0]
        self.assertEqual(snap['self']['spawn'], -0x80000000)
        self.assertEqual(snap['rival']['spawn'], 0x7FFFFFFF)
        self.assertEqual(math.copysign(1, snap['self']['anim']), -1)
        self.assertEqual(snap['self']['x'], 2**-149)
        self.assertEqual(snap['self']['ground_v'], -(2 - 2**-23) * 2**127)
        self.assertIn('-0.0', json.dumps(report, allow_nan=False))
        # Negative zero is also legal in the percent position; negative nonzero isn't.
        row['self'][9] = '80000000'
        self.assertEqual(math.copysign(1, analysis.validate(row)[0]['self'][9]), -1)
        row['self'][9] = '80000001'
        with self.assertRaisesRegex(analysis.Invalid, 'negative_percent'):
            analysis.validate(row)

    def test_exact_hex_not_decimal_uppercase_whitespace_prefix_or_code(self):
        bad_values = [0, 0.0, True, None, [], {}, '', '0', '0000000', '000000000',
                      '0x00000000', 'DEADBEEF', '3f80000A', ' 00000000', '00000000\n',
                      '00 00 00 00', 'gggggggg', '１２３４５６７８', "__import__('os')"]
        for side in ('self', 'rival'):
            for index in analysis.FLOAT_INDICES:
                for value in bad_values:
                    with self.subTest(side=side, index=index, value=value):
                        row = v2([sample()])[0]
                        row[side][index] = value
                        report = analyze(v2([begin()]) + [row])
                        self.assertEqual(report['scan']['rejected_records'], 1)
                        self.assertIn('invalid_binary32_hex', report['warnings']['counts'])
                        self.assertEqual(report['segments'][0]['timeline'], [])

    def test_nonfinite_bit_patterns_rejected_in_every_float_position(self):
        for bits in ('7f800000', 'ff800000', '7fc00000', 'ffc00000', '7f800001', 'ffffffff'):
            for side in ('self', 'rival'):
                for index in analysis.FLOAT_INDICES:
                    row = v2([sample()])[0]
                    row[side][index] = bits
                    with self.subTest(bits=bits, side=side, index=index):
                        report = analyze([row])
                        self.assertEqual(report['scan']['accepted_records'], 0)
                        self.assertIn('nonfinite_binary32', report['warnings']['counts'])
                        json.dumps(report, allow_nan=False)

    def test_float_encoding_required_exact_and_only_v2_samples(self):
        good = v2([sample()])[0]
        missing = {k: v for k, v in good.items() if k != 'float_encoding'}
        self.assertIn('missing_fields', analyze([missing])['warnings']['counts'])
        for encoding in (None, True, 2, [], {}, '', 'IEEE754-binary32-hex', 'ieee754-binary64-hex'):
            self.assertIn('invalid_float_encoding',
                          analyze([dict(good, float_encoding=encoding)])['warnings']['counts'])
        for row in [sample()] + [begin(), gate(), end()] + v2([begin(), gate(), end()]):
            row['float_encoding'] = analysis.FLOAT_ENCODING
            self.assertIn('invalid_float_encoding', analyze([row])['warnings']['counts'])
        # No implicit upgrade/downgrade based on token shape.
        self.assertIn('invalid_finite_number',
                      analyze([dict(missing, v=1)])['warnings']['counts'])
        self.assertIn('invalid_binary32_hex',
                      analyze([dict(sample(), v=2, float_encoding=analysis.FLOAT_ENCODING)])['warnings']['counts'])

    def test_v2_array_shapes_and_integer_positions_remain_strict(self):
        for field, size in (('self', 13), ('rival', 13), ('native', 3), ('input', 7)):
            for value in (None, {}, 'array', [0] * (size - 1), [0] * (size + 1)):
                row = v2([sample()])[0]
                row[field] = value
                self.assertIn('invalid_array_shape', analyze([row])['warnings']['counts'])
        for side in ('self', 'rival'):
            for index in (0, 1, 2, 10, 12):
                for value in ('00000000', 0.0, True, None):
                    row = v2([sample()])[0]
                    row[side][index] = value
                    self.assertEqual(analyze([row])['scan']['accepted_records'], 0)

    def test_mixed_versions_reject_every_record_kind_and_break_bridge(self):
        for version in (1, 2):
            convert = v2 if version == 2 else list
            other = list if version == 2 else v2
            for alien in (begin(101), sample(101), gate(101, count=1), end(101, observations=1)):
                with self.subTest(version=version, kind=alien['type']):
                    rows = convert([begin(), sample()]) + other([alien]) + convert([sample(112)])
                    report = analyze(rows)
                    seg = report['segments'][0]
                    self.assertEqual(report['scan']['rejected_records'], 1)
                    assert_quarantined(self, seg)
                    self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
                    self.assertIn('mixed_record_versions_in_segment', seg['warnings']['counts'])
                    self.assertEqual(seg['integrity']['status'], 'corrupted_or_unreliable')
                    self.assertEqual(report['integrity']['status'], 'corrupted_or_unreliable')

    def test_version_is_segment_local_and_first_orphan_record_establishes_it(self):
        report = analyze(complete() + v2(complete(segment=2, frame=1)))
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual([s['protocol_version'] for s in report['segments']], [1, 2])
        self.assertEqual(report['integrity']['sample_derived_statistics'],
                         'mixed_v1_quarantined_v2_available_with_coverage_caveats')
        assert_quarantined(self, report['segments'][0])
        current = report['segments'][1]
        self.assertIsNone(current['sample_quarantine'])
        self.assertEqual(current['coverage']['known_continuous_frames'], 12)
        text = analysis.markdown(report)
        old_text, current_text = text.split('## Segment 2')
        self.assertIn('Sample summaries withheld', old_text)
        self.assertNotIn('Native priority known frames:', old_text)
        self.assertIn('Native priority known frames:', current_text)
        selected = analyze(complete() + v2(complete(segment=2, frame=1)), segment=2)
        self.assertIsNone(selected['segments'][0]['sample_quarantine'])
        self.assertIn('Native priority known frames:', analysis.markdown(selected))
        self.assertEqual(report['integrity']['status'], 'legacy_transport_unvalidated')
        report = analyze(v2([sample()]) + [sample(112)])
        self.assertEqual(report['scan']['rejected_records'], 1)
        self.assertEqual(report['segments'][0]['coverage']['accepted_sample_records'], 1)
        self.assertIn('missing_begin', report['segments'][0]['warnings']['counts'])

    def test_source_backed_fighter_bounds_both_versions(self):
        bounds = {0: (-0x80000000, 0x7FFFFFFF), 1: (0, 32), 2: (-1, 543),
                  10: (-128, 127), 12: (0, 255)}
        for convert in (list, v2):
            for side in ('self', 'rival'):
                for index, (low, high) in bounds.items():
                    for value in (low, high, low - 1, high + 1):
                        row = sample()
                        row[side][index] = value
                        report = analyze(convert([begin(), row]))
                        with self.subTest(version=convert.__name__, side=side, index=index, value=value):
                            self.assertEqual(report['scan']['rejected_records'], int(value < low or value > high))
        # Motion 4 is a real death state. Constant rival motion 4 is suspicious
        # in the live reviews, but cannot on its own be rejected as impossible.
        report = analyze([begin(), sample(rival=fighter(motion=4))])
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(report['integrity']['sample_derived_statistics'], 'quarantined')

    def test_bounds_guard_actual_source_not_normal_match_stock_assumptions(self):
        kinds = analysis.read_enum((ROOT / 'src/melee/ft/forward.h').read_text(), 'FighterKind')
        self.assertEqual(analysis.FIGHTER_KIND_MAX, kinds['FTKIND_NONE'] - 1)
        common = analysis.read_enum((ROOT / 'src/melee/ft/kinds/ftCommon/forward.h').read_text(),
                                    'ftCommon_MotionState')
        self.assertEqual(common['ftCo_MS_None'], -1)
        kirby = analysis.read_enum((ROOT / 'src/melee/ft/kinds/ftKirby/forward.h').read_text(),
                                   'ftKirby_MotionState', common)
        self.assertEqual(analysis.MOTION_MAX, kirby['ftKb_MS_Count'] - 1)
        player = (ROOT / 'src/melee/pl/player.c').read_text()
        self.assertRegex(player, r's32 Player_GetStocks\(int slot\)\s*\{\s*s8 stocks;')
        self.assertIn('stocks = player->stocks;', player)
        self.assertEqual((analysis.STOCK_MIN, analysis.STOCK_MAX), (-128, 127))

    def test_live_fault_regression_rejects_impossible_flags_without_reconstructing(self):
        for convert in (list, v2):
            rows = complete()
            damaged = sample(106, self=fighter(percent=9999, flags=0x80000101),
                             rival=fighter(spawn=4, motion=4, stocks=100))
            rows.insert(2, damaged)
            report = analyze(convert(rows))
            seg = report['segments'][0]
            self.assertEqual(report['scan']['rejected_records'], 1)
            self.assertIn('invalid_fighter_flag_bits', report['warnings']['counts'])
            assert_quarantined(self, seg)
            self.assertEqual(seg['coverage']['status'], 'corrupted_or_unreliable')
            self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
            self.assertTrue(all(g['logged_updates'] == 13 for g in seg['gates']))
            text = analysis.markdown(report)
            self.assertIn('do not trust sample-derived totals', text)
            self.assertIn('Sample summaries withheld', text)
            self.assertNotIn('comparable net percent increases', text)
            self.assertNotIn('Native priority known frames:', text)
            self.assertNotIn('9999', json.dumps(report))

    def test_corrupt_v2_breaks_all_open_bridges_and_later_pairs_are_diagnostic_only(self):
        rows = v2([begin(), sample(), begin(segment=2, slot=2), sample(segment=2, slot=2)])
        bad = v2([sample(106)])[0]
        bad['rival'][11] = '7f800000'
        rows += [bad] + v2([sample(112), sample(113), sample(112, segment=2, slot=2),
                           sample(113, segment=2, slot=2)])
        report = analyze(rows)
        self.assertEqual(report['scan']['rejected_records'], 1)
        for seg in report['segments']:
            assert_quarantined(self, seg)
            self.assertEqual(seg['coverage']['accepted_sample_records'], 3)
            raw = seg['sample_quarantine']['diagnostic_raw_timeline']
            self.assertEqual([s['frame'] for s in raw], [100, 112, 113])
            self.assertIn('unreadable_or_rejected_record_continuity_unknown', seg['warnings']['counts'])
        # Preserve the continuity algorithm regression without publishing its
        # internal post-corruption calculations as trusted report metrics.
        internal = analysis.Segment(v2([begin()])[0], analysis.Limits(), LABELS, True)
        internal.accept(analysis.validate(v2([sample()])[0])[0], 1)
        internal.warn('unreadable_or_rejected_record_continuity_unknown', corrupt=True)
        for row in v2([sample(112), sample(113)]):
            internal.accept(analysis.validate(row)[0], 2)
        self.assertEqual(internal.known_frames, 1)
        self.assertFalse(internal.timeline[1]['continuous_from_previous'])
        self.assertTrue(internal.timeline[2]['continuous_from_previous'])
        assert_quarantined(self, internal.finish())

    def test_v2_duplicate_encoding_keys_and_forged_extras_never_change_protocol(self):
        row = v2([sample()])[0]
        raw = json.dumps(row).replace('"float_encoding":', '"float_encoding": "decimal", "float_encoding":')
        report = analyze(['SBREC ' + raw + '\n'])
        self.assertIn('duplicate_json_key', report['warnings']['counts'])
        rows = v2(complete())
        rows[1]['result'] = {'winner': 'FORGED_WINNER', 'damage': 987654}
        report = analyze(rows)
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertIn('unknown_fields_ignored_not_outcome_evidence', report['warnings']['counts'])
        self.assertNotIn('FORGED_WINNER', json.dumps(report) + analysis.markdown(report))
        self.assertNotIn('987654', json.dumps(report))

    def test_valid_looking_v1_is_always_quarantined_not_provisional(self):
        report = analyze(complete())
        seg = report['segments'][0]
        self.assertIn(analysis.LEGACY_WARNING, report['warnings']['counts'])
        self.assertIn(analysis.LEGACY_WARNING, seg['warnings']['counts'])
        assert_quarantined(self, seg)
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        self.assertTrue(all(g['logged_updates'] == 13 for g in seg['gates']))
        text = analysis.markdown(report)
        self.assertLess(text.index('QUARANTINED'), text.index('## Segment'))
        self.assertIn('even when fields look valid', text)
        self.assertNotIn('provisional', text.lower())
        self.assertIn('Sample summaries withheld', text)
        self.assertNotIn('Native priority known frames:', text)
        self.assertNotIn('count_consistent_recording', json.dumps(report))

    def test_rejected_orphan_and_filtered_out_corruption_cannot_hide_status(self):
        bad = v2([sample(segment=2, self=fighter(flags=256))])[0]
        report = analyze(v2(complete()) + [bad], segment=1)
        self.assertEqual(report['integrity']['scope'], 'entire_scanned_input')
        self.assertEqual(report['integrity']['status'], 'corrupted_or_unreliable')
        assert_quarantined(self, report['segments'][0])
        self.assertIn('Sample summaries withheld', analysis.markdown(report))
        empty = analyze([bad])
        self.assertEqual(empty['segments'], [])
        self.assertEqual(empty['integrity']['status'], 'corrupted_or_unreliable')
        json.dumps(empty, allow_nan=False)


class QuarantinePolicyTests(unittest.TestCase):
    def test_117_plausible_v1_rows_never_salvaged_by_filtering_with_7324_gates(self):
        rows = [begin()] + [sample(100 + i, ego=i, action=i, events=i,
                                  self=fighter(spawn=10 + i, kind=i % 33, motion=i - 1,
                                               percent=i * 10, stocks=i - 128, flags=i),
                                  rival=fighter(spawn=20, percent=i * 20, flags=255),
                                  native=[i, -i, i]) for i in range(117)]
        rows += flush(frame=216, count=7324, batch=1) + [end(216, observations=7324)]
        bad = sample(101, self=fighter(flags=256))
        damaged = rows[:2] + [bad] + rows[2:]
        filtered = []
        for row in damaged:
            try:
                analysis.validate(row)
            except analysis.Invalid:
                continue
            filtered.append(row)
        for data, rejected in ((rows, 0), (damaged, 1), (filtered, 0)):
            with self.subTest(rejected=rejected, filtered=data is filtered):
                report = analyze(data, limits=replace(analysis.Limits(), timeline=3))
                seg = report['segments'][0]
                self.assertEqual(report['scan']['accepted_records'], 124)
                self.assertEqual(report['scan']['rejected_records'], rejected)
                self.assertEqual(seg['coverage']['accepted_sample_records'], 117)
                assert_quarantined(self, seg)
                self.assertEqual(seg['coverage']['recorder_reported_observations'], 7324)
                self.assertTrue(all(g['logged_updates'] == 7324 for g in seg['gates']))
                self.assertTrue(all(g['missing_vs_reported_observations'] == 0 for g in seg['gates']))
                self.assertEqual(seg['context']['frame'], 100)
                self.assertEqual(seg['recording_end']['frame'], 216)
                quarantine = seg['sample_quarantine']
                self.assertIn('legacy_v1_native_caller_abi_stack_layout_mismatch', quarantine['reasons'])
                self.assertEqual(len(quarantine['diagnostic_raw_timeline']), 3)
                self.assertEqual(quarantine['diagnostic_raw_timeline_omitted'], 114)
                text = analysis.markdown(report)
                for summary in ('Sampled ego range:', 'Custom intent samples:',
                                'Acknowledgments/events (not hits):', 'comparable net percent increases',
                                'sampled positions:', 'Native priority known frames:', 'Timeline (first',
                                'motions (entries / boundary sightings / known frames)', 'PROVISIONAL'):
                    self.assertNotIn(summary, text)
                self.assertIn('| personality | 7324 |', text)
                json.dumps(report, allow_nan=False)

    def test_v1_never_computes_histograms_identities_or_duration_internally(self):
        internal = analysis.Segment(begin(), analysis.Limits(), LABELS, True)
        for row in (sample(), sample(112, self=fighter(percent=80, spawn=99, flags=255))):
            self.assertTrue(internal.accept(row, 1))
        self.assertEqual(internal.samples, 2)
        self.assertEqual(internal.known_frames, 0)
        self.assertEqual(internal.lower_bound, 0)
        self.assertIsNone(internal.ego)
        self.assertFalse(internal.bridge)
        self.assertEqual(internal.timeline, [])
        self.assertEqual(internal.priorities.rows, {})
        for side in ('self', 'rival'):
            self.assertEqual(internal.motions[side].rows, {})
            self.assertEqual(internal.flags[side], {})
            self.assertIsNone(internal.positions[side])
            self.assertEqual(internal.changes[side]['identity_changes'], 0)
        assert_quarantined(self, internal.finish())

    def test_quarantine_diagnostics_can_be_disabled_and_never_drive_gates(self):
        rows = complete()
        rows[1]['reasons'] = [3] * 5
        for convert in (list, v2):
            for cap in (0, 1):
                data = convert(rows)
                if convert is v2:
                    data.insert(2, 'SBREC {truncated\n')
                report = analyze(data, limits=replace(analysis.Limits(), timeline=cap, warnings=0))
                seg = report['segments'][0]
                assert_quarantined(self, seg)
                self.assertEqual(len(seg['sample_quarantine']['diagnostic_raw_timeline']), cap)
                self.assertEqual(seg['sample_quarantine']['diagnostic_raw_timeline_omitted'], 2 - cap)
                self.assertTrue(all(g['reasons'] == {'not_evaluated': 13} for g in seg['gates']))
                self.assertEqual(seg['warnings']['examples'], [])

    def test_v2_current_statistics_remain_available_with_missing_tail_and_gap_caveats(self):
        report = analyze_v2([begin(), sample(), sample(112, gap=1),
                             sample(113, self=fighter(percent=9))])
        seg = report['segments'][0]
        self.assertIsNone(seg['sample_quarantine'])
        self.assertEqual(seg['integrity']['sample_derived_statistics'], 'available_with_coverage_caveats')
        self.assertEqual(seg['coverage']['known_continuous_frames'], 1)
        self.assertEqual(seg['observed_changes']['self']['net_percent_increases'], 9)
        self.assertEqual(seg['native_priorities']['native_priority_1']['known_frames'], 1)
        self.assertEqual(seg['position_ranges_at_samples']['self']['x'], [0, 0])
        self.assertEqual(len(seg['timeline']), 3)
        text = analysis.markdown(report)
        self.assertIn('Native priority known frames:', text)
        self.assertIn('missing_end_eof_unflushed_gate_tail_unknown', text)
        self.assertNotIn('Sample summaries withheld', text)

    def test_corruption_outside_selection_quarantines_previously_closed_v2_segment(self):
        rows = v2(complete() + complete(segment=2, frame=1))
        rows[-2]['count'] = 0
        report = analyze(rows, segment=1)
        self.assertEqual(report['scan']['rejected_records'], 1)
        self.assertEqual(len(report['segments']), 1)
        seg = report['segments'][0]
        assert_quarantined(self, seg)
        self.assertEqual(seg['coverage']['status'], 'corrupted_or_unreliable')
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        self.assertTrue(all(g['logged_updates'] == 13 for g in seg['gates']))


class ContinuityTests(unittest.TestCase):
    def test_unchanged_periodic_twelve_is_known_time_not_twelve_samples(self):
        seg = first(complete())
        self.assertEqual(seg['coverage']['known_continuous_frames'], 12)
        self.assertEqual(seg['coverage']['continuity_supported_observations_lower_bound'], 13)
        self.assertEqual(seg['native_priorities']['native_priority_1']['known_frames'], 12)
        motion = seg['motions']['self']['2:14:ftCo_MS_Wait']
        self.assertEqual(motion['known_frames'], 12)
        self.assertEqual(motion['boundary_sightings'], 1)
        self.assertNotIn('entries', motion)
        self.assertEqual(motion['samples'], 2)

    def test_left_closed_durations_and_observed_state_entries(self):
        seg = first([begin(), sample(),
                     sample(106, self=fighter(motion=20), action=1, native=[9, 0, 0]),
                     sample(112, self=fighter(motion=20), action=1, native=[9, 0, 0])])
        self.assertEqual(seg['native_priorities']['native_priority_1']['known_frames'], 6)
        self.assertEqual(seg['native_priorities']['native_priority_9']['known_frames'], 6)
        self.assertEqual(seg['native_priorities']['native_priority_9']['entries'], 1)
        self.assertEqual(seg['motions']['self']['2:20:ftCo_MS_Dash']['entries'], 1)
        self.assertEqual(seg['custom_intents']['taunt']['entries'], 1)
        self.assertEqual(seg['custom_intents']['taunt']['samples'], 2)

    def test_gap_one_does_not_fill_even_adjacent_or_periodic_frames(self):
        for distance in (1, 12, 500):
            seg = first([begin(), sample(), sample(100 + distance, gap=1), sample(101 + distance)])
            self.assertEqual(seg['coverage']['known_continuous_frames'], 1)
            self.assertEqual(seg['coverage']['continuity_supported_observations_lower_bound'], 3)
            self.assertIn('explicit_frame_gap', seg['warnings']['counts'])
            self.assertFalse(seg['timeline'][1]['continuous_from_previous'])
            self.assertTrue(seg['timeline'][2]['continuous_from_previous'])

    def test_missing_periodic_samples_no_interpolation(self):
        seg = first([begin(), sample(), sample(113)])
        self.assertEqual(seg['coverage']['known_continuous_frames'], 0)
        self.assertIn('sample_interval_exceeded_missing_rows_or_gap', seg['warnings']['counts'])

    def test_malformed_line_breaks_continuity_for_all_open_slots(self):
        report = analyze_v2([begin(), sample(), begin(segment=2, slot=2), sample(segment=2, slot=2),
                             'SBREC {truncated\n', sample(112), sample(112, segment=2, slot=2)])
        for seg in report['segments']:
            assert_quarantined(self, seg)
            self.assertIn('unreadable_or_rejected_record_continuity_unknown', seg['warnings']['counts'])

    def test_new_segment_frame_rollback_is_independent(self):
        report = analyze_v2(complete() + complete(segment=2, frame=1))
        self.assertEqual(len(report['segments']), 2)
        for seg in report['segments']:
            self.assertEqual(seg['coverage']['known_continuous_frames'], 12)
            self.assertEqual(seg['warnings']['counts'], {})
        self.assertEqual(report['segments'][1]['timeline'][0]['frame'], 1)
        self.assertEqual(len(analyze(complete() + complete(2), segment=2)['segments']), 1)

    def test_in_segment_rollback_rejected_and_no_bridge(self):
        seg = first([begin(), sample(), sample(99, ego=100), sample(101)])
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        assert_quarantined(self, seg)
        self.assertEqual([r['ego'] for r in seg['sample_quarantine']['diagnostic_raw_timeline']], [50, 50])
        self.assertIn('frame_rollback_or_out_of_order_record', seg['warnings']['counts'])
        internal = analysis.Segment(v2([begin()])[0], analysis.Limits(), LABELS, True)
        accepted = [internal.accept(analysis.validate(r)[0], 1)
                    for r in v2([sample(), sample(99, ego=100), sample(101)])]
        self.assertEqual(accepted, [True, False, True])
        self.assertEqual(internal.known_frames, 0)
        self.assertEqual(internal.ego, [50, 50])

    def test_duplicate_samples_begin_and_after_end_do_not_count(self):
        rows = complete()
        rows.insert(2, sample(ego=99, events=2))
        rows.insert(1, begin())
        rows += [end(), sample(113)]
        report = analyze_v2(rows)
        seg = report['segments'][0]
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        assert_quarantined(self, seg)
        raw = seg['sample_quarantine']['diagnostic_raw_timeline']
        self.assertEqual([r['ego'] for r in raw], [50, 50])
        self.assertEqual([r['events'] for r in raw], [0, 0])
        self.assertEqual(report['scan']['rejected_records'], 4)
        for code in ('duplicate_sample_frame', 'duplicate_begin', 'record_after_end_or_duplicate_end'):
            self.assertIn(code, seg['warnings']['counts'])

    def test_monotonic_segment_ids_and_slot_identity(self):
        report = analyze(complete(segment=3) + [begin(segment=2), sample(113, segment=3, slot=2)])
        self.assertEqual(len(report['segments']), 1)
        self.assertIn('segment_id_not_monotonic', report['warnings']['counts'])
        self.assertIn('slot_identity_mismatch', report['segments'][0]['warnings']['counts'])

    def test_replaced_slot_cannot_resume_old_segment(self):
        report = analyze([begin(), sample(), begin(frame=1, segment=2), sample(1, segment=2), sample(101)])
        old = report['segments'][0]
        self.assertEqual(old['coverage']['accepted_sample_records'], 1)
        self.assertIn('new_segment_on_slot_without_end', old['warnings']['counts'])
        self.assertIn('record_after_slot_segment_replaced', old['warnings']['counts'])

    def test_missing_begin_end_samples_and_unobserved_tail(self):
        seg = first([sample()])
        self.assertIsNone(seg['context'])
        self.assertIsNone(seg['recording_end'])
        self.assertIsNone(seg['coverage']['recorder_reported_observations'])
        self.assertIsNone(seg['observed_changes']['self']['net_percent_increases'])
        self.assertIsNone(seg['gates'][0]['missing_vs_reported_observations'])
        self.assertIn('missing_begin', seg['warnings']['counts'])
        self.assertIn('missing_end_eof_unflushed_gate_tail_unknown', seg['warnings']['counts'])
        seg = first([begin(), end()])
        self.assertIsNone(seg['ego_range'])
        self.assertIn('missing_samples', seg['warnings']['counts'])
        seg = first([begin(), sample(103), end(110, observations=11)])
        self.assertEqual(seg['coverage']['known_continuous_frames'], 0)
        self.assertIn('missing_initial_sample', seg['warnings']['counts'])
        self.assertIn('unsampled_end_tail_duration_unknown', seg['warnings']['counts'])


class BehaviorTests(unittest.TestCase):
    def test_gates_each_actual_tactic_denominator_and_not_evaluated(self):
        rows = [begin(), sample(), sample(112)]
        rows += [gate(tactic=0, reason=0, count=10), gate(tactic=0, reason=8, count=3)]
        rows += [gate(tactic=1, reason=3), gate(tactic=2, reason=4),
                 gate(tactic=3, reason=15), gate(tactic=4, reason=13), end()]
        seg = first(rows)
        self.assertEqual(seg['warnings']['counts'], {})
        personality, combat, movement, defense, lcancel = seg['gates']
        self.assertEqual(personality['logged_updates'], 13)
        self.assertEqual(personality['not_evaluated'], 10)
        self.assertEqual(personality['evaluated_logged_updates'], 3)
        self.assertEqual(personality['rejected_logged_updates'], 3)
        self.assertEqual(movement['rejected_logged_updates'], 13)
        self.assertEqual(combat['rejected_logged_updates'], 0)
        self.assertEqual(defense['reasons'], {'success': 13})
        self.assertEqual(lcancel['reasons'], {'cancelled': 13})
        self.assertEqual(lcancel['rejected_logged_updates'], 0)

    def test_legacy_duplicate_overlapping_gates_and_invalid_counts(self):
        seg = first([begin(), sample(), sample(112), gate(), gate(),
                     gate(frame=113, count=2, start=112), end(113, observations=14)])
        self.assertEqual(seg['gates'][0]['logged_updates'], 13)
        self.assertEqual(seg['warnings']['counts']['duplicate_or_overlapping_gate_bin'], 2)
        for bad in (gate(count=0), gate(count=2**32), gate(start=113), gate(count=True), gate(tactic=1.0)):
            self.assertEqual(analyze([begin(), bad])['scan']['rejected_records'], 1)

    def test_count_coverage_missing_gates_and_forged_totals(self):
        for total in (1, 14, 999):
            rows = complete()
            rows[-1]['observations'] = total
            seg = first(rows)
            # Only totals below the supported lower bound are impossible. A
            # larger total may represent repeated-frame updates, but these gates
            # do not account for it, so count coverage still must be flagged.
            code = ('end_observation_count_inconsistent' if total == 1 else
                    'observations_not_fully_located_by_samples')
            self.assertIn(code, seg['warnings']['counts'])
            self.assertIn('gate_count_coverage_mismatch', seg['warnings']['counts'])
            self.assertEqual(seg['coverage']['status'], 'partial_or_inconsistent')
        seg = first([begin(), sample(), sample(112), gate(count=3), end()])
        self.assertEqual(seg['gates'][0]['missing_vs_reported_observations'], 10)
        self.assertIn('gate_tactic_totals_disagree', seg['warnings']['counts'])
        self.assertIn('missing_tactic_gate_coverage', seg['warnings']['counts'])
        seg = first([begin(), sample(), sample(112), gate(count=3)])
        self.assertIn('gate_coverage_short_of_known_observations', seg['warnings']['counts'])
        self.assertEqual(seg['coverage']['unflushed_gate_tail'], 'unknown')

    def test_multiple_gate_flushes_count_updates_without_sample_time_distortion(self):
        rows = [begin()] + [sample(f) for f in (100, 112, 124, 136, 148, 159)]
        rows += [gate(frame=159, tactic=t, count=60, start=100) for t in range(5)]
        rows += [sample(160), sample(170)]
        rows += [gate(frame=170, tactic=t, count=11, start=160) for t in range(5)]
        rows += [end(frame=170, observations=71)]
        seg = first(rows)
        self.assertEqual(seg['warnings']['counts'], {})
        self.assertEqual(seg['coverage']['known_continuous_frames'], 70)
        self.assertEqual(seg['coverage']['accepted_sample_records'], 8)
        for tactic in seg['gates']:
            self.assertEqual(tactic['logged_updates'], 71)
            self.assertEqual(tactic['not_evaluated'], 71)

    def test_repeated_frame_batches_end_totals_are_updates_not_frames(self):
        # 60 Begin->Frame updates on f100, another 60 on the same frame, then
        # f100..112 in a third flush. Only one sample may be emitted on f100.
        rows = [begin(), sample()] + flush(frame=100, start=100, count=60, batch=1)
        rows += flush(frame=100, start=100, count=60, batch=2)
        rows += [sample(112)] + flush(count=13, batch=3) + [end(observations=133)]
        report = analyze_v2(rows)
        seg = report['segments'][0]
        self.assertEqual(report['scan']['accepted_records'], 19)
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(seg['coverage']['status'], 'count_consistent_recording')
        self.assertEqual(seg['coverage']['recorder_reported_observations'], 133)
        self.assertEqual(seg['coverage']['accepted_sample_records'], 2)
        self.assertEqual(seg['coverage']['known_continuous_frames'], 12)
        self.assertEqual(seg['warnings']['counts'], {'observations_not_fully_located_by_samples': 1})
        for tactic in seg['gates']:
            self.assertEqual(tactic['logged_updates'], 133)
            self.assertEqual(tactic['missing_vs_reported_observations'], 0)
            self.assertEqual(tactic['coverage'], 'count_consistent_not_independently_verified')

    def test_shared_frame_boundary_between_distinct_batches(self):
        rows = [begin(), sample(), sample(112)] + flush(batch=1)
        rows += [sample(124)] + flush(frame=124, start=112, count=13, batch=2)
        rows += [end(124, observations=26)]
        report = analyze_v2(rows)
        seg = report['segments'][0]
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(seg['coverage']['known_continuous_frames'], 24)
        self.assertEqual(seg['gates'][0]['logged_updates'], 26)
        self.assertNotIn('gate_count_exceeds_frame_span', seg['warnings']['counts'])
        self.assertNotIn('end_observation_count_inconsistent', seg['warnings']['counts'])

    def test_duplicate_batch_rows_do_not_inflate_counts(self):
        rows = [begin(), sample()] + flush(frame=100, count=60, batch=1)
        rows += [gate(frame=100, count=99, batch=1)]  # Changed count still duplicate.
        rows += flush(frame=100, count=60, batch=2)
        rows += [gate(frame=100, count=60, batch=1)]  # Replay older batch.
        rows += [gate(frame=100, count=60, batch=2)]
        rows += [end(100, observations=120)]
        report = analyze(rows)
        seg = report['segments'][0]
        self.assertEqual(report['scan']['rejected_records'], 3)
        self.assertEqual(seg['warnings']['counts']['duplicate_gate_batch_bin'], 2)
        self.assertIn('gate_batch_not_monotonic', seg['warnings']['counts'])
        self.assertTrue(all(t['logged_updates'] == 120 for t in seg['gates']))

    def test_batch_bounds_must_match_and_flushes_cannot_cross(self):
        for bad, code in ((gate(start=101, tactic=1, batch=1), 'gate_batch_bounds_mismatch'),
                          (gate(frame=113, tactic=1, batch=1), 'gate_batch_bounds_mismatch'),
                          (gate(frame=113, start=111, tactic=1, batch=2),
                           'crossing_or_nonmonotonic_gate_bounds'),
                          (gate(frame=111, start=100, tactic=1, batch=2),
                           'frame_rollback_or_out_of_order_record')):
            with self.subTest(bad=bad):
                report = analyze([begin(), sample(), gate(batch=1), bad])
                self.assertEqual(report['scan']['rejected_records'], 1)
                seg = report['segments'][0]
                self.assertIn(code, seg['warnings']['counts'])
                self.assertEqual(seg['gates'][1]['logged_updates'], 0)

    def test_legacy_crossing_ranges_rejected_even_for_different_keys(self):
        report = analyze([begin(), sample(), gate(), gate(frame=113, start=111, tactic=1)])
        self.assertEqual(report['scan']['rejected_records'], 1)
        self.assertIn('crossing_or_nonmonotonic_gate_bounds', report['segments'][0]['warnings']['counts'])

    def test_missing_batches_warn_but_later_counts_retained(self):
        rows = [begin(), sample()] + flush(frame=100, count=60, batch=2)
        rows += flush(frame=100, count=60, batch=4) + [end(100, observations=240)]
        report = analyze(rows)
        seg = report['segments'][0]
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(seg['warnings']['counts']['missing_gate_batches'], 2)
        self.assertEqual(seg['gates'][0]['logged_updates'], 120)
        self.assertEqual(seg['gates'][0]['missing_vs_reported_observations'], 120)
        self.assertEqual(seg['coverage']['status'], 'partial_or_inconsistent')

    def test_batch_ids_restart_per_segment_and_allow_interleaved_slots(self):
        rows = [begin(), sample(), begin(segment=2, slot=2), sample(segment=2, slot=2)]
        for tactic in range(5):
            rows += [gate(tactic=tactic, batch=1), gate(segment=2, slot=2, tactic=tactic, batch=1)]
        rows += [end(), end(segment=2, slot=2)]
        report = analyze_v2(rows)
        self.assertEqual(report['scan']['rejected_records'], 0)
        for seg in report['segments']:
            self.assertTrue(all(t['logged_updates'] == 13 for t in seg['gates']))
            self.assertNotIn('missing_gate_batches', seg['warnings']['counts'])
            self.assertIn('unsampled_end_tail_duration_unknown', seg['warnings']['counts'])
            self.assertIn('observations_not_fully_located_by_samples', seg['warnings']['counts'])
            self.assertEqual(seg['coverage']['status'], 'count_consistent_recording')
            self.assertEqual(seg['coverage']['known_continuous_frames'], 0)

    def test_legacy_and_batch_encoding_cannot_double_count_one_segment(self):
        for left, right in ((gate(), gate(batch=1)), (gate(batch=1), gate())):
            report = analyze([begin(), sample(), left, right])
            self.assertEqual(report['scan']['rejected_records'], 1)
            self.assertEqual(report['segments'][0]['gates'][0]['logged_updates'], 13)
            self.assertIn('mixed_gate_batch_encoding', report['segments'][0]['warnings']['counts'])

    def test_legacy_repeated_updates_allowed_but_duplicate_flushes_ambiguous(self):
        rows = [begin(), sample()] + flush(frame=100, count=60)
        report = analyze(rows + [end(100, observations=60)])
        self.assertEqual(report['scan']['rejected_records'], 0)
        self.assertEqual(report['segments'][0]['coverage']['status'], 'legacy_transport_unvalidated')
        report = analyze(rows + flush(frame=100, count=60) + [end(100, observations=120)])
        self.assertEqual(report['scan']['rejected_records'], 5)
        self.assertTrue(all(t['logged_updates'] == 60 for t in report['segments'][0]['gates']))

    def test_batch_tactic_inconsistency_cannot_hide_in_balanced_segment_totals(self):
        rows = [begin(), sample()]
        for batch in (1, 2):
            rows += [gate(frame=100, tactic=t, count=(2 if (t == 0) == (batch == 1) else 1), batch=batch)
                     for t in range(5)]
        rows += [end(100, observations=3)]
        seg = first(rows)
        self.assertTrue(all(t['logged_updates'] == 3 for t in seg['gates']))
        self.assertEqual(seg['warnings']['counts']['gate_batch_tactic_totals_disagree'], 2)
        self.assertEqual(seg['coverage']['status'], 'partial_or_inconsistent')

    def test_optional_reasons_are_only_bounded_sample_context_not_gate_counts(self):
        rows = complete()
        before = first(rows)
        rows[1]['reasons'] = [0, 3, 4, 15, 13]
        rows[2]['reasons'] = [1, 2, 6, 9, 0]
        report = analyze_v2(rows)
        seg = report['segments'][0]
        self.assertEqual(seg['warnings']['counts'], {})
        self.assertNotIn('unknown_fields_ignored_not_outcome_evidence', report['warnings']['counts'])
        self.assertEqual(seg['gates'], before['gates'])
        self.assertEqual(seg['coverage'], before['coverage'])
        self.assertEqual([s['frame'] for s in seg['timeline']], [100, 112])
        self.assertEqual(seg['timeline'][0]['reasons'], [0, 3, 4, 15, 13])
        self.assertEqual(seg['timeline'][0]['reason_labels']['combat'], 'started')
        self.assertEqual(seg['timeline'][1]['reason_labels']['combat'], 'active')
        self.assertNotIn('reason_labels', before['timeline'][0])
        self.assertIn('at this sampled update only', analysis.markdown(report))
        self.assertIn('Reason changes do not trigger samples', analysis.markdown(report))
        limited = first(rows, limits=replace(analysis.Limits(), timeline=1))
        self.assertEqual(len(limited['timeline']), 1)
        self.assertEqual(limited['timeline_omitted'], 1)
        self.assertEqual(limited['gates'], before['gates'])
        no_gates = first([begin(), sample(reasons=[3] * 5), sample(112, reasons=[3] * 5)])
        self.assertTrue(all(t['logged_updates'] == 0 for t in no_gates['gates']))

    def test_end_token_cannot_become_a_match_result(self):
        rows = complete()
        rows[-1]['reason'] = 'win'
        report = analyze(rows)
        seg = report['segments'][0]
        self.assertEqual(seg['recording_end']['lifecycle_reason_token'], 'win')
        self.assertNotIn('result', seg)
        self.assertNotIn('winner', seg)
        self.assertIn('recording event `win`, not a win', analysis.markdown(report))

    def test_unknown_gate_ids_are_not_rejected_or_known_evaluated(self):
        seg = first([begin(), sample(), gate(frame=100, count=1, tactic=99, reason=99)])
        gate_report = seg['gates'][-1]
        self.assertEqual(gate_report['label'], 'unknown_tactic_99')
        self.assertEqual(gate_report['reasons'], {'unknown_reason_99': 1})
        self.assertEqual(gate_report['unknown_reason_updates'], 1)
        self.assertEqual(gate_report['rejected_logged_updates'], 0)
        self.assertEqual(gate_report['evaluated_logged_updates'], 0)
        self.assertIn('unknown_gate_id', seg['warnings']['counts'])

    def test_net_percent_changes_exclude_stock_spawn_and_percent_resets(self):
        rows = [begin()]
        cases = [(10, 4, 10), (20, 4, 10), (0, 4, 10), (5, 3, 10),
                 (8, 3, 10), (500, 3, 11), (503, 3, 11)]
        for i, (percent, stocks, spawn) in enumerate(cases):
            rows.append(sample(100 + i, self=fighter(spawn=spawn, percent=percent, stocks=stocks)))
        seg = first(rows)
        stats = seg['observed_changes']['self']
        self.assertEqual(stats['net_percent_increases'], 16)
        self.assertEqual(stats['comparable_percent_pairs'], 3)
        self.assertEqual(stats['percent_decreases_excluded'], 1)
        self.assertEqual(stats['reset_pairs_excluded'], 1)
        self.assertEqual(stats['unknown_pairs_excluded'], 1)
        self.assertEqual(stats['identity_changes'], 1)
        self.assertEqual(stats['stock_decreases'], 1)
        self.assertNotIn('hits', stats)
        self.assertNotIn('kills', stats)
        self.assertIn('identity_changed_without_new_segment', seg['warnings']['counts'])

    def test_time_match_zero_stocks_still_have_comparable_percent_changes(self):
        seg = first([begin(match_kind=0),
                     sample(self=fighter(stocks=0, percent=10),
                            rival=fighter(spawn=20, kind=1, stocks=0, percent=7)),
                     sample(101, self=fighter(stocks=0, percent=14.5),
                            rival=fighter(spawn=20, kind=1, stocks=0, percent=19))])
        for side, increase in (("self", 4.5), ("rival", 12)):
            stats = seg["observed_changes"][side]
            self.assertEqual(stats["net_percent_increases"], increase)
            self.assertEqual(stats["comparable_percent_pairs"], 1)
            self.assertEqual(stats["stock_decreases"], 0)
            self.assertNotIn("hits", stats)
            self.assertNotIn("kills", stats)

    def test_kind_rival_identity_gap_inactive_and_unknown_stocks_exclude_damage(self):
        for change in ({'self': fighter(kind=25, percent=500)},
                       {'self': fighter(percent=500), 'rival': fighter(spawn=999, kind=1)},
                       {'self': fighter(percent=500), 'gap': 1},
                       {'self': fighter(percent=500, flags=8)},
                       {'self': fighter(percent=500, stocks=-1)}):
            seg = first([begin(), sample(), sample(101, **change)])
            self.assertIsNone(seg['observed_changes']['self']['net_percent_increases'])

    def test_all_event_masks_through_255_keep_existing_labels_and_add_veto(self):
        expected = {1: 'taunt_ack', 2: 'punch_ack', 4: 'grab_ack', 8: 'aerial_ack',
                    16: 'wavedash_landing_ack', 32: 'custom_powershield_contact',
                    64: 'lcancel_sample', 128: 'side_b_veto'}
        self.assertEqual(analysis.EVENTS, expected)
        self.assertEqual(analysis.EVENT_MASK, 255)
        for mask in range(256):
            with self.subTest(mask=mask):
                rows = complete()
                rows[1]['events'] = mask
                report = analyze_v2(rows)
                seg = report['segments'][0]
                labels = [name for bit, name in expected.items() if mask & bit]
                self.assertEqual(report['scan']['rejected_records'], 0)
                self.assertEqual(seg['protocol_version'], 2)
                self.assertIsNone(seg['sample_quarantine'])
                self.assertEqual(seg['warnings']['counts'], {})
                self.assertEqual(seg['acknowledgment_and_event_samples'],
                                 {name: 1 for name in labels})
                self.assertEqual(seg['timeline'][0]['events_mask'], mask)
                self.assertEqual(seg['timeline'][0]['events'], labels)
                self.assertEqual(seg['timeline'][1]['events'], [])
                self.assertEqual(seg['coverage']['known_continuous_frames'], 12)

    def test_unknown_higher_event_bits_still_warn_without_becoming_veto(self):
        # Retain the analyzer's diagnostic policy for unknown in-range u32
        # bits; the producer masks these and strict wire readers reject them.
        for high in (256, 512, 0x80000000, 0xFFFFFF00):
            for known in (0, 128, 255):
                with self.subTest(high=high, known=known):
                    rows = complete()
                    rows[1]['events'] = high | known
                    seg = first(rows)
                    self.assertEqual(seg['warnings']['counts'], {'unknown_event_bits': 1})
                    self.assertEqual(seg['acknowledgment_and_event_samples'],
                                     {'unknown_event_bits_samples': 1,
                                      **{name: 1 for bit, name in analysis.EVENTS.items() if known & bit}})
                    self.assertEqual(seg['timeline'][0]['events_mask'], high | known)
                    self.assertEqual(seg['timeline'][0]['events'],
                                     [name for bit, name in analysis.EVENTS.items() if known & bit])

    def test_side_b_veto_does_not_escape_legacy_quarantine(self):
        rows = complete()
        rows[1]['events'] = 128
        report = analyze(rows)
        seg = report['segments'][0]
        self.assertEqual(report['scan']['rejected_records'], 0)
        assert_quarantined(self, seg)
        self.assertEqual(seg['sample_quarantine']['diagnostic_raw_timeline'][0]['events'], 128)
        self.assertTrue(all(g['logged_updates'] == 13 for g in seg['gates']))
        self.assertNotIn('side_b_veto=1', analysis.markdown(report))

    def test_side_b_veto_does_not_escape_input_wide_corruption_quarantine(self):
        rows = v2(complete())
        rows[1]['events'] = 128
        # Even a rejected orphan after the end, outside the selected segment,
        # must withhold this new event along with every other sample metric.
        report = analyze(rows + ['SBREC {"v":2}\n'], segment=1)
        self.assertEqual(report['scan']['rejected_records'], 1)
        seg = report['segments'][0]
        assert_quarantined(self, seg)
        self.assertEqual(seg['sample_quarantine']['diagnostic_raw_timeline'][0]['events'], 128)
        self.assertNotIn('side_b_veto=1', analysis.markdown(report))

    def test_side_b_veto_is_not_coverage_gate_or_recovery_evidence(self):
        rows = complete()
        rows[2]['gap'] = 1
        baseline = first(rows)
        rows[2]['events'] = 128
        seg = first(rows)
        self.assertEqual(seg['acknowledgment_and_event_samples'], {'side_b_veto': 1})
        for field in ('coverage', 'gates', 'observed_changes', 'native_priorities',
                      'custom_intents', 'recovery_motion_context_samples', 'warnings'):
            self.assertEqual(seg[field], baseline[field], field)
        self.assertEqual(seg['coverage']['known_continuous_frames'], 0)
        self.assertEqual(seg['coverage']['status'], 'partial_or_inconsistent')
        self.assertEqual(seg['recovery_motion_context_samples'], {'self': 0, 'rival': 0})
        self.assertIsNone(seg['offstage'])
        text = analysis.markdown(analyze_v2(rows))
        self.assertIn('side_b_veto=1', text)
        self.assertIn('not an acknowledgment, hit, success or proof of a saved recovery', text)

    def test_events_intents_flags_ego_and_positions_are_sampled_context(self):
        falcon_hi = next(k for k, v in LABELS.falcon.items() if v == 'ftCa_MS_SpecialAirHi')
        actor = fighter(motion=falcon_hi, flags=255)
        actor[4:9] = [999, -99, -2, 3, 4]
        seg = first([begin(), sample(ego=20, action=3, owns=True, events=127 | 256, self=actor),
                     sample(101, ego=80, action=3, owns=True, events=2, self=actor)])
        self.assertEqual(seg['ego_range'], [20, 80])
        self.assertEqual(seg['custom_intents']['punch']['samples'], 2)
        self.assertEqual(seg['acknowledgment_and_event_samples']['punch_ack'], 2)
        self.assertEqual(seg['acknowledgment_and_event_samples']['lcancel_sample'], 1)
        self.assertEqual(seg['fighter_flag_samples']['self']['airborne'], 2)
        self.assertEqual(seg['fighter_flag_samples']['self']['protected'], 2)
        self.assertEqual(seg['recovery_motion_context_samples']['self'], 2)
        self.assertEqual(seg['position_ranges_at_samples']['self']['x'], [999, 999])
        self.assertIsNone(seg['offstage'])
        self.assertIsNone(seg['timeline'][0]['self']['offstage'])
        self.assertEqual(set(seg['timeline'][0]['self']['flag_names']), set(analysis.FLAGS.values()))
        self.assertIn('unknown_event_bits', seg['warnings']['counts'])
        text = analysis.markdown(analyze([begin(), sample(self=actor)]))
        self.assertIn('Airborne is not offstage', text)
        self.assertIn('does not prove lag reduction', text)

    def test_numeric_fallback_and_internal_fighter_kind_mapping(self):
        self.assertEqual(LABELS.motion(fighter(motion=14)), 'ftCo_MS_Wait')
        self.assertEqual(LABELS.motion(fighter(motion=66)), 'ftCo_MS_AttackAirF')
        falcon_n = next(k for k, v in LABELS.falcon.items() if v == 'ftCa_MS_SpecialN')
        self.assertEqual(LABELS.motion(fighter(motion=falcon_n)), 'ftCa_MS_SpecialN')
        self.assertEqual(LABELS.motion(fighter(kind=25, motion=falcon_n)), 'unknown_motion_' + str(falcon_n))
        seg = first([begin(), sample(action=999, self=fighter(motion=400), native=[9999, -1, -1])])
        self.assertIn('unknown_intent_999', seg['custom_intents'])
        self.assertIn('native_priority_9999', seg['native_priorities'])
        self.assertEqual(seg['timeline'][0]['self']['motion_label'], 'unknown_motion_400')

    def test_enum_reader_is_safe_and_standalone_fallback_explicit(self):
        good = 'typedef enum E { A = -1, B, C = BASE, D, X = D - C, } E;'
        self.assertEqual(analysis.read_enum(good, 'E', {'BASE': 341}),
                         {'A': -1, 'B': 0, 'C': 341, 'D': 342, 'X': 1})
        for expr in ('__import__("os").system("echo bad")', '1 << 3', 'unknown', 'A * A'):
            with self.assertRaises(ValueError):
                analysis.read_enum('typedef enum E { A = ' + expr + ', B } E;', 'E')
        with tempfile.TemporaryDirectory() as directory:
            labels = analysis.Labels(directory)
            report = analysis.analyze_stream(io.BytesIO(encoded(v2(complete()))), labels=labels)
            self.assertEqual(report['segments'][0]['timeline'][0]['self']['motion_label'], 'unknown_motion_14')
            self.assertIn('motion_headers_unavailable_numeric_fallback', report['warnings']['counts'])

    def test_recorder_and_hud_header_ids_match_maps(self):
        text = (ROOT / 'src/melee/mod/showboat_recorder.h').read_text()
        blocks = re.findall(r'enum\s*\{([^}]+)\}', text)
        tactic_ids = [v.strip() for v in blocks[0].split(',') if v.strip()]
        reason_ids = [v.strip() for v in blocks[1].split(',') if v.strip()]
        self.assertEqual(tactic_ids[:-1], ['SBR_' + name.upper() for name in analysis.TACTICS])
        self.assertEqual(reason_ids[:-1], ['SBR_' + name.upper() for name in analysis.REASONS])
        events = dict((name, int(value)) for name, value in re.findall(r'(SBR_EVENT_\w+)\s*=\s*(\d+)', text))
        self.assertEqual(set(events.values()), set(analysis.EVENTS))
        self.assertEqual(events['SBR_EVENT_PUNCH_ACK'], 2)
        self.assertEqual(events['SBR_EVENT_LCANCEL_SAMPLE'], 64)
        self.assertEqual(events['SBR_EVENT_SIDEB_VETO'], 128)
        hud = analysis.read_enum((ROOT / 'src/melee/mod/showboat_hud.h').read_text().replace(
            'enum ShowboatHUD_Action', 'typedef enum ShowboatHUD_Action'), 'ShowboatHUD_Action')
        self.assertEqual(hud, {'SHOWBOAT_HUD_' + name.upper(): i for i, name in enumerate(analysis.INTENTS)})


class BoundsAndCLITests(unittest.TestCase):
    def test_oversize_lines_drained_in_bounded_chunks_and_following_record_survives(self):
        class BoundedReader(io.BytesIO):
            def readline(self, size=-1):
                if size <= 0 or size > 1025:
                    raise AssertionError('unbounded read')
                return super().readline(size)
        data = b'SBREC {"huge":"' + b'x' * 20000 + b'"}\n' + encoded(complete())
        report = analysis.analyze_stream(BoundedReader(data), labels=LABELS,
                                         limits=replace(analysis.Limits(), line_bytes=1024))
        self.assertEqual(report['scan']['accepted_records'], 9)
        self.assertEqual(report['scan']['lines'], 10)
        self.assertIn('line_byte_limit', report['warnings']['counts'])

    def test_file_and_segment_limits_are_explicit_and_selection_does_not_bypass(self):
        report = analyze(complete(), limits=replace(analysis.Limits(), file_bytes=100))
        self.assertTrue(report['scan']['limited'])
        self.assertEqual(report['scan']['bytes'], 100)
        self.assertIn('file_byte_limit_analysis_stopped', report['warnings']['counts'])
        report = analyze(complete() + complete(2), segment=2,
                         limits=replace(analysis.Limits(), segments=1))
        self.assertEqual(report['segments'], [])
        self.assertIn('segment_limit_analysis_stopped', report['warnings']['counts'])
        self.assertIn('requested_segment_not_found_in_scanned_records', report['warnings']['counts'])

    def test_histogram_timeline_warning_and_gate_key_caps(self):
        limits = replace(analysis.Limits(), keys=5, timeline=3, warnings=2)
        rows = [begin()] + [sample(100 + i, self=fighter(motion=400 + i), action=100 + i,
                                  native=[100 + i, 0, 0]) for i in range(30)]
        seg = first(rows, limits=limits)
        self.assertLessEqual(len(seg['motions']['self']), 6)
        self.assertLessEqual(len(seg['native_priorities']), 6)
        self.assertLessEqual(len(seg['custom_intents']), 6)
        self.assertEqual(len(seg['timeline']), 3)
        self.assertEqual(seg['timeline_omitted'], 27)
        self.assertEqual(len(seg['warnings']['examples']), 2)
        self.assertGreater(seg['warnings']['examples_omitted'], 0)
        self.assertIn('histogram_key_limit', seg['warnings']['counts'])
        rows += [gate(frame=129, tactic=i, reason=i, count=1) for i in range(10)]
        seg = first(rows, limits=limits)
        assert_quarantined(self, seg)
        self.assertEqual(len(seg['sample_quarantine']['diagnostic_raw_timeline']), 3)
        self.assertEqual(seg['sample_quarantine']['diagnostic_raw_timeline_omitted'], 27)
        self.assertIn('gate_key_limit_row_rejected', seg['warnings']['counts'])
        json.dumps(seg, allow_nan=False)

    def test_streaming_memory_not_proportional_to_samples(self):
        class SyntheticStream:
            def __init__(self, count):
                self.count = count
                self.index = -1

            def readline(self, size):
                if self.index >= self.count:
                    return b''
                row = begin() if self.index == -1 else sample(100 + self.index)
                self.index += 1
                data = encoded(v2([row]))
                if size < len(data):
                    raise AssertionError('unexpected small read')
                return data

        def peak(count):
            tracemalloc.start()
            try:
                report = analysis.analyze_stream(SyntheticStream(count), labels=LABELS,
                                                 limits=replace(analysis.Limits(), timeline=2))
                memory = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertEqual(report['segments'][0]['coverage']['accepted_sample_records'], count)
            return memory
        short = peak(100)
        long = peak(3000)
        self.assertLess(long, short + 250000, (short, long))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools/analyze_showboat.py'), *map(str, args)],
                              capture_output=True, text=True, timeout=10,
                              env=None)

    def test_capture_directory_cli_json_markdown_segment_and_metadata_not_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete() + complete(2, frame=1)))
            (path / 'metadata.json').write_text(json.dumps({'winner': 'FAKE_WINNER', 'match_result': 'won',
                                                          'observations': 999999, 'started_at': 'synthetic'}))
            output, markdown = path / 'analysis.json', path / 'analysis.md'
            result = self.run_cli(path, '--segment', 2, '--json', output, '--markdown', markdown)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            report = json.loads(output.read_text())
            self.assertEqual([s['segment'] for s in report['segments']], [2])
            assert_quarantined(self, report['segments'][0])
            self.assertIn('Sample summaries withheld', markdown.read_text())
            self.assertNotIn('Native priority known frames:', markdown.read_text())
            self.assertNotIn('PROVISIONAL', markdown.read_text())
            self.assertEqual(report['segments'][0]['coverage']['recorder_reported_observations'], 13)
            self.assertFalse(report['metadata']['used_for_statistics'])
            self.assertNotIn('FAKE_WINNER', output.read_text() + markdown.read_text())
            self.assertIn('## Segment 2', markdown.read_text())
            result = self.run_cli(path / 'runtime.log')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith('# Showboat recording analysis'))
            self.assertIn('## Segment 1', result.stdout)

    def test_v2_cli_reports_numeric_floats_and_withholds_corrupted_sample_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            log, output, text = path / 'runtime.log', path / 'analysis.json', path / 'analysis.md'
            rows = v2(complete())
            rows[1]['self'][4] = '80000000'
            rows[1]['rival'][4] = '00000001'
            log.write_bytes(encoded(rows))
            result = self.run_cli(log, '--json', output, '--markdown', text)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            snap = report['segments'][0]['timeline'][0]
            self.assertEqual(math.copysign(1, snap['self']['x']), -1)
            self.assertEqual(snap['rival']['x'], 2**-149)
            self.assertEqual(report['integrity']['status'], 'validated_v2_records_not_runtime_verified')
            self.assertIn('Native priority known frames:', text.read_text())
            rows[1]['self'][12] = 256
            evidence = encoded(rows)
            log.write_bytes(evidence)
            result = self.run_cli(log, '--json', output, '--markdown', text)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_bytes(), evidence)
            self.assertEqual(json.loads(output.read_text())['integrity']['sample_derived_statistics'],
                             'quarantined')
            self.assertIn('Sample summaries withheld', text.read_text())
            self.assertNotIn('Native priority known frames:', text.read_text())

    def test_missing_malformed_and_huge_metadata_remain_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete()))
            report = analysis.analyze_path(path)
            self.assertIn('missing_metadata', report['warnings']['counts'])
            for data in ('{"v":', '{"x":NaN}', '[]', '{"x":1,"x":2}', 'x' * 70000):
                (path / 'metadata.json').write_text(data)
                report = analysis.analyze_path(path)
                self.assertIn('invalid_or_oversize_metadata', report['warnings']['counts'])
                self.assertEqual(report['segments'][0]['coverage']['accepted_sample_records'], 2)

    def test_launch_fallback_long_args_whitelist_and_live_or_incomplete_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded([begin(), sample()]))
            sentinel = path / 'must-not-execute'
            command = ['/' + 'p' * 3000, "$(touch '%s')" % sentinel]
            launch = {'dol': '/' + 'd' * 3000, 'command': command,
                      'dol_sha1': 'a' * 40, 'dol_size': 12345,
                      'recorder_marker_present': True, 'git_commit': 'b' * 40,
                      'git_dirty': False, 'controller_config_sha1': 'c' * 40,
                      'start_utc': '2026-06-01T12:34:56.000Z',
                      'winner': 'FORGED_WINNER', 'observations': 999,
                      'returncode': 0, 'end_utc': '2026-06-01T12:35:00Z'}
            (path / 'launch.json').write_text(json.dumps(launch))
            report = analysis.analyze_path(path)
            metadata = report['metadata']
            self.assertEqual(metadata['source'], 'launch.json')
            self.assertEqual(metadata['status'], 'launch_metadata_context_only')
            self.assertEqual(metadata['capture_status'], 'live_or_incomplete')
            self.assertFalse(metadata['used_for_statistics'])
            self.assertEqual(metadata['context'], {k: launch[k] for k in (
                'dol_sha1', 'dol_size', 'recorder_marker_present', 'git_commit', 'git_dirty',
                'controller_config_sha1', 'start_utc')})
            self.assertIn('missing_metadata', report['warnings']['counts'])
            self.assertIn('capture_live_or_incomplete', report['warnings']['counts'])
            self.assertIn('missing_end_eof_unflushed_gate_tail_unknown',
                          report['segments'][0]['warnings']['counts'])
            self.assertIsNone(report['segments'][0]['coverage']['recorder_reported_observations'])
            output = json.dumps(report) + analysis.markdown(report)
            self.assertNotIn('FORGED_WINNER', output)
            self.assertNotIn(command[0], output)
            self.assertNotIn(str(sentinel), output)
            self.assertIn('live_or_incomplete', analysis.markdown(report))
            self.assertFalse(sentinel.exists())

    def test_completion_metadata_preferred_and_process_exit_not_match_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete()))
            (path / 'launch.json').write_text(json.dumps({'dol_sha1': 'a' * 40}))
            completion = {'dol_sha1': 'b' * 40, 'command': ['/' + 'p' * 3000],
                          'launch_error': 'x' * 3000, 'returncode': -9,
                          'end_utc': '2026-06-01T12:35:00Z', 'winner': 'FAKE_WINNER'}
            (path / 'metadata.json').write_text(json.dumps(completion))
            report = analysis.analyze_path(path)
            metadata = report['metadata']
            self.assertEqual(metadata['source'], 'metadata.json')
            self.assertEqual(metadata['capture_status'], 'completion_manifest_present_not_outcome')
            self.assertEqual(metadata['context'], {'dol_sha1': 'b' * 40, 'returncode': -9,
                                                    'end_utc': completion['end_utc']})
            self.assertNotIn('capture_live_or_incomplete', report['warnings']['counts'])
            self.assertEqual(report['segments'][0]['coverage']['recorder_reported_observations'], 13)
            self.assertNotIn('FAKE_WINNER', json.dumps(report))

    def test_invalid_completion_falls_back_without_hiding_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete()))
            (path / 'metadata.json').write_text('{truncated')
            (path / 'launch.json').write_text(json.dumps({'dol_sha1': 'c' * 40}))
            report = analysis.analyze_path(path, limits=replace(analysis.Limits(), warnings=0))
            self.assertEqual(report['metadata']['source'], 'launch.json')
            self.assertEqual(report['metadata']['capture_status'], 'live_or_incomplete')
            self.assertIn('invalid_or_oversize_metadata', report['warnings']['counts'])
            self.assertEqual(report['warnings']['examples'], [])
            self.assertEqual(report['warnings']['examples_omitted'], sum(report['warnings']['counts'].values()))

    def test_launch_metadata_security_caps_and_typed_whitelist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete()))
            for data in ('{"x":NaN}', '{"x":1e999}', '{"x":1,"x":2}', '[]',
                         '[' * 9 + '0' + ']' * 9, json.dumps({'x': [0] * 129}),
                         json.dumps({'x': [[0] * 100] * 6}),
                         json.dumps({'x': 'a' * 129}),
                         json.dumps({'command': ['p' * 4097]}),
                         json.dumps({'dol': 'p' * 4097}), ' ' * 65536 + '{}'):
                with self.subTest(data=data[:50]):
                    (path / 'launch.json').write_text(data)
                    report = analysis.analyze_path(path)
                    self.assertIn('invalid_or_oversize_launch_metadata', report['warnings']['counts'])
                    self.assertIsNone(report['metadata']['source'])
            invalid_types = {'dol_sha1': 'not a hash', 'git_commit': 123, 'git_dirty': 1,
                             'recorder_marker_present': 'true', 'dol_size': True,
                             'returncode': False, 'start_utc': '$(command)', 'end_utc': '<script>'}
            (path / 'metadata.json').write_text(json.dumps(invalid_types))
            report = analysis.analyze_path(path)
            self.assertEqual(report['metadata']['context'], {})
            # Long string exceptions do not apply to structured recorder rows.
            self.assertIn('string_limit', analyze([sample(command=['p' * 129])])['warnings']['counts'])

    def test_cli_protects_launch_metadata_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'runtime.log').write_bytes(encoded(complete()))
            launch = path / 'launch.json'
            launch.write_text('{}')
            alias = path / 'launch-alias.json'
            alias.symlink_to(launch)
            hard = path / 'launch-hard.json'
            hard.hardlink_to(launch)
            for source in (path, path / 'runtime.log'):
                for target in (launch, alias, hard):
                    result = self.run_cli(source, '--json', target)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(launch.read_text(), '{}')
            launch.unlink()
            self.assertEqual(self.run_cli(path, '--json', launch).returncode, 2)
            self.assertFalse(launch.exists())

    def test_batch_tracking_is_bounded_by_keys_not_flush_count(self):
        limits = replace(analysis.Limits(), keys=5, timeline=1, warnings=1)
        segment = analysis.Segment(begin(), limits, LABELS, True)
        for batch in range(1, 3001):
            for row in flush(frame=100, start=100, count=60, batch=batch):
                self.assertTrue(segment.accept(row, 1))
        self.assertEqual(segment.gate_batch, 3000)
        self.assertEqual(len(segment.gate_seen), 5)
        self.assertEqual(len(segment.gate_last), 5)
        self.assertTrue(all(sum(bins.values()) == 180000 for bins in segment.gates.values()))
        bad = gate(frame=100, count=1, reason=1, batch=3001)
        self.assertFalse(segment.accept(bad, 1))
        self.assertIn('gate_key_limit_row_rejected', segment.warnings.counts)
        # An old ID remains invalid even when its current-flush keys are gone.
        self.assertFalse(segment.accept(gate(frame=100, count=60, batch=1), 1))
        self.assertEqual(len(segment.gate_seen), 5)

    def test_cli_input_errors_and_output_aliases_do_not_destroy_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            log = path / 'runtime.log'
            data = encoded(complete())
            log.write_bytes(data)
            alias = path / 'alias.log'
            alias.symlink_to(log)
            hard = path / 'hard.log'
            hard.hardlink_to(log)
            for target in (log, alias, hard):
                result = self.run_cli(log, '--json', target)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(log.read_bytes(), data)
            for args in ((path / 'missing.log',), (log, '--segment', -1),
                         (log, '--json', path / 'same', '--markdown', path / 'same')):
                self.assertEqual(self.run_cli(*args).returncode, 2)
            result = self.run_cli(log, '--segment', 99)
            self.assertEqual(result.returncode, 0)
            self.assertIn('requested_segment_not_found', result.stdout)


if __name__ == '__main__':
    unittest.main()
