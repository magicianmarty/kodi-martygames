"""Per-game emulator settings, and a menu you can read.

Core settings in Kodi are per-emulator and global: turning a game up to 4x
resolution turns every game on that system up, and the built-in add-on settings
dialog shows a list of values without indicating which one is in force. This
keeps a setting per game and presents the current value in the label.

Settings are applied through xbmcaddon.Addon(core).setSetting() rather than by
writing the core's settings.xml. Kodi caches an add-on's settings once loaded,
so a file written behind its back is not seen until it reloads - that is why
changing settings.xml by hand needs a Kodi restart.
"""

import json
import os
from xml.etree import ElementTree

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
STORE = os.path.join(PROFILE, 'game_settings.json')


class Option:
    def __init__(self, key, label, values, labels=None):
        self.key = key
        self.label = label
        self.values = values
        self.labels = labels or values

    def label_for(self, value):
        try:
            return self.labels[self.values.index(value)]
        except ValueError:
            return value


# Only the settings worth reaching for mid-session; the rest stay in the core's
# own dialog. Ids and values are copied from each add-on's resources/settings.xml
# - a value outside the declared set is rejected by UpdateSettingString and
# surfaces as WrongTypeException.
OPTIONS = {
    'n64': [
        Option('mupen64plus-rdp-plugin', 'Renderer',
               ['gliden64', 'angrylion', 'parallel'],
               ['GLideN64 (hardware, fast)', 'Angrylion (accurate, software)',
                'ParaLLEl']),
        Option('mupen64plus-rsp-plugin', 'RSP',
               ['hle', 'parallel', 'cxd4'],
               ['HLE (pair with GLideN64)', 'ParaLLEl (pair with Angrylion)',
                'CXD4 (accurate, slow)']),
        Option('mupen64plus-43screensize', 'Resolution (4:3)',
               ['320x240', '640x480', '960x720', '1280x960', '1440x1080', '1920x1440'],
               ['320x240 (half)', '640x480 (native)', '960x720 (1.5x)',
                '1280x960 (2x)', '1440x1080 (2.25x)', '1920x1440 (3x)']),
        Option('mupen64plus-169screensize', 'Resolution (16:9)',
               ['640x360', '960x540', '1280x720', '1920x1080'],
               ['640x360', '960x540 (native)', '1280x720 (720p)', '1920x1080 (1080p)']),
        Option('mupen64plus-aspect', 'Aspect', ['4:3', '16:9', '16:9 adjusted'],
               ['4:3 (as the N64 output)', '16:9 (widescreen hack)',
                '16:9 adjusted']),
    ],
    'psp': [
        Option('ppsspp_internal_resolution', 'Resolution',
               ['480x272', '960x544', '1440x816', '1920x1088'],
               ['480x272 (native)', '960x544 (2x)', '1440x816 (3x)',
                '1920x1088 (4x)']),
        Option('ppsspp_cpu_core', 'CPU core', ['JIT', 'IR JIT', 'Interpreter'],
               ['JIT (fastest)', 'IR JIT (more compatible)',
                'Interpreter (slowest)']),
        Option('ppsspp_frameskip', 'Frame skip', ['disabled', '1', '2', '3'],
               ['Off', '1 frame', '2 frames', '3 frames']),
    ],
    'dreamcast': [
        Option('reicast_internal_resolution', 'Resolution',
               ['320x240', '640x480', '800x600', '960x720', '1280x960'],
               ['320x240 (half)', '640x480 (native)', '800x600', '960x720 (1.5x)',
                '1280x960 (2x)']),
    ],
    'psx': [
        Option('pcsx_rearmed_frameskip_type', 'Frame skip',
               ['disabled', 'auto', 'auto_threshold', 'fixed_interval'],
               ['Off', 'Automatic', 'Automatic (threshold)', 'Fixed interval']),
    ],
}


# RetroPlayer settings, as opposed to core settings. These reach Kodi as
# properties on the home window, read when playback starts - see Kodi patches
# 1038 and 1039. The add-on cannot set them any other way: <defaultgamesettings>
# lives in guisettings.xml, which Kodi caches and rewrites on exit, and
# advancedsettings.xml is parsed once at startup.
PLAYER_PROPERTY = {
    'videofilter': 'retroplayer.videofilter',
    'stretchmode': 'retroplayer.stretchmode',
    'runahead': 'retroplayer.runahead',
}

# Drawn by CRPRendererFBO, which has no shader chain - only CRPRendererOpenGLES
# runs presets. Offering shaders here would silently do nothing.
HW_RENDERED = {'n64', 'psp', 'dreamcast'}

PRESETS_XML = ('special://home/addons/game.shader.presets/resources/'
               'ShaderPresetsGLSLP_GLES.xml')

STRETCH = Option('stretchmode', 'Screen fit',
                 ['normal', '4:3', '16:9', 'integer', 'fullscreen', 'original'],
                 ['Normal (as the game intended)', 'Stretch to 4:3',
                  'Stretch to 16:9', 'Integer scale (sharpest)',
                  'Fill the screen', 'Original size'])

RUNAHEAD = Option('runahead', 'Run-ahead',
                  ['0', '1', '2', '3'],
                  ['Off', '1 frame (less input lag)', '2 frames',
                   '3 frames (needs a fast core)'])


def _shader_presets():
    """The presets Kodi itself will accept, read from the add-on's manifest.

    Parsed rather than hardcoded: the manifest is the same list the in-game
    dialog builds from, and a path Kodi has not listed there will be set
    without complaint and then quietly not render.
    """
    path = xbmcvfs.translatePath(PRESETS_XML)
    if not os.path.exists(path):
        return []
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError) as exc:
        xbmc.log('martygames: cannot read shader presets: %s' % exc, xbmc.LOGWARNING)
        return []

    base = os.path.dirname(path)
    out = []
    for preset in tree.getroot().iter('preset'):
        rel = preset.findtext('path', '').strip()
        name = preset.findtext('name', '').strip()
        folder = preset.findtext('folder', '').strip()
        if not rel or not name:
            continue
        label = '%s - %s' % (folder, name) if folder else name
        out.append((os.path.join(base, rel), label))
    return out


def player_options(system_key):
    """Run-ahead and aspect everywhere; shaders only where they can render."""
    options = [RUNAHEAD, STRETCH]
    if system_key in HW_RENDERED:
        return options
    presets = _shader_presets()
    values = ['nearest', 'linear'] + [p for p, _ in presets]
    labels = ['Sharp (no filtering)', 'Smooth (bilinear)'] + [l for _, l in presets]
    options.insert(0, Option('videofilter', 'Shader', values, labels))
    return options


def _player_default(key):
    if key == 'runahead':
        return '0'
    if key == 'stretchmode':
        return 'normal'
    return 'nearest'


def clear_player_overrides():
    """Drop any per-game player settings left on the home window.

    They outlive the listing that set them, so without this a game launched
    straight from a home row - which never runs this add-on - would inherit
    whatever the last game opened through the detail page asked for.
    """
    home = xbmcgui.Window(10000)
    for prop in PLAYER_PROPERTY.values():
        home.clearProperty(prop)


def _load():
    try:
        with open(STORE, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(data):
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(STORE, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
    except OSError as exc:
        xbmc.log('martygames: cannot save game settings: %s' % exc, xbmc.LOGWARNING)


def _game_key(system_key, title):
    return '%s/%s' % (system_key, title)


def stored_for(system_key, title):
    return _load().get(_game_key(system_key, title), {})


def options_for(system):
    """Everything adjustable for this system, core settings first."""
    return OPTIONS.get(system.key, []) + player_options(system.key)


def current(core, option, overrides):
    """What this game will actually run with: its override, else the default."""
    if option.key in overrides:
        return overrides[option.key]
    if option.key in PLAYER_PROPERTY:
        return _player_default(option.key)
    try:
        return xbmcaddon.Addon(core).getSetting(option.key)
    except Exception:  # noqa: BLE001 - core may not be installed
        return ''


def apply(system, title):
    """Push this game's overrides out before it is launched.

    The player properties are always written, cleared included: they live on the
    home window for the life of the session, so leaving one set would carry a
    previous game's shader or run-ahead into the next one.
    """
    overrides = stored_for(system.key, title)

    home = xbmcgui.Window(10000)
    for key, prop in PLAYER_PROPERTY.items():
        home.setProperty(prop, overrides.get(key, ''))

    core_overrides = {k: v for k, v in overrides.items() if k not in PLAYER_PROPERTY}
    if not core_overrides:
        return

    try:
        addon = xbmcaddon.Addon(system.core)
    except Exception:  # noqa: BLE001
        xbmc.log('martygames: %s not installed, settings not applied' % system.core,
                 xbmc.LOGWARNING)
        return

    for key, value in core_overrides.items():
        try:
            addon.setSetting(key, value)
        except Exception as exc:  # noqa: BLE001
            xbmc.log('martygames: could not set %s=%s: %s' % (key, value, exc),
                     xbmc.LOGWARNING)

    xbmc.log('martygames: applied %d setting(s) for %s' % (len(overrides), title),
             xbmc.LOGINFO)


def menu(system, title):
    """Show the settings for one game, with the value in force on each line."""
    options = options_for(system)
    if not options:
        xbmcgui.Dialog().notification('Marty Games',
                                      'No adjustable settings for %s' % system.label,
                                      xbmcgui.NOTIFICATION_INFO, 3000)
        return

    while True:
        overrides = stored_for(system.key, title)
        rows = []
        for option in options:
            value = current(system.core, option, overrides)
            # A core setting the user has never touched is absent from its
            # settings.xml, which reads back as empty rather than as the
            # default declared in the add-on.
            shown = option.label_for(value) if value else 'Core default'
            mark = '[COLOR yellow]*[/COLOR] ' if option.key in overrides else '  '
            rows.append('%s%s:  [B]%s[/B]' % (mark, option.label, shown))

        if overrides:
            rows.append('[COLOR grey]Clear this game\'s settings (%d)[/COLOR]' % len(overrides))

        choice = xbmcgui.Dialog().select('%s - settings' % title, rows)
        if choice < 0:
            return

        if choice == len(options):
            data = _load()
            data.pop(_game_key(system.key, title), None)
            _save(data)
            apply(system, title)
            continue

        option = options[choice]
        value = current(system.core, option, overrides)
        preselect = option.values.index(value) if value in option.values else -1

        picked = xbmcgui.Dialog().select(option.label, option.labels, preselect=preselect)
        if picked < 0:
            continue

        data = _load()
        game = data.setdefault(_game_key(system.key, title), {})
        game[option.key] = option.values[picked]
        _save(data)
        apply(system, title)
