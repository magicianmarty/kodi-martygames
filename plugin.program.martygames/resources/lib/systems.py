"""System definitions: which core plays what, and which files are games."""


class System:
    def __init__(self, key, label, core, exts, platform,
                 prefer=(), skip_exts=(), folder_games=False):
        self.key = key
        self.label = label
        self.core = core
        self.exts = exts
        self.platform = platform
        # when a game has several candidate files, these extensions win
        self.prefer = prefer
        self.skip_exts = skip_exts
        # DOS games are directories containing an executable, not single files
        self.folder_games = folder_games


SYSTEMS = [
    System('amiga', 'Amiga', 'game.libretro.uae',
           # No .m3u: Kodi treats it as a VIDEO PLAYLIST and tries to demux each
           # .adf ("Open - probing detected format [adf]" then CVideoPlayer),
           # so it never reaches PUAE. Point at disk 1 and use RetroPlayer's
           # disc control to swap; the .m3u files stay on disk unused.
           ('.adf', '.adz', '.dms', '.ipf', '.lha'),
           'Commodore Amiga'),
    # No .zip: Genesis Plus GX reports "Supports VFS: false" and its valid
    # extensions are m3u|mdx|md|smd|gen|bin|cue|iso|chd|... - a zipped ROM
    # simply fails with "Unable to open file". ROMs must be unpacked.
    System('megadrive', 'Mega Drive', 'game.libretro.genplus',
           ('.md', '.gen', '.bin', '.smd', '.sms', '.gg', '.chd', '.cue'),
           'Sega Mega Drive'),
    # No .m3u, for the same reason as Amiga: Kodi routes it to CVideoPlayer
    # before any game client is considered. Verified on Metal Gear Solid - the
    # playlist opened in the video player and the game never started. Multi-disc
    # sets therefore start on disc 1's .cue; the .m3u files stay on disk unused.
    System('psx', 'PlayStation', 'game.libretro.pcsx-rearmed',
           ('.cue', '.pbp', '.chd'), 'Sony PlayStation',
           prefer=('.cue',), skip_exts=('.bin', '.img')),
    System('nes', 'NES', 'game.libretro.nestopia',
           ('.nes', '.fds', '.unf'), 'Nintendo NES'),
    System('snes', 'SNES', 'game.libretro.snes9x',
           ('.sfc', '.smc', '.zip'), 'Nintendo SNES'),
    # Needs hardware rendering: mupen64plus-nx is the only installed client that
    # calls SET_HW_RENDER, so it does nothing until the FBO renderer works.
    System('n64', 'Nintendo 64', 'game.libretro.mupen64plus-nx',
           ('.z64', '.n64', '.v64'), 'Nintendo 64'),
    System('c64', 'Commodore 64', 'game.libretro.vice_x64',
           ('.d64', '.nib', '.t64', '.prg', '.crt', '.g64', '.tap'), 'Commodore 64'),
    System('dos', 'DOS', 'game.libretro.dosbox-pure',
           ('.exe', '.com', '.bat'), 'MS-DOS', folder_games=True),
    System('doom', 'Doom', 'game.libretro.prboom',
           ('.wad',), 'DOS'),
    System('quake', 'Quake', 'game.libretro.tyrquake',
           ('.pak',), 'DOS'),
    System('arcade', 'Arcade', 'game.libretro.mame2003_plus',
           ('.zip',), 'Arcade'),
    System('scummvm', 'ScummVM', 'game.libretro.scummvm',
           ('.scummvm',), 'ScummVM'),
]

BY_KEY = {s.key: s for s in SYSTEMS}

# Files that are never games, whatever their extension.
EXCLUDE_NAMES = {
    'deice.exe', 'install.exe', 'install.bat', 'setup.exe', 'setup.bat',
    'uninstall.exe', 'unins000.exe', 'dosbox.exe', 'modem.cfg',
}

# DOS folders often ship several executables; prefer one that looks like the game.
DOS_EXE_BLOCKLIST = (
    'install', 'instl', 'setup', 'deice', 'unins', 'dosbox', 'config', 'readme',
    'sysinfo', 'edit', 'view', 'help',
    # DOS extenders and bundled utilities that sit next to the real game
    'dos4gw', 'dos32a', 'dos32', 'setsound', 'smkplay', 'mssw', 'mss',
    'patch', 'sbtest', 'modem', 'univbe', 'cwsdpmi', 'pkunzip', 'test',
    # manuals, intros, cheats and helpers that outweigh the real game on size
    'guide', 'info', 'intro', 'cheat', 'cht', 'trainer', 'mouse', 'order', 'manual',
    'demo', 'insthd', 'terrtron', 'fix', 'nosound',
)
