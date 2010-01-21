import os, os.path

# /proc/net/unix
# RefCount => reference count
# Protocol => always 0
# Flags: __SO_ACCEPTCON if TCP_LISTEN, otherwise 0
# Type: sk_type
# St: has a socket? => SS_CONNECTED (3) / SS_UNCONNECTED (1)
#     has no socket? => SS_CONNECTING (2) / SS_DISCONNECTING (4)
# Inode: inode
# Path: if u_addr => unix socket path...
#   unix socket paths starting with '@' are abstract sockets, meaning their
#   paths are unrelated to the actual filesystem

class UnixSocketInfo(object):
    __slots__ = ['listening', 'stream', 'connected', 'inode', 'name']
    def __init__(self, stream, connected, inode, name):
        self.listening = listening
        self.stream = stream
        self.connected = connected
        self.inode = inode
        self.name = name

class FDInfo(object):
    __slots__ = ['inode', 'mode', 'path']

    def __init__(self, inode, mode, path):
        self.inode = inode
        self.mode = mode

class ProcessInfo(object):
    __slots__ = ['pid', 'exe', 'cmdline', 'fds']

    def __init__(self, pid, exe, cmdline, fds):
        self.pid = pid
        self.exe = exe
        self.cmdline = cmdline
        self.fds = fds

def grab(fpath):
    f = open(fpath, 'r')
    data = f.read().strip()
    f.close()
    return data

class FDDigger(object):
    '''
    Dig for info about processes via file descriptors and such.
    '''

    def __init__(self):
        self.inodes = {}
        self.procs = {}

    def grok_fd_link(self, path):
        '''
        Given a path that we got out of an fd, provide the corresponding object.
        '''
        if path.startswith('pipe:['):
            inode = int(path[6:-1])
        elif path.startswith('socket:['):
            inode = int(path[8:-1])
        elif path.startswith('/dev/'):
            pass
        elif path == 'inotify':
            pass
        elif path.endswith(' (deleted)'):
            pass
        else: # file
            pass

    def dig_proc_num(self, pid):
        basepath = '/proc/%d/' % (pid,)
        proc = ProcessInfo(pid,
                           os.readlink(basepath + 'exe'),
                           grab(basepath + 'cmdline'),
                           self.dig_proc_num_fd, pid)

    def dig_proc_num_fd(self, pid):
        for name in os.listdir('/proc/%d/fd' % (pid,)):
            num = int(name)
            path = '/proc/%d/fd/%d' % (pid, num)
            statinfo = os.stat(path)
            

    def dig_proc_net_unix(self):
        f = open('/proc/net/unix', 'r')
        for iLine, line in enumerate(f):
            if iLine == 0:
                continue
            bits = line.strip().split()

            listening = int(bits[3]) != 0
            # 0001 is SOCK_STREAM, 0002 is SOCK_DGRAM, etc.
            stream = bits[4] == "0001"
            connected = bits[5] in ('02', '03')
            inode = int(bits[6])
            # unnamed
            if len(bits) == 8:
                name = bits[7]
            else:
                name = None

            self.inodes[inode] = UnixSocketInfo(listening, stream, connected,
                                                inode, name)
        f.close()

if __name__ == '__main__':
    digger = FDDigger()
    
