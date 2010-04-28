#!/usr/bin/python
# MPL/GPL/LGPL licensed
# Andrew Sutherland <asutherland@asutherland.org>
#
# Usage: addrsymfilt.py <PID>
#
# Example: stap mytap.stp | addrsymfilt.py `pgrep thunderbird-bin`
#
# We filter the provided text stream, replacing any addresses we find with the
#  closest preceding symbol found in the process.
#
# This is accomplished by reading /proc/PID/maps to understand the address space
# of the process.  Once we have this information, we are able to get the symbols
# for each process using 'nm'.  (We could be fancier, but why bother?)  We do
# not do anything with dwarf debug symbols, but do ask nm to perform C++
# demangling for us.
#

import sys, re
import subprocess


def hexparse(x):
    return int(x, 16)

class BinaryInfo(object):
    '''
    Provides address to symbol translation for a binary with on-demand retrieval
    of symbols.  Because we only fetch things on-demand, it's okay even if the
    binaries are data things like fonts.

    We do some pragmatic if likely sketchy things when it comes to address
    mapping.  Sadly, I even used to know how to do these things properly, but
    it turns out this is easier than re-learning.  See _loadOffsetInfo.
    '''
    def __init__(self, path):
        self.path = path
        #: the adjustment to apply if we have any offset passed
        self.offsetAdjustment = 0
        self.symbols = None

    def _loadOffsetInfo(self):
        '''
        Figure out how to map the file offset to the virtual address offset.

        We take all the LOAD segments from readelf -l and record the offset and
        VirtAddr.  This will allow us to map using the offset passed in from
        the offset provided by /proc/PID/maps to just directly have the virt
        addr to add on.
        '''
        self.offsetInfo = {}
        args = ['/usr/bin/readelf', '-l', self.path]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE)
        for line in proc.stdout:
            line = line.strip()
            # we only care about load lines
            if line.startswith('LOAD'):
                bits = line.split(None, 3)
                offset = int(bits[1], 16)
                virtAddr = int(bits[2], 16)
                self.offsetAdjustment = virtAddr - offset

    def _loadSymbols(self):
        '''
        Grab symbols from the binary via nm.
        '''
        self._loadOffsetInfo()
        self.symbols = []
        lastaddr = -1

        args = ['/usr/bin/nm', '--demangle', '--defined-only',
                '--numeric-sort', self.path]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE)
        for line in proc.stdout:
            addrStr, symtype, symname = line.rstrip().split(None, 2)
            addr = hexparse(addrStr)

            # no dupes!
            if addr == lastaddr:
                continue

            # - trim the symbol name of junk
            if symname.startswith('non-virtual thunk to '):
                symname = 'thunk:' + symname[21:]

            idxParen = symname.find('(')
            if idxParen >= 0:
                if symname[idxParen+1] != ')':
                    ridxParen = symname.find(')', idxParen+1)
                    symname = symname[:idxParen+1] + '...' + symname[ridxParen:]

            lastaddr = addr
            self.symbols.append((addr, symname))

    def translateAddress(self, addr, offset):
        '''
        @returns (symbol string, overshoot in bytes)
        '''
        if self.symbols is None:
            self._loadSymbols()

        if offset:
            addr += offset + self.offsetAdjustment

        symbols = self.symbols
        if not symbols:
            return None, None
        lo = 0
        hi = len(symbols)
        while lo < hi:
            mid = (lo+hi)//2
            midtupe = symbols[mid]
            midaddr = midtupe[0]
            if midaddr < addr:
                lo = mid+1
            elif midaddr > addr:
                hi = mid
            else:
                # exact match! hooray!
                return midtupe[1], 0
        # not an exact match, lo-1 is our index if lo>0
        if lo:
            midtupe = symbols[lo-1]
            return midtupe[1], addr-midtupe[0]
        return None, None

class ProcInfo(object):
    def __init__(self, pid, mappath=None):
        self.pid = int(pid)
        #: Tuples of (low addr, high addr, adjust, binary).
        #:  The low address is inclusive, the high address is exclusive.
        self.ranges = []
        self.binaries_by_path = {}

        self._read_maps(mappath)

    def _read_maps(self, mappath=None):
        '''read /proc/PID/maps to get info about the address space'''
        # example:
        #address           perms offset  dev   inode      pathname
        #08040000-08050000 r-xp 00000000 01:02 12345      /usr/bin/ls
        # perms: read/write/execute/shared/private (copy on write)
        # offset: the offset into the mapped file
        # dev: major/minor device number of the file's origin
        # inode: inode on the origin device
        if mappath is None:
            mappath = '/proc/%d/maps' % (self.pid,)
        mapfile = open(mappath, 'r')
        for line in mapfile:
            bits = line.rstrip().split(None, 5)
            # ignore things without paths, we can't look in them
            if len(bits) < 6:
                continue
            path = bits[5]
            # ignore stack/vdso/vsyscall
            if path.startswith('['):
                continue
            # ignore things we can't get at
            if path.endswith(' (deleted)'):
                continue
            if path not in self.binaries_by_path:
                self.binaries_by_path[path] = BinaryInfo(path)
            binary = self.binaries_by_path[path]

            addr_low, addr_high = map(hexparse, bits[0].split('-'))
            offset = hexparse(bits[2])

            self.ranges.append((addr_low, addr_high, offset, binary))

        mapfile.close()

    def translateAddress(self, addr):
        ranges = self.ranges
        if not ranges:
            return None, None

        lo = 0
        hi = len(ranges)
        while lo < hi:
            mid = (lo+hi)//2
            midtupe = ranges[mid]
            range_start = midtupe[0]
            range_end = midtupe[1]
            if range_end <= addr:
                lo = mid+1
            elif range_start > addr:
                hi = mid
            else:
                # in the range, hooray!
                binary = midtupe[3]
                offset = midtupe[2]
                #print hex(addr), hex(range_start), hex(addr-range_start), 'in', binary.path
                return binary.translateAddress(addr-range_start, offset)
        return None, None

    def normalizeHexAddress(self, hexaddr, command, padding=None):
        addr = int(hexaddr, 16)
        symname, overshoot = self.translateAddress(addr)
        if symname:
            if command:
                if command == 'vt':
                    if symname.startswith('vtable for '):
                        symname = symname[11:]
                if padding:
                    symname = symname.ljust(int(padding))
                return symname
            if overshoot:
                return '%s+%x' % (symname, overshoot)
            return symname
        return hexaddr

    full_addr_hex_re = re.compile('^:!([a-z]{2,2})(?:,(\d+))?:([0-9a-f]+)$')
    def transformString(self, s):
        match = self.full_addr_hex_re.match(s)
        if match:
            command = match.group(1)
            padding = match.group(2)
            hexaddr = match.group(3)
            return self.normalizeHexAddress(hexaddr, command, padding)
        return s


def main(pid):
    normal_hex_re = re.compile("0x[0-9a-f]+")
    addr_hex_re = re.compile(':!([a-z]{2,2})(?:,(\d+))?:([0-9a-f]+)')
    
    proc = ProcInfo(pid)

    def normal_replacer(match):
        hexaddr = match.group(0)
        symname, overshoot = proc.translateAddress(int(hexaddr, 16))
        return symname or hexaddr

    def replacer(match):
        command = match.group(1)
        padding = match.group(2)
        hexaddr = match.group(3)
        return proc.normalizeHexAddress(hexaddr, command, padding)

    while not sys.stdin.closed:
        line = sys.stdin.readline()
        line = addr_hex_re.sub(replacer, line)
        line = normal_hex_re.sub(normal_replacer, line)
        sys.stdout.write(line)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.stderr.write('We need the PID as an arg!')
        sys.exit(1)

    main(sys.argv[1])
