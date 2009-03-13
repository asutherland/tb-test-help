from straceparser import funcLine
import datetime

def listify_delta_hash(d, tstart, tend):
    vals = [0] * (tend - tstart + 1)
    for key, val in d.items():
        vals[key - tstart] = val
    return vals

class FDInfo(object):
    __slots__ = ['handle', 'filename',
                 'countReads', 'countZeroReads', 'totalReadBytes',
                 'countWrites', 'totalWrittenBytes',
                 'totalStats', 'totalSeeks',
                 'readCountStats', 'readBytesStats',
                 'writeCountStats', 'writtenBytesStats',
                 'statCountStats', 'seekCountStats',
                 'firstAccess', 'lastAccess',
                 'eventsSeen']
    def __init__(self, handle, filename=None):
        self.handle = handle
        self.filename = filename

        self.countReads = 0
        self.countZeroReads = 0
        self.totalReadBytes = 0

        self.countWrites = 0
        self.totalWrittenBytes = 0

        self.totalStats = 0
        self.totalSeeks = 0

        self.readCountStats = {}
        self.readBytesStats = {}

        self.writeCountStats = {}
        self.writtenBytesStats = {}

        self.statCountStats = {}
        self.seekCountStats = {}

        self.firstAccess = None
        self.lastAccess = None

        self.eventsSeen = {}

    def observeEvent(self, name, when):
        self.eventsSeen[name] = when

    def summarize(self, stime, tdelta):
        print '.' * 20
        print 'fd:', self.handle, self.filename
        print ' first accessed at:', self.firstAccess - stime
        print ' last accessed at:', self.lastAccess - stime
        print ' %d reads (%d zero reads) totaling %d' % (
            self.countReads, self.countZeroReads, self.totalReadBytes)
        print '', self.countWrites, 'writes totaling', self.totalWrittenBytes
        print '', self.totalStats, 'stats'
        print '', self.totalSeeks, 'seeks'
        print
        print ' reads per sec:', listify_delta_hash(
            self.readCountStats, self.firstAccess, self.lastAccess)
        print ' writes per sec:', listify_delta_hash(
            self.writeCountStats, self.firstAccess, self.lastAccess)
        print ' stats per sec:', listify_delta_hash(
            self.statCountStats, self.firstAccess, self.lastAccess)
        print ' seeks per sec:', listify_delta_hash(
            self.seekCountStats, self.firstAccess, self.lastAccess)
        print
        if len(self.eventsSeen):
            for name, when in self.eventsSeen.items():
                print ' event: %s at %d' % (name, when - stime)
            print


class STraceGrokker(object):
    def __init__(self):
        pass

    def grokFile(self, filename):
        f = open(filename, 'r')
        try:
            self.grok(f)
        finally:
            f.close()

    def _get_fd(self, fd_handle, filename=None):
        if fd_handle in self.fd_info:
            fd = self.fd_info[fd_handle]
            if filename:
                fd.filename = filename
        else:
            fd = self.fd_info[fd_handle] = FDInfo(fd_handle, filename)
        # assume sequential access!
        if fd.firstAccess is None:
            fd.firstAccess = self.timestamp
        fd.lastAccess = self.timestamp
        return fd

    def _fd_open(self, filename, flags, fdh):
        if fdh < 0:
            print '_fd_open does not like errors'
            return
        fd = self._get_fd(fdh, filename)
        fd.observeEvent('open', self.timestamp)

    def _fd_close(self, fdh):
        fd = self._get_fd(fdh)
        fd.observeEvent('close', self.timestamp)

    def _fd_read(self, fdh, bytes):
        fd = self._get_fd(fdh)
        fd.countReads += 1
        if bytes > 0:
            fd.totalReadBytes += bytes
        else:
            fd.countZeroReads += 1
        fd.readCountStats[self.timestamp] = 1 + fd.readCountStats.get(self.timestamp, 0)
        fd.readBytesStats[self.timestamp] = bytes + fd.readBytesStats.get(self.timestamp, 0)

    def _fd_write(self, fdh, bytes):
        fd = self._get_fd(fdh)
        fd.countWrites += 1
        fd.totalWrittenBytes += bytes
        fd.writeCountStats[self.timestamp] = 1 + fd.writeCountStats.get(self.timestamp, 0)
        fd.writtenBytesStats[self.timestamp] = bytes + fd.writtenBytesStats.get(self.timestamp, 0)

    def _fd_select(self, fdh):
        pass

    def _fd_fstat(self, fdh):
        fd = self._get_fd(fdh)
        fd.totalStats += 1
        fd.statCountStats[self.timestamp] = 1 + fd.statCountStats.get(self.timestamp, 0)

    def _fd_seek(self, fdh):
        fd = self._get_fd(fdh)
        fd.totalSeeks += 1
        fd.seekCountStats[self.timestamp] = 1 + fd.seekCountStats.get(self.timestamp, 0)

    def _procfunc_gettimeofday(self, info, args):
        secs, usecs = args[0]
        self.timestamp = secs

        if self.firstTimestamp is None:
            self.firstTimestamp = secs
        self.lastTimestamp = secs

    def _procfunc_select(self, info, args):
        pass

    def _procfunc_poll(self, info, args):
        pass

    def _procfunc_open(self, info, args):
        self._fd_open(args[0], args[1], info.rval)

    def _procfunc_close(self, info, args):
        self._fd_close(args[0])

    def _procfunc_read(self, info, args):
        fd, iov, iovcnt = args
        self._fd_read(fd, info.rval)

    def _procfunc_writev(self, info, args):
        fd, iov, iovcnt = args
        self._fd_write(fd, info.rval)

    def _procfunc_fstat64(self, info, args):
        fd, buf = args
        self._fd_fstat(fd)

    def _procfunc__llseek(self, info, args):
        fd, offset, result, whence = args
        self._fd_seek(fd)

    def _init_file_state(self):
        self.fd_info = {}
        self.firstTimestamp = None
        self.lastTimestamp = None

    def summarize(self):
        tdelta = self.lastTimestamp - self.firstTimestamp
        print tdelta, 'seconds of strace'
        print
        for fdh in sorted(self.fd_info.keys()):
            fd = self.fd_info[fdh]
            fd.summarize(self.firstTimestamp, tdelta)

    def grok(self, filey):
        self._init_file_state()
        for line in filey:
            try:
                info = funcLine.parseString(line)
            except Exception, e:
                print 'problem parsing line', line
                raise e
            
            func_name = info.func
            handler_name = '_procfunc_' + func_name
            handler = getattr(self, handler_name, None)

            args = info.args
            if handler:
                handler(info, args)

        self.summarize()

if __name__ == '__main__':
    import sys
    grokker = STraceGrokker()
    for filename in sys.argv[1:]:
        grokker.grokFile(filename)
