#/usr/bin/python2.6

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

import imp, optparse, os.path, re, shutil, struct, subprocess, sys, time

class ChewContext(object):
    '''
    Concentrate all our file-layout assumptions and decisions and what not in
    here.  If you are trying to use this for purposes where MozChewContext is
    not right, then you probably want to subclass this dude and make his methods
    happy.
    '''
    def __init__(self):
        raise Exception("I currently cannot be directly instantiated!")

    def find_source_file(self, pathish):
        '''
        Given a path whose 'root' directory is a virtual root, translate it to
        a real on-disk path.  The idea for root directories is to handle the
        mozilla-central/comm-central difference somewhat generically.
        '''
        # it's a given this is not windows. calm down!
        vpart, rpart = pathish.split('/', 1)
        if not vpart in self.src_vpaths:
            raise Exception("'%s' is not a valid vpath root!" % (vpart,))
        return os.path.join(self.src_vpaths[vpart], rpart)

    def find_lib_file(self, pathish):
        '''
        Straightforward path mapping from the given relative path to the
        absolute lib_root_path.
        '''
        return os.path.join(self.lib_root_path, pathish)

class MozChewContext(ChewContext):
    '''
    Keep the mozilla (well, really, Thunderbird) decisions in here.
    '''
    def __init__(self, objdir, srcdir=None):
        if not os.path.isdir(objdir):
            raise Exception("objdir %s does not exist!" % (objdir,))

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
            raise Exception("srcdir '%s' does not exist!" % (srcdir,))
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
        self.stap_args = []

        # -- @@postprocess
        self.postprocess_script = None

    def _stmt_stapargs(self, val):
        self.stap_args = val.split(',')

    def _stmt_postprocess(self, val):
        self.postprocess_script = val

    def _stmt_file(self, val):
        '''
        Given a vpath, save off the filename for later and open the file for
        its lines for use by a lineseek statement later.
        '''
        path = self.context.find_source_file(val)
        if not os.path.isfile(path):
            raise Exception("vpath '%s' does not exist!" % (val,))

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
            raise Exception('No current file lines to process @@lineseek')

        if self.src_line is not None:
            # start on the line after our last match
            startLine = self.src_line + 1
        else:
            startLine = 0
        lines = self.cached_file_lines

        for iLine in range(startLine, len(lines)):
            line = lines[iLine]
            if line.strip() == val:
                # results are 1-based, of course.
                self.src_line = iLine + 1
                return

        raise Exception(
            ("Unable to locate line with contents '%s' starting " +
             "from line %d in file %s.") %
            (val, startLine+1, self.src_file_name))
        
        
    def _expr_statement(self, val):
        '''
        Always looks like "@@statement:ref".  This should take the contents of
        the file/method/lineseeks preceding this and smashing their results
        together to get us a result string that amounts to:
        "METHOD@FILE:LINESEEK", with one specific example resulting in:
        "nsThread::ProcessNextEvent@nsThread.cpp:527"
        '''
        return '"%s@%s:%d"' % (self.method_name,
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
        expr_re = re.compile(r'@@([^:]+):([^\)]+)([,\)])')
        def expr_helper(match):
            exprfunc = getattr(self, '_expr_%s' % (match.group(1),))
            return '%s%s' % (exprfunc(match.group(2)),match.group(3))

        out_lines = self.out_lines = []

        self.script_src_path = path
        f = open(path, 'r')
        for line in f:
            # statement?
            if line.startswith('//@@'):
                out_lines.append(line)
                idxColon = line.find(':', 4)
                if idxColon != -1:
                    key = line[4:idxColon]
                    # there's a newline...
                    val = line.rstrip()[idxColon+1:]
                    stmtfunc = getattr(self, '_stmt_%s' % (key,))
                    stmtfunc(val)
            else:
                out_lines.append(expr_re.sub(expr_helper, line))
        f.close()

    def maybe_write_script(self, out_path):
        '''
        After we've chewed the input script we should see if the file at the
        target destination is already up-to-date.  We only rewrite it if it
        differs from our in-memory results to avoid contaminating timestamps.

        Return True if we wrote the script, False if we did not need to.
        '''
        if self.script_src_path == out_path:
            raise Exception("You are trying to overwrite the source file!!")
        
        if os.path.isfile(out_path):
            f = open(out_path, 'r')
            cur_contents = f.read()
            f.close()
        else:
            cur_contents = ''

        # out_lines have newlines on them
        out_str = ''.join(self.out_lines)
        wrote_it = False
        if out_str != cur_contents:
            f = open(out_path, 'w')
            f.write(out_str)
            f.close()
            wrote_it = True

        self.out_lines = None

        return wrote_it

class BulkProcessor(object):
    '''
    In bulk mode each per-cpu file is written as a series of records where the
    header is a _stp_trace record:

    struct _stp_trace {
      uint32_t sequence;      /* event number */
      uint32_t pdu_len;       /* length of data after this trace */
    };

    The headers are not aligned; they can start at any byte offset.

    We take on the responsibility of stitching together the bulk files and
    providing the event blobs in-order.

    In theory at some point we might be able to do this in a realtime streaming
    fashion by watching as the files get appended to or something along those
    lines, but we don't do it right now.  We do try and keep our memory usage
    down though.

    Use us like an iterator in a for loop...
    for blob in BulkProcessor('/tmp/dir_with_bulk/files'):
        print 'I got a blob!', blob
    '''

    def __init__(self, path):
        '''
        We expect bulk_# files to be found in path.
        '''
        self.files = []
        self.next_seqs_by_file = []
        self.next_blobs_by_file = []

        i = 0
        while True:
            speculative_path = os.path.join(path, 'bulk_%d' % (i,))
            if not os.path.exists(speculative_path):
                break
            self.files.append(open(speculative_path, 'r'))
            seq, blob = self._read_next(i)
            self.next_seqs_by_file.append(seq)
            self.next_blobs_by_file.append(blob)
            i += 1

    def _read_next(self, i):
        '''
        Read the next seq and blob packet for the file at the given index.  If
        we encounter a problem we close the file and return None for both
        values.
        '''
        try:
            seq, pdu_len = struct.unpack('II', self.files[i].read(8))
            blob = self.files[i].read(pdu_len)
            return seq, blob
        except:
            self.files[i].close()
            return None, None

    def __iter__(self):
        return self

    def next(self):
        min_idx = 0
        min_seq = self.next_seqs_by_file[0]
        for i in range(1, len(self.next_seqs_by_file)):
            seq = self.next_seqs_by_file[i]
            if (min_seq is None) or seq < min_seq:
                min_idx = i
                min_seq = seq
        if min_seq is None:
            raise StopIteration

        min_blob = self.next_blobs_by_file[min_idx]
        #print 'min_seq', min_seq, 'min_blob', min_blob
        next_seq, next_blob = self._read_next(min_idx)
        self.next_seqs_by_file[min_idx] = next_seq
        self.next_blobs_by_file[min_idx] = next_blob

        return min_blob
        


class MozMain(object):
    '''
    This command-line driver is mozilla biased.  Go get your own driver, other
    people!  (I will genericize this a little bit eventually).
    '''

    usage = '''usage: %prog systemtapscript PID
    '''

    def _build_parser(self):
        parser = optparse.OptionParser(usage=self.usage)

        parser.add_option('--re-run',
                          dest='rerunpath',
                          default=None)
        return parser

    def run(self):
        parser = self._build_parser()
        options, args = parser.parse_args()

        dorunrun = True

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

        # -- BUILD the tapscript
        context = MozChewContext(objdir)
        chewer = ScriptChewer(context)
        chewer.chew_script(tapscript)
        chewer.maybe_write_script(built_tapscript)

        # -- FETCH required data about the running process.
        # we need a temporary directory to hold our data for this invocation
        
        if options.rerunpath:
            tmp_dir = options.rerunpath
            dorunrun = False
        else:
            tmp_dir = '/tmp/chewtap-%d' % (pid,)
            if os.path.exists(tmp_dir):
                tmp_dir += '-%d' % (int(time.time()),)
            os.mkdir(tmp_dir)

            # we need the proc maps files to convert pointers
            shutil.copyfile(os.path.join(proc_dir, 'maps'),
                            os.path.join(tmp_dir, 'maps'))
        
        # -- RUN systemtap
        # - build args
        # assume the user is in the stapdev group
        args = ['/usr/bin/stap']
        # the script tells us what arguments it wants
        args.extend(chewer.stap_args)
        if '-b' in chewer.stap_args:
            args.append('-o %s' % (os.path.join(tmp_dir, 'bulk'),))
        # the built script
        args.append(built_tapscript)
        # the library paths
        args.extend(chewer.arg_values)
        
        # - run
        # The expected use-case is to hit control-c when done, at which point
        #  we want to tell stap to close up shop.
        if dorunrun:
            pope = subprocess.Popen(args, stdin=subprocess.PIPE)
            try:
                print 'Hit control-C to terminate the tapscript'
                pope.communicate()
                # if we get here, the user did not hit control-c and this means
                #  either the tapscript terminated itself or there was a
                #  problem...
                if pope.poll():
                    # problem!
                    print 'Detected stap error result code, not post-processing'
                    print 'Any results will be in', tmp_dir
                    return pope.returncode
            except KeyboardInterrupt:
                # (python2.6 required)
                pope.terminate()

        # -- POST PROCESS
        if chewer.postprocess_script:
            search_path = [os.path.dirname(os.path.abspath(tapscript))]
            search_path.extend(sys.path)
            fp, modpath, desc = imp.find_module(chewer.postprocess_script,
                                                search_path)
            module = None
            try:
                module = imp.load_module(chewer.postprocess_script,
                                         fp, modpath, desc)
            finally:
                if fp:
                    fp.close()

            if module:
                bulkproc = BulkProcessor(tmp_dir)
                modproc = module.Processor()
                modproc.process(tmp_dir, bulkproc)
        
        return 0

if __name__ == '__main__':
    m = MozMain()
    sys.exit(m.run())
