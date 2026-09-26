"""Verified regulation/Sudden Death boundaries and contest-level results."""

import time

from .replay import expected_settings, summarize_file
from .rules import TIME_LIMIT_SECONDS, SIMULATION_FPS


class MatchBoundaryError(ValueError):
    pass


def start_segment(number, match_number, phase, frame, now, start_index, settings):
    if frame != -123 or start_index != number or not expected_settings(settings,phase=phase):
        raise MatchBoundaryError('unverified_segment_start')
    return {'episode':number,'match_number':match_number,'phase':phase,
        'start_event_index':start_index,'start_settings':settings,
        'first_frame':frame,'last_frame':frame,'observations':0,'gaps':0,
        'duplicates':0,'rollbacks':0,'started_monotonic':now}


def record_observation(episode, current, stocks, now):
    if episode['observations']:
        delta = current-episode['last_frame']
        episode['gaps'] += max(0,delta-1)
        episode['duplicates'] += int(delta == 0)
        episode['rollbacks'] += int(delta < 0)
    episode.update(last_frame=current,last_monotonic=now,last_stocks=stocks)
    elapsed = now-episode['started_monotonic']
    episode['simulation_fps'] = (current-episode['first_frame'])/elapsed if elapsed else None
    episode['observations'] += 1


def completed_replay(run_dir, episode_number, phase):
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        paths = sorted((run_dir/'replays').glob('*.slp'))
        if len(paths) >= episode_number:
            try:
                replay = summarize_file(paths[episode_number-1], 268435456)
                if replay['outcome'] in ('game','time') and expected_settings(replay['settings'],phase=phase):
                    return replay
            except (OSError,ValueError,KeyError):
                pass
        time.sleep(.1)
    raise MatchBoundaryError('segment_end_or_settings_unverified')


def verify_sudden_death(previous, replay, settings, frame, stocks, percents, start_index):
    if (previous.get('phase','regulation') != 'regulation' or
            previous['last_frame'] < TIME_LIMIT_SECONDS*SIMULATION_FPS or
            replay['outcome'] != 'time' or not expected_settings(replay['settings']) or
            not expected_settings(settings,phase='sudden_death') or frame != -123 or
            stocks != [1,1] or percents != [300.,300.] or
            len(previous['last_stocks']) != 2 or previous['last_stocks'][0] < 1 or
            previous['last_stocks'][0] != previous['last_stocks'][1] or
            start_index != previous['start_event_index']+1):
        raise MatchBoundaryError('unverified_sudden_death_boundary')


def replay_layout_valid(episodes, replays, *, complete=False, expected_matches=None):
    """One replay per segment; one completed contest per final result only."""
    if not episodes or len(episodes) != len(replays):
        return False
    match_number = completed = 0
    previous = None
    try:
        for index, (episode,replay) in enumerate(zip(episodes,replays),1):
            phase = episode.get('phase','regulation')
            if episode['episode'] != index or not expected_settings(replay['settings'],phase=phase):
                return False
            if episode.get('start_settings',replay['settings']) != replay['settings']:
                return False
            if phase == 'regulation':
                if previous and not previous.get('match_completed',previous.get('result_event_verified')):
                    return False
                match_number += 1
            elif (not previous or previous.get('phase','regulation') != 'regulation' or
                    previous.get('continued_as_sudden_death') is not True):
                return False
            if episode.get('match_number',index) != match_number:
                return False
            verified = episode.get('result_event_verified') is True
            continued = episode.get('continued_as_sudden_death') is True
            if verified:
                if replay['outcome'] not in ('game','time'):
                    return False
                if episode.get('replay_sha256',replay['sha256']) != replay['sha256']:
                    return False
                if continued:
                    if (phase != 'regulation' or replay['outcome'] != 'time' or
                            episode.get('winner_port') is not None or episode.get('match_completed')):
                        return False
                else:
                    if (replay['winner_port'] not in (1,2) or episode.get('winner_port') != replay['winner_port'] or
                            not episode.get('match_completed',True) or
                            (phase == 'sudden_death' and replay['outcome'] != 'game')):
                        return False
                    if replay['outcome'] == 'time' and len(set(episode['last_stocks'])) == 1:
                        return False
                    completed += 1
            elif complete or index != len(episodes) or continued:
                return False
            previous = episode
        if previous.get('continued_as_sudden_death'):
            return False
        return not complete or completed == match_number == expected_matches
    except (KeyError,TypeError,ValueError):
        return False
