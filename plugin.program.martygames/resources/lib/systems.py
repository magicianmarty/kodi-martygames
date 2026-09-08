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
    # yabause, not beetle-saturn: Mednafen's core is accuracy-first and saturates
    # an A73 at 97-99% on this box, which starves the audio - Panzer Dragoon ran
    # at 45% and a full 60fps under yabause. beetle-saturn is still installed for
    # anything yabause renders wrongly.
    System('saturn', 'Saturn', 'game.libretro.yabause',
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

    # --- Sega, on cores already installed for Mega Drive ---------------------
    # genplus and picodrive each already accept these; they are separate
    # systems here only so they get their own label, artwork and shelf.
    System('mastersystem', 'Master System', 'game.libretro.genplus',
           ('.sms',), 'Sega Master System'),
    System('gamegear', 'Game Gear', 'game.libretro.genplus',
           ('.gg',), 'Sega Game Gear'),
    System('sg1000', 'SG-1000', 'game.libretro.genplus',
           ('.sg',), 'Sega SG-1000'),
    # Needs the regional BIOS in the core's system directory, like Saturn does.
    System('segacd', 'Sega CD', 'game.libretro.genplus',
           ('.chd', '.cue', '.iso'), 'Sega CD',
           prefer=('.chd', '.cue'), skip_exts=('.bin', '.img')),
    System('sega32x', '32X', 'game.libretro.picodrive',
           ('.32x',), 'Sega 32X'),

    # --- Nintendo handhelds --------------------------------------------------
    System('gameboy', 'Game Boy', 'game.libretro.gambatte',
           ('.gb', '.gbc'), 'Nintendo Game Boy'),
    System('gba', 'Game Boy Advance', 'game.libretro.mgba',
           ('.gba',), 'Nintendo Game Boy Advance'),
    System('virtualboy', 'Virtual Boy', 'game.libretro.beetle-vb',
           ('.vb',), 'Nintendo Virtual Boy'),

    # --- SNK -----------------------------------------------------------------
    # .zip and nothing else: fbneo takes MAME-style romsets, not loose files.
    System('neogeo', 'Neo Geo', 'game.libretro.fbneo',
           ('.zip',), 'SNK Neo Geo'),
    System('ngp', 'Neo Geo Pocket', 'game.libretro.beetle-ngp',
           ('.ngp', '.ngc'), 'SNK Neo Geo Pocket Color'),

    # --- Atari ---------------------------------------------------------------
    System('atari2600', 'Atari 2600', 'game.libretro.stella',
           ('.a26', '.bin'), 'Atari 2600'),
    System('atari7800', 'Atari 7800', 'game.libretro.prosystem',
           ('.a78',), 'Atari 7800'),
    System('atari800', 'Atari 8-bit', 'game.libretro.atari800',
           ('.atr', '.xex', '.atx', '.cas'), 'Atari 800'),
    System('lynx', 'Lynx', 'game.libretro.beetle-lynx',
           ('.lnx',), 'Atari Lynx'),
    System('jaguar', 'Jaguar', 'game.libretro.virtualjaguar',
           ('.j64', '.jag'), 'Atari Jaguar'),

    # --- home computers ------------------------------------------------------
    System('spectrum', 'ZX Spectrum', 'game.libretro.fuse',
           ('.tzx', '.tap', '.z80', '.sna', '.szx'), 'Sinclair ZX Spectrum'),
    System('msx', 'MSX', 'game.libretro.bluemsx',
           ('.rom', '.mx1', '.mx2', '.dsk', '.cas'), 'Microsoft MSX'),
    System('amstrad', 'Amstrad CPC', 'game.libretro.cap32',
           ('.dsk', '.sna', '.cdt', '.tap'), 'Amstrad CPC'),

    # --- the rest ------------------------------------------------------------
    System('threedo', '3DO', 'game.libretro.opera',
           ('.chd', '.cue', '.iso'), 'Panasonic 3DO',
           prefer=('.chd', '.cue'), skip_exts=('.bin', '.img')),
    System('pcfx', 'PC-FX', 'game.libretro.beetle-pcfx',
           ('.chd', '.cue'), 'NEC PC-FX',
           prefer=('.chd', '.cue'), skip_exts=('.bin', '.img')),
    System('wonderswan', 'WonderSwan', 'game.libretro.beetle-wswan',
           ('.ws', '.wsc'), 'Bandai WonderSwan Color'),
    System('vectrex', 'Vectrex', 'game.libretro.vecx',
           ('.vec', '.bin'), 'GCE Vectrex'),
    System('odyssey2', 'Odyssey 2', 'game.libretro.o2em',
           ('.bin',), 'Magnavox Odyssey 2'),
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
