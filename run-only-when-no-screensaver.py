#!/usr/bin/python

# A simple script to use dbus to check the state of the screensaver that starts
#  a subprocess when the screensaver deactivates and kills the subprocess when
#  the screensaver activates.
#
# Assuming you lock your computer for peace of mind, this helps out your peace
#  of mind by letting you only run security-compromising things when you are
#  at your keyboard.  (Or if you are not at your keyboard and forget to lock
#  and you ahve no auto-lock, you're certainly no worse off.)
#
# We also restart dead processes periodically if they go away.
#
# To kill the child process we send it a SIGTERM and follow that up after
#  a second with a SIGKILL if it did not die from the SIGTERM.  We are not
#  killer robots from the future, though, so we can be outwitted.  If you are
#  using a shell script as a fancy alias, you can simplify things by using
#  "exec" in the shell script to have the shell replaced with the executable.
#
# For example, you could use this to run an SSH port forwarding mechanism that
#  exposes potentially private data on the machine running the script to another
#  machine that you are less paranoid about.  (Obviously, nothing stops the
#  other machine from getting compromised and then used to do evil once the
#  port forwarding mechanism reconnects, but I'm assuming that's not the most
#  important concern.)
#
# Andrew Sutherland <asutherland@asutherland.org>, 2010

import dbus, dbus.glib, gobject, subprocess, time


class ProcessMinder(object):
    def __init__(self, args):
        self.args = args
        self.pope = None

    def run(self):
        # if we have an active kid, just make sure it's still kicking
        if self.pope is not None:
            return self.stay_alive_or_dead()
        
        # leave stdin/stdout hooked up so we don't really need to do anything
        #  to keep the big wheel 'on turning
        self.pope = subprocess.Popen(self.args)

    def kill(self):
        # bail if already dead
        if self.pope is None:
            return
        
        # send a term so it has a chance to clean up, but follow it up with a
        #  kill if it does not die after a second
        self.pope.terminate()
        time.sleep(0.1)
        if self.pope.poll() is None:
            time.sleep(0.9)
        if self.pope.poll() is None:
            self.pope.kill()
        self.pope = None

    def stay_alive_or_dead(self):
        """
        Make sure the child process has not died.
        """
        # things don't just magically come to life
        if self.pope is None:
            return

        if self.pope.poll() is not None:
            # it died! oh noes!
            self.pope = None
            print 'Restarting process'
            self.run()
        

    def screensaver_active_state_changed(self, active):
        if active:
            # screensaver active => kill the child process
            self.kill()
        else:
            # screensaver inactive => run
            self.run()
    

# How often to check on the subprocess.  This also doubles as our throttle to
#  stop us from going into a tight loop of spawning processes that immediately
#  fail and terminate.
POLL_INTERVAL_MS = 5000

def main(args):
    minder = ProcessMinder(args)

    bus = dbus.SessionBus()

    # figure out what the screensaver is up to right now
    saver_proxy = bus.get_object('org.gnome.ScreenSaver',
                                 '/org/gnome/ScreenSaver')
    minder.screensaver_active_state_changed(saver_proxy.GetActive())

    # listen for changes in screensaver activity
    bus.add_signal_receiver(
        minder.screensaver_active_state_changed,
        'ActiveChanged',
        'org.gnome.ScreenSaver')

    # periodically poke the subprocess with a stick
    gobject.timeout_add(POLL_INTERVAL_MS, minder.stay_alive_or_dead)

    mainLoop = gobject.MainLoop()
    try:
        mainLoop.run()
    finally:
        minder.kill()


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])
