"""Games that live on a Windows host and arrive over Moonlight.

They have no ROM on disk, so the scanner cannot find them: the list is
declared in resources/pc.json and each entry names a Sunshine app.
"""

import json
import os

KEY = 'pc'
LABEL = 'PC'
PLATFORM = 'Windows'


def load(resources_dir):
    """(host, stream_opts, [{'title','app','system'}]) - empty list if absent."""
    path = os.path.join(resources_dir, 'pc.json')
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return '', {}, []

    games = [{'title': g['title'], 'app': g['app'], 'system': KEY}
             for g in data.get('games', []) if g.get('title') and g.get('app')]
    return data.get('host', ''), data.get('stream', {}), games


def stream_args(script, app, host, opts):
    return [script, app, host,
            str(opts.get('resolution', '1080')),
            str(opts.get('fps', '60')),
            str(opts.get('bitrate', 20000)),
            str(opts.get('codec', 'h264'))]
