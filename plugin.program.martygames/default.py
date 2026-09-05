"""Marty Games - browse the ROM library and launch each game with the right core."""

import os
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib import scanner
from resources.lib.systems import BY_KEY, SYSTEMS

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
ADDON = xbmcaddon.Addon()
ROMS = ADDON.getSetting('rom_path') or '/storage/sdcard/roms'


def url(**kwargs):
    return BASE + '?' + urlencode(kwargs)


def log(msg):
    xbmc.log('[martygames] %s' % msg, xbmc.LOGINFO)


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
    # Artwork lands here in phase 2; the skin resolves poster -> thumb -> landscape.
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


def list_games(games, category):
    xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'games')
    for game in games:
        # Point straight at the ROM. RetroPlayer will not resolve a plugin://
        # URL - it hands the URL itself to the core, which then reports
        # "Unable to open file". The gameclient property on the ListItem is what
        # selects the game player, so extension-based routing (.zip to the
        # picture viewer, .bin to the video player) does not apply here.
        xbmcplugin.addDirectoryItem(HANDLE, game['path'], make_item(game), False)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(HANDLE)


def play(path, core):
    li = xbmcgui.ListItem(path=path)
    li.setProperty('gameclient', core)
    try:
        li.getGameInfoTag().setGameClient(core)
    except AttributeError:
        pass
    log('launching %s with %s' % (path, core))
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


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
    elif action == 'play':
        play(args['path'], args['core'])
    else:
        list_root()


if __name__ == '__main__':
    main()
