"""Explicit controller roles; raw Slippi player indices are never renumbered."""


def validate_bot_port(port):
    if type(port) is not int or port not in (1,2):
        raise ValueError('Bot controller port must be 1 or 2')
    return port


def record_bot_port(row, expected=None):
    if 'bot_port' in row and (type(row.get('schema_version')) is not int or row['schema_version'] != 5):
        raise ValueError('Explicit player roles require frame schema 5')
    if row.get('schema_version',4) == 5:
        if 'bot_port' not in row:
            raise ValueError('Frame schema 5 requires explicit controller roles')
        port = validate_bot_port(row['bot_port'])
    else:
        port = 1
    if expected is not None and port != validate_bot_port(expected):
        raise ValueError('Recorded controller role differs from launch')
    return port


def raw_fighter(row, *, opponent=False):
    port = record_bot_port(row)
    return row['raw_observation']['players'][str(3-port if opponent else port)]['raw_post']
