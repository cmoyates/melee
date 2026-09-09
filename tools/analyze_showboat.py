#!/usr/bin/env python3
"""Read-only SBREC v1 analysis (Python stdlib, no emulator dependencies).

Usage: python3 tools/analyze_showboat.py runtime.log [--segment N]
       python3 tools/analyze_showboat.py capture/ --json report.json --markdown report.md
Tests: python3 -m unittest discover -s tools/tests -p test_showboat_analysis.py

Memory is independent of log length: bounded binary readline, bounded JSON trees,
segments, histogram keys, warning examples and first-N timeline snapshots. Default
limits: 1 GiB scanned, 64 KiB/line, 128 segments, 128 keys/histogram, 48 snapshots
and 32 warning examples per segment/report. Oversize lines are drained in bounded
chunks; file/segment limits stop analysis with an explicit partial warning. Limits
apply before --segment filtering. JSON depth <=8, <=512 nodes, <=128 items per
container/string characters, <=10 integer digits and finite f32 magnitude (with
text rounding tolerance). Metadata is capped at 64 KiB; only its path/argument/
launch-error strings may reach 4096 characters. Only whitelisted provenance is
retained, never used for statistics or match results.
Log text is never executed; reports use validated fields, never raw log lines.

Durations are left-closed intervals [previous sample, current sample), supported
only by the v1 change/12-frame sampling guarantee, gap=0 and intact ordering and
identities. No initial/end extrapolation. Counts are observations, not matches.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys


TACTICS = ('personality', 'combat', 'movement', 'defense', 'lcancel')
REASONS = ('not_evaluated', 'no_candidate', 'active', 'started',
           'native_priority', 'input_or_script', 'physical_or_state', 'target',
           'geometry_or_window', 'cooldown', 'ego_or_caution', 'items',
           'completed', 'cancelled', 'budget', 'success')
INTENTS = ('vanilla', 'taunt', 'swagger', 'punch', 'dance', 'grab', 'knee',
           'upair', 'juggle', 'wdash', 'block', 'perfect')
EVENTS = {1: 'taunt_ack', 2: 'punch_ack', 4: 'grab_ack', 8: 'aerial_ack',
          16: 'wavedash_landing_ack', 32: 'custom_powershield_contact',
          64: 'lcancel_sample'}
FLAGS = {1: 'airborne', 2: 'hitstun', 4: 'hitlag', 8: 'inactive',
         16: 'held_item', 32: 'captured_or_thrown', 64: 'protected',
         128: 'global_items_present'}
REJECTED = {1, 4, 5, 6, 7, 8, 9, 10, 11, 14}
BASE = {'v', 'type', 'segment', 'slot', 'frame'}
# Accept decimal roundings of FLT_MAX, including 3.4028235e38, not f32 overflow.
F32_TEXT_MAX = 3.4028235e38
OPTIONAL = {'sample': {'reasons'}, 'gate': {'batch'}}
FIELDS = {
    'begin': {'stage', 'mode', 'match_kind', 'target', 'interval'},
    'sample': {'ego', 'action', 'owns', 'events', 'gap', 'self', 'rival',
               'native', 'input'},
    'gate': {'from', 'tactic', 'reason', 'count'},
    'end': {'reason', 'observations'},
}
NOTES = [
    'Segments are recording intervals, not complete matches. End is a recording '
    'lifecycle event, never a win/loss or match result; metadata is not outcome evidence.',
    'Sample counts are actual accepted snapshots, not all CPU updates. End totals '
    'are recorder-reported; continuity lower bounds rely on the v1 emission contract.',
    'Known frames use [previous,current) only with gap=0, at most 12 frames, intact '
    'ordering and identities. Periodic unchanged samples count; gaps and tails do not.',
    'Motion/intent entries are observed continuous transitions, not action totals. '
    'Initial sightings and sightings after breaks are separate. Native priorities '
    'are numeric IDs, not inferred tactics.',
    'Gate denominators are each tactic\'s logged updates, not pooled tactics. '
    'NOT_EVALUATED is not rejection; missing bins and unflushed EOF tails are unknown. '
    'Multiple updates can share a game frame, including across flush batches; '
    'gate counts are never durations. Legacy shared-boundary duplicate bins are ambiguous.',
    'Optional sample reasons are final tactic outcomes at that sampled update only. '
    'Reason changes do not trigger samples; no reasons are inferred between samples '
    'or added to gate aggregates.',
    'Acknowledgments are not hits; lcancel_sample does not prove lag reduction. '
    'Percent increases are comparable endpoint net increases, not raw hit damage '
    'or guaranteed attribution; stock changes are not attributed KOs.',
    'Inputs are CPU output before preprocessing, not hardware or opponent inputs. '
    'Both fighters are sampled at the CPU hook, not an atomic world snapshot.',
    'Recovery context is motion/flag evidence only. Offstage is unknown: v1 has '
    'no offstage bit or stage geometry. Airborne is not offstage, and sparse '
    'positions do not prove recovery success or useful wavedash displacement.',
]


@dataclass(frozen=True)
class Limits:
    file_bytes: int = 1024 * 1024 * 1024
    line_bytes: int = 64 * 1024
    segments: int = 128
    keys: int = 128
    timeline: int = 48
    warnings: int = 32
    metadata_bytes: int = 64 * 1024


class Invalid(ValueError):
    """A bounded, non-log-derived diagnostic code."""


class Warnings:
    def __init__(self, limit):
        self.counts = Counter()
        self.examples = []
        self.limit = limit

    def add(self, code, line=None):
        self.counts[code] += 1
        if len(self.examples) < self.limit:
            self.examples.append({'code': code, 'line': line})

    def export(self):
        return {'counts': dict(self.counts), 'examples': self.examples,
                'examples_omitted': sum(self.counts.values()) - len(self.examples)}


def strict_json(text, *, metadata=False):
    """Only JSON; reject duplicate keys, deep/wide trees and oversized scalars."""
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 8:
                raise Invalid('json_depth_limit')
        elif char in ']}':
            depth -= 1

    def integer(token):
        if len(token.lstrip('-')) > 10:
            raise Invalid('integer_limit')
        return int(token)

    def constant(_):
        raise Invalid('nonfinite_number')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Invalid('duplicate_json_key')
            result[key] = value
        return result

    try:
        value = json.loads(text, parse_int=integer, parse_constant=constant,
                           object_pairs_hook=pairs)
    except (json.JSONDecodeError, RecursionError, OverflowError):
        raise Invalid('malformed_or_truncated_json') from None
    budget = [512]

    def check(node, path=()):
        budget[0] -= 1
        if budget[0] < 0:
            raise Invalid('json_node_limit')
        if isinstance(node, str):
            long_context = metadata and (path in (('dol',), ('launch_error',)) or
                                         (len(path) == 2 and path[0] == 'command'
                                          and type(path[1]) is int))
            if len(node) > (4096 if long_context else 128):
                raise Invalid('string_limit')
        elif type(node) in (int, float):
            if not math.isfinite(node):
                raise Invalid('nonfinite_number')
            if abs(node) > F32_TEXT_MAX:
                raise Invalid('numeric_magnitude_limit')
        elif isinstance(node, (list, dict)):
            if len(node) > 128:
                raise Invalid('json_shape_limit')
            if isinstance(node, dict):
                for key, item in node.items():
                    check(key)
                    check(item, path + (key,))
            else:
                for index, item in enumerate(node):
                    check(item, path + (index,))
    check(value)
    return value


def integer(value, low=0, high=0xFFFFFFFF):
    if type(value) is not int or not low <= value <= high:
        raise Invalid('invalid_integer_or_id')


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Invalid('invalid_finite_number')
    if abs(value) > F32_TEXT_MAX:
        raise Invalid('numeric_magnitude_limit')


def validate(row):
    if not isinstance(row, dict):
        raise Invalid('record_not_object')
    integer(row.get('v'))
    if row['v'] != 1:
        raise Invalid('unknown_version')
    kind = row.get('type')
    if not isinstance(kind, str) or kind not in FIELDS:
        raise Invalid('unknown_record_type')
    expected = BASE | FIELDS[kind]
    if not expected <= row.keys():
        raise Invalid('missing_fields')
    expected |= OPTIONAL.get(kind, set()) & row.keys()
    for key in ('segment', 'frame'):
        integer(row[key])
    integer(row['slot'], 0, 5)
    if kind == 'begin':
        for key in ('stage', 'mode', 'match_kind'):
            integer(row[key], -1)
        integer(row['target'], 0, 5)
        integer(row['interval'], 12, 12)
    elif kind == 'sample':
        integer(row['ego'], -0x80000000, 0x7FFFFFFF)
        for key in ('action', 'events'):
            integer(row[key])
        integer(row['gap'], 0, 1)
        if type(row['owns']) is not bool:
            integer(row['owns'], 0, 1)
        for key, size in (('self', 13), ('rival', 13), ('native', 3), ('input', 7)):
            array = row[key]
            if not isinstance(array, list) or len(array) != size:
                raise Invalid('invalid_array_shape')
            for value in array:
                number(value)
        for key in ('self', 'rival'):
            array = row[key]
            # anim is cur_anim_frame (fractional), not an animation ID.
            integer(array[0], -0x80000000, 0x7FFFFFFF)
            for i in (1, 2, 10, 12):
                integer(array[i], -1 if i in (1, 2, 10) else 0)
            if array[9] < 0:
                raise Invalid('negative_percent')
        for value in row['native']:
            integer(value, -0x80000000, 0x7FFFFFFF)
        integer(row['input'][0])
        for value in row['input'][1:5]:
            integer(value, -128, 127)
        for value in row['input'][5:]:
            integer(value, 0, 255)
        if 'reasons' in row:
            if not isinstance(row['reasons'], list) or len(row['reasons']) != len(TACTICS):
                raise Invalid('invalid_sample_reasons_shape')
            for value in row['reasons']:
                integer(value)
    elif kind == 'gate':
        for key in ('from', 'tactic', 'reason'):
            integer(row[key])
        integer(row['count'], 1)
        if 'batch' in row:
            integer(row['batch'], 1)
        if row['from'] > row['frame']:
            raise Invalid('impossible_gate_range_or_count')
    else:
        integer(row['observations'])
        if not isinstance(row['reason'], str) or not re.fullmatch(
                r'[A-Za-z][A-Za-z0-9_:-]{0,47}', row['reason']):
            raise Invalid('invalid_end_token')
    # Ignore extra fields, especially forged result/winner/hit claims.
    return {key: row[key] for key in expected}, bool(row.keys() - expected)


def read_enum(text, enum_name, symbols=None):
    """Deliberately tiny C-enum grammar: literals, prior names, or name +/- name.

    No eval/exec, preprocessor, imports, shell or arbitrary AST interpretation.
    Fail closed for the whole enum rather than shifting following numeric labels.
    """
    symbols = dict(symbols or {})
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    match = re.search(r'\btypedef\s+enum\s+' + re.escape(enum_name)
                      + r'\s*\{([^{}]*)\}', text)
    if not match:
        raise ValueError('enum unavailable')
    result = {}
    previous = -1
    for item in match[1].split(','):
        if not item.strip():
            continue
        part = re.fullmatch(r'\s*([A-Za-z_]\w*)\s*(?:=\s*(.*?))?\s*', item)
        if not part:
            raise ValueError('unsupported enum member')
        name, expr = part.groups()
        if expr is None:
            value = previous + 1
        elif re.fullmatch(r'-?(?:0x[0-9A-Fa-f]+|[0-9]+)', expr):
            value = int(expr, 16 if '0x' in expr else 10)
        elif expr in symbols:
            value = symbols[expr]
        else:
            terms = re.fullmatch(r'([A-Za-z_]\w*)\s*([+-])\s*([A-Za-z_]\w*)', expr)
            if not terms or terms[1] not in symbols or terms[3] not in symbols:
                raise ValueError('unsupported enum expression')
            value = symbols[terms[1]] + (1 if terms[2] == '+' else -1) * symbols[terms[3]]
        symbols[name] = result[name] = previous = value
    return result


class Labels:
    def __init__(self, root=None):
        self.common = {}
        self.falcon = {}
        self.sources = []
        root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
        symbols = {}
        for relative, enum, dest in (
            ('src/melee/ft/kinds/ftCommon/forward.h', 'ftCommon_MotionState', self.common),
            ('src/melee/ft/kinds/ftCaptain/forward.h', 'ftCaptain_MotionState', self.falcon),
        ):
            try:
                with (root / relative).open('rb') as stream:
                    data = stream.read(256 * 1024 + 1)
                if len(data) > 256 * 1024:
                    raise ValueError('header limit')
                members = read_enum(data.decode('utf-8'), enum, symbols)
                symbols.update(members)
                dest.update({value: name for name, value in members.items()
                             if not name.endswith(('Count', 'SelfCount'))})
                self.sources.append(relative)
            except (OSError, UnicodeError, ValueError):
                pass  # Standalone copies still work; explicit numeric fallback.

    def motion(self, fighter):
        kind, motion = fighter[1:3]
        label = self.common.get(motion)
        if label is None and kind == 2:  # FighterKind, not external CharacterKind.
            label = self.falcon.get(motion)
        return label or 'unknown_motion_' + str(motion)


def enum_label(names, value, category):
    return names[value] if 0 <= value < len(names) else 'unknown_' + category + '_' + str(value)


def flag_names(mask):
    names = [name for bit, name in FLAGS.items() if mask & bit]
    if mask & ~255:
        names.append('unknown_bits_0x%x' % (mask & ~255))
    return names


class Histogram:
    """At most limit specific keys plus an explicit overflow aggregate."""
    def __init__(self, limit, warnings):
        self.rows = {}
        self.limit = limit
        self.warnings = warnings

    def add(self, key, field, amount=1):
        if key not in self.rows and len(self.rows) >= self.limit:
            key = 'other_ids_key_limit'
            if key not in self.rows:
                self.warnings.add('histogram_key_limit')
        bucket = self.rows.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount


def identity(fighter):
    return tuple(fighter[:2])  # spawn and internal FighterKind


def motion_key(fighter, labels):
    return '%d:%d:%s' % (fighter[1], fighter[2], labels.motion(fighter))


def fighter_context(fighter, labels):
    label = labels.motion(fighter)
    recovery = any(word in label for word in ('SpecialHi', 'SpecialAirHi', 'FallSpecial', 'Cliff'))
    return {'spawn': fighter[0], 'kind': fighter[1], 'motion': fighter[2],
            'motion_label': label, 'anim': fighter[3], 'x': fighter[4], 'y': fighter[5],
            'vx': fighter[6], 'vy': fighter[7], 'ground_v': fighter[8],
            'percent': fighter[9], 'stocks': fighter[10], 'shield': fighter[11],
            'flags': fighter[12], 'flag_names': flag_names(fighter[12]),
            'recovery_motion_context': recovery, 'offstage': None}


class Segment:
    def __init__(self, row, limits, labels, began):
        self.id = row['segment']
        self.slot = row['slot']
        self.limits = limits
        self.labels = labels
        self.warnings = Warnings(limits.warnings)
        self.begin = row if began else None
        self.end = None
        self.superseded = False
        self.last_frame = row['frame']
        self.first_frame = row['frame']
        self.previous = None
        self.bridge = False
        self.damaged = not began
        self.samples = self.known_frames = self.lower_bound = self.gaps = 0
        self.ego = None
        self.owns = 0
        self.timeline = []
        self.motions = {side: Histogram(limits.keys, self.warnings) for side in ('self', 'rival')}
        self.priorities = Histogram(limits.keys, self.warnings)
        self.intents = Histogram(limits.keys, self.warnings)
        self.events = Counter()
        self.flags = {side: Counter() for side in ('self', 'rival')}
        self.positions = {side: None for side in ('self', 'rival')}
        self.recovery = Counter()
        self.changes = {side: {'comparable_percent_pairs': 0, 'net_percent_increases': None,
                               'percent_decreases_excluded': 0, 'reset_pairs_excluded': 0,
                               'unknown_pairs_excluded': 0, 'stock_comparable_pairs': 0,
                               'stock_change_pairs': 0, 'stock_decreases': 0,
                               'stock_increases': 0, 'identity_changes': 0}
                        for side in ('self', 'rival')}
        self.gates = {}
        self.gate_last = {}  # Bounded distinct (tactic, reason) keys across segment.
        self.gate_mode = None
        self.gate_batch = 0
        self.gate_bounds = None
        self.gate_seen = {}  # Only current flush; never retain a set of all batches.
        if not began:
            self.warn('missing_begin')

    def warn(self, code, line=None, damage=True):
        self.warnings.add(code, line)
        if damage:
            self.damaged = True
            self.bridge = False

    def sample(self, row, line):
        prev = self.previous
        delta = row['frame'] - prev['frame'] if prev else 0
        stable = prev is not None and all(identity(prev[s]) == identity(row[s])
                                         for s in ('self', 'rival'))
        continuous = bool(prev and self.bridge and stable and not row['gap'] and 0 < delta <= 12)
        if row['gap']:
            self.gaps += 1
            self.warn('explicit_frame_gap', line)
        if prev and delta > 12:
            self.warn('sample_interval_exceeded_missing_rows_or_gap', line)
        if prev and not stable:
            self.warn('identity_changed_without_new_segment', line)
        if not prev and self.begin and row['frame'] != self.begin['frame']:
            self.warn('missing_initial_sample', line)
        if continuous:
            self.known_frames += delta
            self.lower_bound += delta - 1
        self.lower_bound += 1
        self.samples += 1
        self.owns += int(row['owns'])
        self.ego = ([row['ego'], row['ego']] if self.ego is None else
                    [min(self.ego[0], row['ego']), max(self.ego[1], row['ego'])])
        if not 0 <= row['ego'] <= 100:
            self.warn('ego_outside_hud_range', line, damage=False)
        if row['action'] >= len(INTENTS):
            self.warn('unknown_intent_id', line, damage=False)
        if row['events'] & ~127:
            self.warn('unknown_event_bits', line, damage=False)
            self.events['unknown_event_bits_samples'] += 1
        for bit, name in EVENTS.items():
            if row['events'] & bit:
                self.events[name] += 1
        intent = enum_label(INTENTS, row['action'], 'intent')
        self.intents.add(intent, 'samples')
        priority = 'native_priority_' + str(row['native'][0])
        self.priorities.add(priority, 'samples')
        if continuous:
            self.priorities.add('native_priority_' + str(prev['native'][0]), 'known_frames', delta)
            if prev['native'][0] != row['native'][0]:
                self.priorities.add(priority, 'entries')
            if prev['action'] != row['action']:
                self.intents.add(intent, 'entries')
        else:
            self.priorities.add(priority, 'boundary_sightings')
            self.intents.add(intent, 'boundary_sightings')
        contexts = {}
        for side in ('self', 'rival'):
            now = row[side]
            old = prev[side] if prev else None
            key = motion_key(now, self.labels)
            hist = self.motions[side]
            hist.add(key, 'samples')
            if continuous:
                hist.add(motion_key(old, self.labels), 'known_frames', delta)
                if old[2] != now[2]:
                    hist.add(key, 'entries')
            else:
                hist.add(key, 'boundary_sightings')
            if self.labels.motion(now).startswith('unknown_'):
                self.warn('unknown_motion_id_numeric_fallback', line, damage=False)
            for bit, name in FLAGS.items():
                if now[12] & bit:
                    self.flags[side][name] += 1
            if now[12] & ~255:
                self.flags[side]['unknown_bits_samples'] += 1
                self.warn('unknown_fighter_flag_bits', line, damage=False)
            context = contexts[side] = fighter_context(now, self.labels)
            self.recovery[side] += int(context['recovery_motion_context'])
            position = self.positions[side]
            if position is None:
                self.positions[side] = {'x': [now[4], now[4]], 'y': [now[5], now[5]]}
            else:
                for axis, index in (('x', 4), ('y', 5)):
                    position[axis] = [min(position[axis][0], now[index]),
                                      max(position[axis][1], now[index])]
            stats = self.changes[side]
            if old is not None:
                if identity(old) != identity(now):
                    stats['identity_changes'] += 1
                if not continuous:
                    stats['unknown_pairs_excluded'] += 1
                else:
                    if old[10] >= 0 and now[10] >= 0:
                        stats['stock_comparable_pairs'] += 1
                        stock_delta = now[10] - old[10]
                        stats['stock_change_pairs'] += int(stock_delta != 0)
                        stats['stock_decreases'] += max(0, -stock_delta)
                        stats['stock_increases'] += max(0, stock_delta)
                    # Inactive snapshots and any stock change are reset
                    # boundaries, even if percent increased at the boundary.
                    # Zero stocks are normal in Time matches. Only unknown
                    # (negative) stock values, changes or inactive snapshots
                    # block these endpoint comparisons; this is not hit damage.
                    if old[10] != now[10] or min(old[10], now[10]) < 0 or (old[12] | now[12]) & 8:
                        stats['reset_pairs_excluded'] += 1
                    elif now[9] < old[9]:
                        stats['percent_decreases_excluded'] += 1
                    else:
                        stats['comparable_percent_pairs'] += 1
                        stats['net_percent_increases'] = (stats['net_percent_increases'] or 0) + now[9] - old[9]
        if 'reasons' in row and any(r >= len(REASONS) for r in row['reasons']):
            self.warn('unknown_sample_reason_id', line, damage=False)
        if len(self.timeline) < self.limits.timeline:
            self.timeline.append({'frame': row['frame'], 'gap': row['gap'],
                                  'continuous_from_previous': continuous,
                                  'ego': row['ego'], 'intent': intent, 'action': row['action'],
                                  'owns': bool(row['owns']), 'events_mask': row['events'],
                                  'events': [name for bit, name in EVENTS.items() if row['events'] & bit],
                                  'self': contexts['self'], 'rival': contexts['rival'],
                                  'native': row['native'], 'input': row['input']})
            if 'reasons' in row:
                self.timeline[-1]['reasons'] = row['reasons']
                self.timeline[-1]['reason_labels'] = {
                    tactic: enum_label(REASONS, reason, 'reason')
                    for tactic, reason in zip(TACTICS, row['reasons'])}
        self.previous = row
        self.bridge = True

    def finish_gate_batch(self):
        if self.gate_mode == 'batch' and self.gate_seen:
            totals = [sum(n for (t, _), n in self.gate_seen.items() if t == tactic)
                      for tactic in range(len(TACTICS))]
            if len(set(totals)) != 1:
                self.warn('gate_batch_tactic_totals_disagree')

    def gate(self, row, line):
        tactic, reason = row['tactic'], row['reason']
        key = (tactic, reason)
        bounds = (row['from'], row['frame'])
        mode = 'batch' if 'batch' in row else 'legacy'
        batch = row.get('batch', 0)
        if row['from'] < self.first_frame:
            self.warn('gate_before_segment', line)
            return False
        if self.gate_mode is not None and mode != self.gate_mode:
            # Changing encodings cannot be used to count the same flush twice.
            self.warn('mixed_gate_batch_encoding', line)
            return False
        new_flush = self.gate_bounds is None
        if self.gate_bounds is not None:
            if mode == 'batch':
                if batch < self.gate_batch:
                    self.warn('gate_batch_not_monotonic', line)
                    return False
                new_flush = batch > self.gate_batch
                if not new_flush and bounds != self.gate_bounds:
                    self.warn('gate_batch_bounds_mismatch', line)
                    return False
            else:
                new_flush = bounds != self.gate_bounds
            if new_flush and row['from'] < self.gate_bounds[1]:
                self.warn('crossing_or_nonmonotonic_gate_bounds', line)
                return False
            if not new_flush and key in self.gate_seen:
                self.warn('duplicate_gate_batch_bin' if mode == 'batch' else
                          'duplicate_or_overlapping_gate_bin', line)
                return False
        if mode == 'legacy' and key in self.gate_last and row['from'] <= self.gate_last[key]:
            # A shared frame may be real, but without batch IDs this bin could
            # be a replay. Keep a conservative lower count, never inflate it.
            self.warn('duplicate_or_overlapping_gate_bin', line)
            return False
        # Unknown IDs are retained under numeric labels, but cannot grow memory.
        if key not in self.gate_last and len(self.gate_last) >= self.limits.keys:
            self.warn('gate_key_limit_row_rejected', line)
            return False
        if new_flush:
            self.finish_gate_batch()
            if mode == 'batch' and batch != self.gate_batch + 1:
                # Missing flushes do not invalidate later, independently keyed bins.
                self.warn('missing_gate_batches', line)
            self.gate_seen.clear()
            self.gate_batch = batch
            self.gate_bounds = bounds
        self.gate_mode = mode
        self.gate_seen[key] = row['count']
        self.gate_last[key] = row['frame']
        if tactic >= len(TACTICS) or reason >= len(REASONS):
            self.warn('unknown_gate_id', line, damage=False)
        bins = self.gates.setdefault(tactic, Counter())
        bins[reason] += row['count']
        return True

    def accept(self, row, line):
        kind = row['type']
        if row['slot'] != self.slot:
            self.warn('slot_identity_mismatch', line)
            return False
        if self.end is not None:
            self.warn('record_after_end_or_duplicate_end', line)
            return False
        if self.superseded:
            self.warn('record_after_slot_segment_replaced', line)
            return False
        if kind == 'begin':
            self.warn('duplicate_begin', line)
            return False
        if row['frame'] < self.last_frame:
            self.warn('frame_rollback_or_out_of_order_record', line)
            return False
        if kind == 'sample' and self.previous and row['frame'] == self.previous['frame']:
            self.warn('duplicate_sample_frame', line)
            return False
        if kind == 'gate' and not self.gate(row, line):
            return False
        if kind == 'sample':
            self.sample(row, line)
        if kind == 'end':
            self.end = row
        self.last_frame = row['frame']
        return True

    def finish(self):
        self.finish_gate_batch()
        observations = self.end['observations'] if self.end else None
        if self.end is None:
            self.warn('missing_end_eof_unflushed_gate_tail_unknown')
        if self.samples == 0:
            self.warn('missing_samples')
        if self.end and self.previous and self.end['frame'] > self.previous['frame']:
            self.warn('unsampled_end_tail_duration_unknown', damage=False)
        if observations is not None:
            if observations < self.lower_bound:
                self.warn('end_observation_count_inconsistent')
            elif observations > self.lower_bound:
                self.warn('observations_not_fully_located_by_samples', damage=False)
        totals = [sum(self.gates.get(t, {}).values()) for t in range(len(TACTICS))]
        if len(set(totals)) != 1:
            self.warn('gate_tactic_totals_disagree')
        gates = []
        for tactic in sorted(set(range(len(TACTICS))) | self.gates.keys()):
            bins = self.gates.get(tactic, {})
            total = sum(bins.values())
            if not total:
                self.warn('missing_tactic_gate_coverage')
            if observations is not None and total != observations:
                self.warn('gate_count_coverage_mismatch')
            if observations is None and total < self.lower_bound:
                self.warn('gate_coverage_short_of_known_observations')
            not_eval = bins.get(0, 0)
            unknown = sum(n for r, n in bins.items() if r >= len(REASONS))
            gates.append({'tactic': tactic, 'label': enum_label(TACTICS, tactic, 'tactic'),
                          'logged_updates': total, 'not_evaluated': not_eval,
                          'evaluated_logged_updates': total - not_eval - unknown,
                          'rejected_logged_updates': sum(n for r, n in bins.items() if r in REJECTED),
                          'unknown_reason_updates': unknown,
                          'reasons': {enum_label(REASONS, r, 'reason'): n for r, n in sorted(bins.items())},
                          'missing_vs_reported_observations': (max(0, observations - total)
                                                               if observations is not None else None),
                          'coverage': ('count_consistent_not_independently_verified'
                                       if observations is not None and total == observations
                                       else 'partial_or_unknown')})
        return {'segment': self.id, 'slot': self.slot,
                'context': ({k: self.begin[k] for k in ('stage', 'mode', 'match_kind', 'target', 'interval')}
                            if self.begin else None),
                'coverage': {'begin_seen': self.begin is not None, 'end_seen': self.end is not None,
                             'status': 'partial_or_inconsistent' if self.damaged else 'count_consistent_recording',
                             'first_record_frame': self.first_frame, 'last_record_frame': self.last_frame,
                             'accepted_sample_records': self.samples,
                             'recorder_reported_observations': observations,
                             'continuity_supported_observations_lower_bound': self.lower_bound,
                             'known_continuous_frames': self.known_frames,
                             'explicit_gap_samples': self.gaps,
                             'unflushed_gate_tail': 'unknown' if self.end is None else 'end_seen_check_counts'},
                'recording_end': ({'frame': self.end['frame'], 'lifecycle_reason_token': self.end['reason']}
                                  if self.end else None),
                'ego_range': self.ego, 'owns_sample_count': self.owns,
                'motions': {s: h.rows for s, h in self.motions.items()},
                'native_priorities': self.priorities.rows, 'custom_intents': self.intents.rows,
                'acknowledgment_and_event_samples': dict(self.events), 'gates': gates,
                'observed_changes': self.changes,
                'position_ranges_at_samples': self.positions,
                'fighter_flag_samples': {s: dict(v) for s, v in self.flags.items()},
                'recovery_motion_context_samples': dict(self.recovery), 'offstage': None,
                'timeline': self.timeline, 'timeline_omitted': self.samples - len(self.timeline),
                'warnings': self.warnings.export()}


def analyze_stream(stream, limits=None, labels=None, segment=None):
    """Analyze a binary file-like object. Never read more than a bounded chunk."""
    limits = limits or Limits()
    labels = labels or Labels()
    warnings = Warnings(limits.warnings)
    segments = {}
    highest = -1
    line = consumed = structured = accepted = rejected = legacy = 0
    limited = False

    def broken(code):
        nonlocal rejected
        rejected += 1
        warnings.add(code, line)
        # A malformed row cannot be assigned to an identity safely. Break all
        # open bridges, not merely the segment claimed by untrusted JSON.
        for value in segments.values():
            if value.end is None:
                value.warn('unreadable_or_rejected_record_continuity_unknown', line)

    while consumed < limits.file_bytes:
        chunk = stream.readline(min(limits.line_bytes + 1, limits.file_bytes - consumed))
        if not chunk:
            break
        line += 1
        consumed += len(chunk)
        if len(chunk) > limits.line_bytes:
            broken('line_byte_limit')
            while chunk and not chunk.endswith(b'\n') and consumed < limits.file_bytes:
                chunk = stream.readline(min(limits.line_bytes + 1, limits.file_bytes - consumed))
                consumed += len(chunk)
            continue
        marker = re.search(rb'(?<![A-Za-z0-9_])SBREC\s+', chunk)
        if not marker:
            if b'SBREC' in chunk:
                structured += 1
                broken('malformed_sbrec_transport')
            elif b'SHOWBOAT' in chunk:
                legacy += 1
            continue
        structured += 1
        if not chunk.endswith(b'\n'):
            warnings.add('unterminated_final_record_line', line)
        try:
            row, extras = validate(strict_json(chunk[marker.end():].decode('utf-8')))
        except UnicodeError:
            broken('invalid_utf8_record')
            continue
        except Invalid as exc:
            broken(str(exc))
            continue
        if extras:
            warnings.add('unknown_fields_ignored_not_outcome_evidence', line)
        sid = row['segment']
        if sid not in segments:
            if sid <= highest:
                broken('segment_id_not_monotonic')
                continue
            if len(segments) >= limits.segments:
                warnings.add('segment_limit_analysis_stopped', line)
                limited = True
                break
            highest = sid
            # Interleaved slots are valid, two open identities on one slot are not.
            for value in segments.values():
                if value.slot == row['slot'] and value.end is None and not value.superseded:
                    value.warn('new_segment_on_slot_without_end', line)
                    value.superseded = True
            value = segments[sid] = Segment(row, limits, labels, row['type'] == 'begin')
            if row['type'] == 'begin':
                accepted += 1
                continue
        value = segments[sid]
        if value.accept(row, line):
            accepted += 1
        else:
            rejected += 1
    if consumed >= limits.file_bytes:
        # Avoid even a one-byte overread: reaching the budget is conservatively
        # reported as partial, including an exactly budget-sized file.
        warnings.add('file_byte_limit_analysis_stopped', line)
        limited = True
    if limited:
        for value in segments.values():
            if value.end is None:
                value.warn('analysis_limit_tail_unknown', line)
    if not structured:
        warnings.add('no_structured_records_partial_legacy' if legacy else 'no_structured_records')
    if not labels.sources:
        warnings.add('motion_headers_unavailable_numeric_fallback')
    reports = [value.finish() for value in segments.values()]
    if segment is not None:
        reports = [value for value in reports if value['segment'] == segment]
        if not reports:
            warnings.add('requested_segment_not_found_in_scanned_records')
    return {'analysis_schema': 1, 'scope': 'recording_segments_not_match_results',
            'scan': {'bytes': consumed, 'lines': line, 'structured_candidates': structured,
                     'accepted_records': accepted, 'rejected_records': rejected,
                     'limited': limited, 'segments_seen': len(segments)},
            'legacy': {'logged_showboat_lines': legacy, 'coverage': 'unknown_not_complete'},
            'limits': dict(vars(limits)), 'motion_label_sources': labels.sources,
            'segments': reports, 'warnings': warnings.export(), 'notes': NOTES}


def metadata_context(data, completion):
    """Small, typed provenance whitelist; paths, argv and arbitrary text stay out.

    Even a command-looking string is only bounded JSON data, never executed or
    rendered as Markdown. Exit codes describe capture processes, not gameplay.
    """
    context = {}
    for key in ('dol_sha1', 'controller_config_sha1', 'git_commit'):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{40}', value):
            context[key] = value
    for key in ('recorder_marker_present', 'git_dirty'):
        if type(data.get(key)) is bool:
            context[key] = data[key]
    value = data.get('dol_size')
    if type(value) is int and 0 <= value <= 0xFFFFFFFF:
        context['dol_size'] = value
    for key in (('start_utc', 'end_utc') if completion else ('start_utc',)):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r'[0-9T:.+Z-]{1,64}', value):
            context[key] = value
    value = data.get('returncode')
    if completion and type(value) is int and -0x80000000 <= value <= 0x7FFFFFFF:
        context['returncode'] = value
    return context


def analyze_path(path, segment=None, limits=None):
    limits = limits or Limits()
    path = Path(path)
    capture = path.is_dir()
    log = path / 'runtime.log' if capture else path
    with log.open('rb') as stream:
        report = analyze_stream(stream, limits=limits, segment=segment)
    metadata = {'status': 'not_requested', 'used_for_statistics': False}
    if capture:
        def warn(code):
            report['warnings']['counts'][code] = report['warnings']['counts'].get(code, 0) + 1
            if len(report['warnings']['examples']) < limits.warnings:
                report['warnings']['examples'].append({'code': code, 'line': None})
            else:
                report['warnings']['examples_omitted'] += 1

        metadata.update(source=None, capture_status='live_or_incomplete', context={})
        for name in ('metadata', 'launch'):
            try:
                with (path / (name + '.json')).open('rb') as stream:
                    data = stream.read(limits.metadata_bytes + 1)
                if len(data) > limits.metadata_bytes:
                    raise Invalid('metadata_byte_limit')
                data = strict_json(data.decode('utf-8'), metadata=True)
                if not isinstance(data, dict):
                    raise Invalid('metadata_not_object')
            except FileNotFoundError:
                code = 'missing_' + name + ('_metadata' if name == 'launch' else '')
            except (OSError, UnicodeError, Invalid):
                code = 'invalid_or_oversize_' + name + ('_metadata' if name == 'launch' else '')
            else:
                completion = name == 'metadata'
                metadata.update(status='completion_metadata_context_only' if completion else
                                'launch_metadata_context_only', source=name + '.json',
                                context=metadata_context(data, completion))
                if completion:
                    metadata['capture_status'] = 'completion_manifest_present_not_outcome'
                break
            warn(code)
            if name == 'metadata':
                metadata['status'] = code
        if metadata['capture_status'] == 'live_or_incomplete':
            # Offline analysis cannot distinguish a running capture from SIGKILL.
            warn('capture_live_or_incomplete')
    report['metadata'] = metadata
    return report


def markdown(report):
    def display(value):
        return 'unknown' if value is None else str(value)

    def counts(values):
        return ', '.join('%s=%s' % (k, v) for k, v in values.items()) or 'none logged'

    lines = ['# Showboat recording analysis', '',
             'Recording segments only; **no match result or KO attribution**.',
             'Scanned %d bytes; %d accepted / %d rejected records.' %
             (report['scan']['bytes'], report['scan']['accepted_records'], report['scan']['rejected_records'])]
    if report.get('metadata', {}).get('capture_status'):
        lines += ['Capture metadata: %s (%s); context only, never a match outcome.' %
                  (report['metadata']['capture_status'], report['metadata']['source'] or 'unavailable')]
    if report['warnings']['counts']:
        lines += ['Warnings: ' + counts(report['warnings']['counts'])]
    if report['legacy']['logged_showboat_lines']:
        lines += ['Legacy SHOWBOAT lines logged: %d; partial diagnostics, coverage unknown (not complete).' %
                  report['legacy']['logged_showboat_lines']]
    for seg in report['segments']:
        cov = seg['coverage']
        lines += ['', '## Segment %d · CPU slot %d' % (seg['segment'], seg['slot']),
                  'Context: ' + (counts(seg['context']) if seg['context'] else 'unknown (missing begin)'),
                  'Coverage: %s; %d actual sample records; reported updates %s; '
                  'continuity-supported lower bound %d; known continuous frames %d.' %
                  (cov['status'], cov['accepted_sample_records'], display(cov['recorder_reported_observations']),
                   cov['continuity_supported_observations_lower_bound'], cov['known_continuous_frames']),
                  'End: ' + ('recording event `%s`, not a win.' % seg['recording_end']['lifecycle_reason_token']
                            if seg['recording_end'] else 'missing; EOF and unflushed gate tail unknown.'),
                  'Sampled ego range: %s; owns samples: %d.' % (display(seg['ego_range']), seg['owns_sample_count']),
                  'Custom intent samples: ' + counts({k: v.get('samples', 0) for k, v in seg['custom_intents'].items()}),
                  'Acknowledgments/events (not hits): ' + counts(seg['acknowledgment_and_event_samples'])]
        for side in ('self', 'rival'):
            changes = seg['observed_changes'][side]
            lines += ['**%s** motions (entries / boundary sightings / known frames): %s' %
                      (side, '; '.join('%s: %d/%d/%d' % (k, v.get('entries', 0),
                                                        v.get('boundary_sightings', 0), v.get('known_frames', 0))
                                      for k, v in seg['motions'][side].items()) or 'unknown'),
                      '%s: comparable net percent increases %s (%d pairs); stock endpoint changes %d '
                      '(%d decreases, %d increases; %d comparable pairs), not attributed KOs.' %
                      (side, display(changes['net_percent_increases']), changes['comparable_percent_pairs'],
                       changes['stock_change_pairs'], changes['stock_decreases'], changes['stock_increases'],
                       changes['stock_comparable_pairs']),
                      '%s sampled positions: %s; flags: %s; recovery-motion context samples: %d; offstage unknown.' %
                      (side, display(seg['position_ranges_at_samples'][side]), counts(seg['fighter_flag_samples'][side]),
                       seg['recovery_motion_context_samples'].get(side, 0))]
        lines += ['Native priority known frames: ' + counts({k: v.get('known_frames', 0)
                                                           for k, v in seg['native_priorities'].items()}),
                  '', '| Tactic | Logged updates | Not evaluated | Rejected | Reasons | Missing vs end |',
                  '|---|---:|---:|---:|---|---:|']
        for gate in seg['gates']:
            lines += ['| %s | %d | %d | %d | %s | %s |' %
                      (gate['label'], gate['logged_updates'], gate['not_evaluated'], gate['rejected_logged_updates'],
                       counts(gate['reasons']), display(gate['missing_vs_reported_observations']))]
        lines += ['', 'Timeline (first %d snapshots; %d omitted):' % (len(seg['timeline']), seg['timeline_omitted'])]
        # The complete bounded timeline is in JSON; keep default Markdown concise.
        for snap in seg['timeline'][:8]:
            lines += ['- f%d%s: %s / %s; intent %s; self (%g,%g), rival (%g,%g).' %
                      (snap['frame'], ' gap' if snap['gap'] else '', snap['self']['motion_label'],
                       snap['rival']['motion_label'], snap['intent'], snap['self']['x'], snap['self']['y'],
                       snap['rival']['x'], snap['rival']['y'])]
            if 'reason_labels' in snap:
                lines += ['  Reasons at this sampled update only: ' + counts(snap['reason_labels']) + '.']
        if len(seg['timeline']) > 8:
            lines += ['- %d further retained snapshots in JSON.' % (len(seg['timeline']) - 8)]
        if seg['warnings']['counts']:
            lines += ['Warnings: ' + counts(seg['warnings']['counts'])]
    lines += ['', '## Interpretation and limits'] + ['- ' + note for note in report['notes']]
    lines += ['- Resource limits: ' + counts(report['limits']) + '. Truncation/limits are reported, never silently complete.']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', type=Path,
                        help='runtime log or capture directory (runtime.log, launch.json, metadata.json)')
    parser.add_argument('--json', type=Path, metavar='OUTPUT', help='write machine-readable report')
    parser.add_argument('--markdown', type=Path, metavar='OUTPUT', help='write Markdown report')
    parser.add_argument('--segment', type=int, metavar='N', help='report only this capture-local segment ID')
    args = parser.parse_args(argv)
    if args.segment is not None and not 0 <= args.segment <= 0xFFFFFFFF:
        parser.error('--segment must be a nonnegative 32-bit integer')
    # Never overwrite the evidence, including through symlinks/hard links.
    evidence_dir = args.input if args.input.is_dir() else args.input.parent
    sources = [evidence_dir / name for name in ('runtime.log', 'metadata.json', 'launch.json')]
    if not args.input.is_dir():
        sources.append(args.input)
    outputs = [p for p in (args.json, args.markdown) if p is not None]
    try:
        for i, output in enumerate(outputs):
            for other in sources + outputs[:i]:
                if output.resolve() == other.resolve() or (output.exists() and other.exists() and output.samefile(other)):
                    parser.error('output must not overwrite an input or another report')
        report = analyze_path(args.input, segment=args.segment)
        text = markdown(report)
        if args.json:
            args.json.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if args.markdown:
            args.markdown.write_text(text, encoding='utf-8')
        if not outputs:
            sys.stdout.write(text)
    except OSError as exc:
        parser.exit(2, 'analyze_showboat: %s\n' % exc)
    return 0


if __name__ == '__main__':
    sys.exit(main())
