"""Marty Games - browse the ROM library and launch each game with the right core."""

import json
import os
import re
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
# Kodi puts one parent entry at the top of every plugin listing.
PARENT_ITEMS = 1
ARTWORK = os.path.normpath(os.path.join(ROMS, '..', 'artwork'))

# Built by tools/fetch_metadata.py and cached beside the artwork, so a reinstall
# of this add-on does not throw it away.
try:
    with open(os.path.join(ARTWORK, 'metadata.json'), encoding='utf-8') as _fh:
        METADATA = json.load(_fh)
except (OSError, ValueError):
    METADATA = {}

SEP = '   \u00b7   '

# Kodi sorts labels with "ignore articles when sorting" on by default, so its
# order and ours have to agree or the A-Z offsets below point at the wrong row.
_ARTICLE = re.compile(r'^(the|a|an)\s+', re.I)


def sort_key(title):
    return _ARTICLE.sub('', title).lower()


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
    # A home-screen tile opens the detail page rather than launching, so the
    # Play row there is what starts the game - that is the only path carrying
    # the gameclient property, which is what skips the emulator picker.
    li.setProperty('marty_info', url(action='info', key=game['system'],
                                     title=game['title']))
    describe(li, game, system)
    art = {}
    boxart = os.path.join(ARTWORK, game['system'], game['title'] + '.png')
    if os.path.exists(boxart):
        art.update(poster=boxart, thumb=boxart)
    # An in-game screenshot as fanart: the home rows each draw one full-bleed
    # image behind the hero text, and games were the only row without one.
    snap = os.path.join(ARTWORK, 'snaps', game['system'], game['title'] + '.png')
    if os.path.exists(snap):
        art['fanart'] = snap
    if art:
        li.setArt(art)
    return li


def describe(li, game, system):
    """Fill the hero area under a focused tile.

    The lines are composed here rather than in the skin because a skin can only
    concatenate: a missing publisher would strand its separator. They are plain
    properties because ListItem.Plot does not resolve for a game item - Kodi
    serves a game tag through RetroPlayer.* labels only (GamesGUIInfo.cpp has no
    LISTITEM_ case at all), and giving the item a video tag to reach Plot would
    make VIDEO::IsVideo() true and put the ROM in front of the video player.
    """
    meta = METADATA.get(game['system'], {}).get(game['title'])
    if not meta:
        return {}
    genres = ', '.join(g for g in meta.get('genres', '').split('; ') if g)
    players = meta.get('players')
    if players:
        players = '%s player%s' % (players, '' if players == '1' else 's')
    facts = [f for f in (meta.get('year'), system.label if system else None,
                         genres, players) if f]
    if facts:
        li.setProperty('facts_line', SEP.join(facts))
    # Most games are self-published; saying the same name twice reads as an error.
    people = [p for p in (meta.get('developer'), meta.get('publisher')) if p]
    if len(people) == 2 and people[0] == people[1]:
        people.pop()
    if people:
        li.setProperty('people_line', SEP.join(people))
    if meta.get('overview'):
        li.setProperty('plot_line', meta['overview'])
    lines = {'facts_line': SEP.join(facts) if facts else '',
             'people_line': SEP.join(people) if people else '',
             'plot_line': meta.get('overview', '')}

    try:
        tag = li.getGameInfoTag()
        tag.setDeveloper(meta.get('developer', ''))
        tag.setPublisher(meta.get('publisher', ''))
        tag.setOverview(meta.get('overview', ''))
        if genres:
            tag.setGenres(genres.split(', '))
        if meta.get('year', '').isdigit():
            tag.setYear(int(meta['year']))
    except AttributeError:
        pass
    return lines


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


def list_games(games, category, sort=True, detail=True):
    xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'games')
    if sort:
        games = sorted(games, key=lambda g: sort_key(g['title']))
    letters = {}
    for index, game in enumerate(games):
        first = (sort_key(game['title'])[:1] or '?').upper()
        if not first.isalpha():
            first = '#'
        # Where each letter starts, so the skin's A-Z strip can jump to it
        # rather than filter to it - picking Z should leave you somewhere you
        # can scroll on from. Offset by the parent entry Kodi puts at the top
        # of every plugin listing, which occupies position zero.
        letters.setdefault(first, index + PARENT_ITEMS)
        # In a browse window the tile opens the detail page; from a home row
        # the same item still launches directly, through marty_click.
        #
        # Direct ROM path when it is playable. Routing playback through the
        # plugin does not work: RetroPlayer will not resolve a plugin:// URL,
        # and Player().play() from a plugin context never starts (verified
        # again through RunPlugin). The gameclient property is what selects the
        # emulator; the scanner avoids extensions Kodi hijacks.
        if detail:
            xbmcplugin.addDirectoryItem(
                HANDLE, url(action='info', key=game['system'],
                            title=game['title']), make_item(game), True)
        else:
            xbmcplugin.addDirectoryItem(HANDLE, game['path'], make_item(game),
                                        False)
    # Recently Played is already in the order we want; a sort method would let
    # Kodi re-order it back to alphabetical - and an A-Z strip over a listing
    # sorted by when you last played is meaningless, so it only goes on the
    # listings that are actually alphabetical.
    if sort:
        # NONE, not LABEL: Kodi would re-sort the list out from under the
        # offsets just computed - its label sort drops leading articles, ours
        # does too, but only one of them can own the final order.
        xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.setProperty(HANDLE, 'alphabet', '1')
        for name, index in letters.items():
            xbmcplugin.setProperty(HANDLE, 'letter_index_' + name, str(index))
    xbmcplugin.endOfDirectory(HANDLE)


def show_game(key, title):
    """One game on its own page: art, facts and a single Play row.

    A listing rather than a dialog, deliberately. Selecting the Play row goes
    through the container's own click, which is the only path that carries the
    gameclient property to RetroPlayer - a dialog button would have to fake that
    click, and CGUIMediaWindow only launches on a GUI_MSG_CLICKED whose param is
    ACTION_SELECT_ITEM, which SendClick does not send. Back then works by
    itself, because it is just a folder you stepped into.
    """
    system = BY_KEY.get(key)
    game = None
    if system:
        game = next((g for g in scanner.scan_system(ROMS, system)
                     if g['title'] == title), None)
    if game is None:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    xbmcplugin.setPluginCategory(HANDLE, game['title'])
    xbmcplugin.setContent(HANDLE, 'games')
    li = make_item(game)
    li.setLabel('Play')
    # On the container, not just the item: Kodi puts a parent row above the
    # Play row, and the page must read the same whichever of the two has focus.
    for name in ('facts_line', 'people_line', 'plot_line'):
        xbmcplugin.setProperty(HANDLE, 'game_' + name, li.getProperty(name))
    poster = os.path.join(ARTWORK, game['system'], game['title'] + '.png')
    if os.path.exists(poster):
        xbmcplugin.setProperty(HANDLE, 'game_poster', poster)
    snap = os.path.join(ARTWORK, 'snaps', game['system'], game['title'] + '.png')
    if os.path.exists(snap):
        xbmcplugin.setProperty(HANDLE, 'game_fanart', snap)
    xbmcplugin.addDirectoryItem(HANDLE, game['path'], li, False)
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
        list_games(list(scanner.scan_all(ROMS)), 'All Games')
    elif action == 'info':
        show_game(args.get('key', ''), args.get('title', ''))
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
