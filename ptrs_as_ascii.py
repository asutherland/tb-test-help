#!/usr/bin/python

import re

# meh, our official builds are all 32-bit right now...
PTR_REGEX = re.compile('(0x[0-9a-fA-F]{8,8})')

def ptr_as_ascii(z):
    if (z == 0xffffffff):
        return None

    # the world is little-endian, yo
    s = (chr(z & 0xff) + chr((z >> 8) & 0xff) + chr((z >> 16) & 0xff)
         + chr ((z >> 24) & 0xff))
    return repr(s,)

def see_pointers(f):
    abits = []
    for line in f:
        for match in PTR_REGEX.finditer(line):
            s = ptr_as_ascii(int(match.group(1), 16))
            if s:
                abits.append(s)

    DESIRED_WIDTH = 60
    PTRS_PER_LINE = DESIRED_WIDTH // 7
    for i in range(0, len(abits), PTRS_PER_LINE):
        print ' '.join(abits[i:i+PTRS_PER_LINE])

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print 'Yo, filename!'
        sys.exit(1)
    f = open(sys.argv[1], 'rt')
    see_pointers(f)
    f.close()
