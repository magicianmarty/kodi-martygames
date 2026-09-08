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
    # HuCard and CD in one core - beetle-pce-fast is built with HAVE_CDROM=1,
    # so TurboGrafx-CD works from the same entry.
    System('tg16', 'TurboGrafx-16', 'game.libretro.beetle-pce-fast',
           ('.pce', '.chd', '.cue', '.ccd', '.m3u'), 'NEC TurboGrafx-16',
           prefer=('.chd', '.cue'), skip_exts=('.bin', '.img')),
    System('snes', 'SNES', 'game.libretro.snes9x',
           ('.sfc', '.smc', '.zip'), 'Nintendo SNES'),
    # Hardware rendering, via the FBO renderer. Set the core's rdp-plugin to
    # gliden64 for it; angrylion is the software fallback and looks it.
    System('n64', 'Nintendo 64', 'game.libretro.mupen64plus-nx',
           ('.z64', '.n64', '.v64'), 'Nintendo 64'),
    # Hardware rendering too. .cso is a compressed ISO and the format the
    # collection is in; PPSSPP reads it directly, so nothing is unpacked.
    System('psp', 'PSP', 'game.libretro.ppsspp',
           ('.cso', '.iso', '.chd', '.pbp'), 'Sony PlayStation Portable'),
    # Hardware rendering as well. .cdi and .gdi are the two disc formats the
    # collection is in; Flycast reads both without unpacking.
    # prefer .chd: with no preference the fallback sorts by extension, so a
    # leftover .cdi beat the CHD beside it - the same game at 777 MB instead of
    # 98 MB, and unverified. .cdi stays last as the fallback for the few discs
    # that only exist in that form.
    System('dreamcast', 'Dreamcast', 'game.libretro.flycast',
           ('.cdi', '.gdi', '.chd'), 'Sega Dreamcast',
           prefer=('.chd', '.gdi', '.cdi')),
    # Software rendering, and it will not start without a BIOS - the four
    # regional ROMs are installed beside the core.
    System('saturn', 'Saturn', 'game.libretro.beetle-saturn',
           ('.cue', '.ccd', '.chd', '.toc'), 'Sega Saturn',
           prefer=('.chd', '.cue'), skip_exts=('.bin', '.img')),
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
    'dos4gw', '4gwpro', 'dos4g', 'dos32a', 'dos32', 'pmodew', 'zpmi',
    'setsound', 'smkplay', 'mssw', 'mss',
    'patch', 'sbtest', 'modem', 'univbe', 'cwsdpmi', 'pkunzip', 'test',
    # manuals, intros, cheats and helpers that outweigh the real game on size
    'guide', 'info', 'intro', 'cheat', 'cht', 'trainer', 'mouse', 'order', 'manual',
    'demo', 'insthd', 'terrtron', 'fix', 'nosound',
    # Archivers and crack tools shipped alongside install disks. Without these
    # an installer-only release imports as a game whose executable is LHA.EXE,
    # which is how Ultima Underworld and Simon the Sorcerer 2 first arrived.
    'lha', 'lharc', 'arj', 'crack', 'autoplay',
)
