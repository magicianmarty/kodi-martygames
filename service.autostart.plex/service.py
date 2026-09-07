import xbmc
import xbmcgui

# Start Plex, then get out of the way.
#
# The skin's Plex rows - Continue Watching, On Deck, Recently Added - are
# plugin://script.plexmod/hubs paths, and that endpoint only answers while the
# add-on is already running: asked cold it logs "Trying to reactivate minimized
# addon" and the row comes back empty. So Plex genuinely has to be started at
# boot for the home screen to have anything on it.
#
# What it must not do is stay in front. RunAddon opens it full screen, which is
# not what you want to see when the box comes up. Sending the window back to
# home once it is up is exactly what the add-on's own Minimize does - it keeps
# running and serving the hubs, with the skin in front.

HOME = 10000
RUNNING = 'script.plex.running'

monitor = xbmc.Monitor()
home = xbmcgui.Window(HOME)


def wait_for(predicate, seconds):
    for _ in range(int(seconds * 2)):
        if monitor.waitForAbort(0.5):
            return False
        if predicate():
            return True
    return False


if wait_for(lambda: xbmc.getCondVisibility('Window.IsActive(home)'), 60):
    xbmc.log('[autostart.plex] home ready -> starting script.plexmod', xbmc.LOGINFO)
    xbmc.executebuiltin('RunAddon(script.plexmod)')

    # Only send it away once it is actually up; doing it too early races the
    # add-on's own window opening and leaves Plex in front anyway.
    if wait_for(lambda: bool(home.getProperty(RUNNING)), 90):
        xbmc.log('[autostart.plex] plexmod up -> returning to the skin', xbmc.LOGINFO)
        xbmc.executebuiltin('ActivateWindow({0})'.format(HOME))
    else:
        xbmc.log('[autostart.plex] plexmod never reported running; leaving it alone',
                 xbmc.LOGWARNING)
