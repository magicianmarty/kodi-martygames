"""Marty Games - browse the ROM library and launch each game with the right core."""

import os
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import scanner
from resources.lib.systems import BY_KEY, SYSTEMS

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
ADDON = xbmcaddon.Addon()
ROMS = ADDON.getSetting('rom_path') or '/storage/sdcard/roms'
SAVES = xbmcvfs.translatePath('special://home/saves')
RECENT_LIMIT = 20


def url(**kwargs):
    return BASE + '?' + urlencode(kwargs)


def log(msg):
    xbmc.log('[martygames] %s' % msg, xbmc.LOGINFO)


def quote(value):
    """Quote a path for a Kodi builtin: params are split on unquoted commas."""
    return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')


def last_played(path):
    """When this game was last opened, from the savestate directory Kodi creates.

    Kodi makes special://home/saves/<rom filename>/ the moment a game is opened
    and writes into it while it plays, so the directory's mtime is a last-played
    stamp for free - no play tracking of our own, and it survives a reinstall of
    this add-on. It is created even when the core cannot serialise (dosbox-pure
    fails every save), which is what we want: the game was still played.
    """
    try:
        return os.path.getmtime(os.path.join(SAVES, os.path.basename(path)))
    except OSError:
        return 0.0


def make_item(game):
    """Build a playable ListItem with the emulator core pinned to it."""
    li = xbmcgui.ListItem(label=game['title'])
    li.setPath(game['path'])
    li.setIsFolder(False)
    li.setProperty('IsPlayable', 'true')
    # RetroPlayer reads this to skip the "select emulator" dialog and to avoid
    # resuming a savestate under whichever core happened to open the file first.
    li.setProperty('gameclient', game['core'])
    system = BY_KEY.get(game['system'])
    try:
        tag = li.getGameInfoTag()
        tag.setTitle(game['title'])
        tag.setGameClient(game['core'])
        if system:
            tag.setPlatform(system.platform)
    except AttributeError:
        pass  # older Kodi without InfoTagGame; the property above still works
    li.setProperty('marty_click', 'PlayMedia(%s)' % quote(game['path']))
    art = os.path.join(ROMS, '..', 'artwork', game['system'],
                       game['title'] + '.png')
    art = os.path.normpath(art)
    if os.path.exists(art):
        li.setArt({'poster': art, 'thumb': art})
    return li


def list_root():
    xbmcplugin.setPluginCategory(HANDLE, 'Games')
    present = []
    for system in SYSTEMS:
        if os.path.isdir(os.path.join(ROMS, system.key)):
            games = list(scanner.scan_system(ROMS, system))
            if games:
                present.append((system, len(games)))

    total = sum(n for _, n in present)
    li = xbmcgui.ListItem(label='Recently Played')
    li.setArt({'icon': 'DefaultAddonGame.png'})
    xbmcplugin.addDirectoryItem(HANDLE, url(action='recent'), li, isFolder=True)

    li = xbmcgui.ListItem(label='All Games')
    li.setArt({'icon': 'DefaultAddonGame.png'})
    li.setProperty('total', str(total))
    xbmcplugin.addDirectoryItem(HANDLE, url(action='all'), li, isFolder=True)

    for system, count in present:
        li = xbmcgui.ListItem(label='%s  (%d)' % (system.label, count))
        li.setArt({'icon': 'DefaultAddonGame.png'})
        xbmcplugin.addDirectoryItem(
            HANDLE, url(action='system', key=system.key), li, isFolder=True)

    xbmcplugin.endOfDirectory(HANDLE)


def list_games(games, category, sort=True):
    xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'games')
    for game in games:
        # Direct ROM path. Routing playback through the plugin does not work:
        # RetroPlayer will not resolve a plugin:// URL, and Player().play() from
        # a plugin context never starts. The gameclient property below is what
        # selects the emulator; the scanner avoids extensions Kodi hijacks.
        xbmcplugin.addDirectoryItem(HANDLE, game['path'], make_item(game), False)
    # Recently Played is already in the order we want; a sort method would let
    # Kodi re-order it back to alphabetical.
    if sort:
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(HANDLE)


def play(path, core):
    """Start the game ourselves instead of letting Kodi route by extension.

    Kodi picks a player from the file type before any game client is
    considered: .m3u is treated as a video playlist (it tries to demux each
    .adf), .zip goes to the picture viewer and .bin to the video player. Only
    .adf/.nes/.wad/.gen are unambiguous. Driving Player().play() with a
    ListItem that carries the gameclient bypasses all of that.
    """
    li = xbmcgui.ListItem(label=os.path.basename(path), path=path)
    li.setProperty('gameclient', core)
    try:
        li.getGameInfoTag().setGameClient(core)
    except AttributeError:
        pass
    log('launching %s with %s' % (path, core))
    xbmc.Player().play(path, li)


def main():
    args = dict(parse_qsl(sys.argv[2][1:]))
    action = args.get('action')

    if action == 'system':
        system = BY_KEY.get(args.get('key', ''))
        if not system:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
        list_games(list(scanner.scan_system(ROMS, system)), system.label)
    elif action == 'all':
        list_games(sorted(scanner.scan_all(ROMS), key=lambda g: g['title'].lower()),
                   'All Games')
    elif action == 'recent':
        played = [(last_played(g['path']), g) for g in scanner.scan_all(ROMS)]
        played = sorted((p for p in played if p[0]), key=lambda p: p[0], reverse=True)
        list_games([g for _, g in played[:RECENT_LIMIT]], 'Recently Played', sort=False)
    elif action == 'play':
        play(args['path'], args['core'])
    else:
        list_root()


if __name__ == '__main__':
    main()
