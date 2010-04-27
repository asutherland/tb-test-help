#/usr/bin/python

# This file is intended to be a pragmatic wrapper around invoking systemtap
#  scripts that compensates for the following limitations we currently
#  encounter:
#
# - When dealing with multiple libraries, we have to use @1/@2/@3 in the
#    script to reference the libraries and they often result in annoyingly
#    long command lines.  It is desirable to have easier invocations as well
#    as for the file to be able to deal with such things more symbolically.
#
# - Because of the unreliability of entry probes and our need to probe in the
#    middle of functions, maintaining source lines can be annoying.  It is
#    desirable to be able to anchor such statements once and be able to forget
#    about them until a major change happens.  Simple string matching seems
#    most pragmatic, but we could also accomplish this using version control
#    cleverness if we were so inclined and were using a diff algorithm / strings
#    that don't match on semantically ridiculous edge-cases.  (Something
#    involving DWARF processing could also be possible...)
#
# The net goal is we want to be able to point this script at a systemtap file,
#  a directory tree structure containing the binaries, and have it be able to
#  both invoke that file as well as produce a systemtap script that could be
#  used by others without this script.

import optparse, os.path, re, subprocess, sys

class ChewContext(object):
    '''
    Concentrate all our file-layout assumptions and decisions and what not in
    here.  If you are trying to use this for purposes where MozChewContext is
    not right, then you probably want to subclass this dude and make his methods
    happy.
    '''
    def __init__(self):
        raise Error("I currently cannot be directly instantiated!")

    def find_source_file(self, pathish):
        '''
        Given a path whose 'root' directory is a virtual root, translate it to
        a real on-disk path.  The idea for root directories is to handle the
        mozilla-central/comm-central difference somewhat generically.
        '''
        # it's a given this is not windows. calm down!
        vpart, rpart = pathish.split('/', 1)
        if not vpart in self.src_vpaths:
            raise Error("'%s' is not a valid vpath root!" % (vpart,))
        return os.path.join(self.src_vpaths[vpart], rpart)

    def find_lib_file(self, pathish):
        '''
        Straightforward path mapping from the given relative path to the
        absolute lib_root_path.
        '''
        return os.path.join(self.lib_root_path, pathish)

class MozChewContext(object):
    '''
    Keep the mozilla (well, really, Thunderbird) decisions in here.
    '''
    def __init__(self, objdir, srcdir=None):
        if not os.path.isdir(objdir):
            raise Error("objdir %s does not exist!" % (objdir,))

        # -- Binaries

        # From thunderbird's perspective, everything lives in
        #  objdir/mozilla/dist.  From firefox's persepctive, it's just
        #  objdir/dist
        moz_objdir_root = os.path.join(objdir, 'mozilla')
        if not os.path.isdir(moz_objdir_root):
            moz_objdir_root = objdir
        self.lib_root_path = os.path.join(moz_objdir_root, 'dist')

        # -- Source
        # assume the objdir lives immediately under the srcdir
        if srcdir is None:
            srcdir = os.path.dirname(objdir)
        elif not os.path.isdir(srcdir):
            raise Error("srcdir '%s' does not exist!" % (srcdir,))
        moz_srcdir_root = os.path.join(srcdir, 'mozilla')
        if not os.path.isdir(moz_srcdir_root):
            self.src_vpaths = {'mozilla': srcdir}
        else:
            self.src_vpaths = {'mozilla': moz_srcdir_root,
                               'comm': srcdir}
        

class ScriptChewer(object):
    '''
    Process a systemtap script looking for "@@"-prefix statements and
    expressions.

    We implement support for the following tasks:

    - Finding the appropriate source line to set a breakpoint.  The information
       to find the line is given using @@file/@@method/@@lineseek commands and
       the result is retrieved via the @@statement expression.

    - Allocating command-line argument slots (chew-time) and performing path
       resolution for libraries (invocation-time) using the @@lib expression.
    '''
    def __init__(self, context):
        self.context = context

        self.out_lines = None

        # - @@statement breakpoint support
        self.src_file_name = None
        self.method_name = None
        self.src_line = None

        self.cached_file_path = None
        self.cached_file_lines = None

        # - @@lib support
        self.arg_values = []
        self.arg_descriptions = []
        self.known_libs = {}

        # -- @@stapargs
        self.stap_args = ''

    def _stmt_stapargs(self, val):
        self.stap_args = val

    def _stmt_file(self, val):
        '''
        Given a vpath, save off the filename for later and open the file for
        its lines for use by a lineseek statement later.
        '''
        path = self.context.find_source_file(val)
        if not os.path.isfile(path):
            raise Error("vpath '%s' does not exist!" % (val,))

        if self.cached_file_path != path:
            self.cached_file_path = path
            f = open(path, 'r')
            self.cached_file_lines = f.readlines()
            f.close()

        self.src_line = None
        # we just need the filename to save off
        self.src_file_name = os.path.basename(val)


    def _stmt_method(self, val):
        val = val.strip()
        self.method_name = val

    def _stmt_lineseek(self, val):
        if self.cached_file_lines is None:
            raise Error('No current file lines to process @@lineseek')

        if self.src_line is not None:
            # start on the line after our last match
            startLine = self.src_line + 1
        else:
            startLine = 0
        lines = self.cached_file_lines

        for iLine in range(startLine, len(lines)):
            line = lines[iLine]
            if line.lstrip() == val:
                # results are 1-based, of course.
                self.src_line = iLine + 1
                return

        raise Error(("Unable to locate line with contents '%s' starting " +
                     "from line %d.") % (val, startLine+1))
        
        
    def _expr_statement(self, val):
        '''
        Always looks like "@@statement:ref".  This should take the contents of
        the file/method/lineseeks preceding this and smashing their results
        together to get us a result string that amounts to:
        "METHOD@FILE:LINESEEK", with one specific example resulting in:
        "nsThread::ProcessNextEvent@nsThread.cpp:527"
        '''
        return "%s@%s:%d" % (self.method_name,
                             self.src_file_name, 
                             self.src_line)


    def _expr_lib(self, val):
        '''
        Take "@@lib:bin/components/libgklayout.so" and convert it to @1/@2/...
        based on the allocated arg slots.
        '''
        if val in self.known_libs:
            return self.known_libs[val]

        path = self.context.find_lib_file(val)
        self.arg_values.append(path)
        self.arg_descriptions.append("Path to lib '%s'" % (val,))
        rval = '@%d' % (len(self.arg_values),)
        self.known_libs[val] = rval
        return rval

    def chew_script(self, path):
        expr_re = re.compile(r'\(@@([^:]+):([^\)]+)\)')
        def expr_helper(match):
            exprfunc = getattr(self, '_expr_%s' % (match.groups(1)))
            return exprfunc(match.groups(2))

        out_lines = self.out_lines = []

        self.script_src_path = path
        f = open(path, 'r')
        for line in f:
            # statement?
            if line.startswith('//@@'):
                out_lines.push(out_lines)
                idxColon = line.find(':', 4)
                if idxColon != -1:
                    key = line[4:idxColon]
                    val = line[idxColon+1:]
                    stmtfunc = getattr(self, '_stmt_%s' % (key,))
                    stmtfunc(val)
            else:
                out_lines.push(expr_re.sub(expr_helper, line))
        f.close()

    def maybe_write_script(self, out_path):
        '''
        After we've chewed the input script we should see if the file at the
        target destination is already up-to-date.  We only rewrite it if it
        differs from our in-memory results to avoid contaminating timestamps.

        Return True if we wrote the script, False if we did not need to.
        '''
        if self.script_src_path == out_path:
            raise Error("You are trying to overwrite the source file!!")
        
        if os.path.isfile(out_path):
            f = open(out_path, 'r')
            cur_contents = f.read()
            f.close()
        else:
            cur_contents = ''

        out_str = '\n'.join(self.out_lines)
        wrote_it = False
        if out_str != cur_contents:
            f = open(out_path, 'w')
            f.write(out_str)
            f.close()
            wrote_it = True

        self.out_lines = None

        return wrote_it

class MozMain(object):
    '''
    This command-line driver is mozilla biased.  Go get your own driver, other
    people!  (I will genericize this a little bit eventually).
    '''

    usage = '''usage: %prog systemtapscript PID
    '''

    def _build_parser(self):
        parser = optparse.OptionParser(usage=self.usage)
        return parser

    def run(self):
        parser = self._build_parser()
        options, args = parser.parse_args()

        if len(args) < 2:
            parser.print_usage()
            return 1

        tapscript = args[0]
        pid = int(args[1])

        # use thie pid to get the binary and from that the objdir
        proc_dir = '/proc/%d' % (pid,)
        exe_path = os.path.realpath(os.path.join(proc_dir, 'exe'))

        # systemtap = linux
        pathparts = exe_path.split('/')
        # comm-central?
        if pathparts[-4] == 'mozilla':
            objdir = '/'.join(pathparts[:-4])
        # mozilla-central
        else:
            objdir = '/'.join(pathparts[:-3])
        
        # put our built script in the objdir...
        built_tapscript = os.path.join(objdir, os.path.basename(tapscript))

        # we need a temporary directory to hold our data for this invocation
        tmp_dir = '/tmp/chewtap-%d' % (pid,)
        os.mkdir(tmp_dir)

        # - BUILD the tapscript
        context = MozChewContext(objdir)
        chewer = ScriptChewer(context)
        chewer.chew_script(tapscript)
        chewer.maybe_write_script(built_tapscript)

        # - FETCH required data about the running process.
        # we need the proc maps files to convert pointers
        shutil.copyfile(os.path.join(proc_dir, 'maps'),
                        os.path.join(tmp_dir, 'maps'))
        
        # - RUN systemtap
        # fixup our systemtap args...
        
        try:
            pass
        except 

        return 0

if __name__ == '__main__':
    m = MozMain()
    sys.exit(m.run())
