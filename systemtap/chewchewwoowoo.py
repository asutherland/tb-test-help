#!/usr/bin/python2.6

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
# - Cramming meta-data about the probes into the script and having it easily
#    accessible.  For example, knowing the post-processing script to use (and
#    using it), knowing how to mangle wrapped command arguments to extract a
#    targeted output directory, etc.
#
# - Limitations in the stap/staprun '-c' command in terms of environment
#    clobbering.
#
# - Apparent limitations in stap's ability to cache modules without having to
#    probe around to make sure things are still the same become workflow
#    concerns.  Specifically, I want to be able to run a bunch of unit tests
#    with the same set of probes without any per-test expensive logic happening.
#    Since we can guarantee that nothing has changed, we really don't need
#    'stap' to paranoia check anything.  The workflow rationale is that even if
#    'stap' becomes extra-efficient about the caching, it still is beneficial
#    to be able to have a 2-phase workflow of 1) build probes then 2) run tests.
#    Were we to rely on inline caching and have flawed probes, we might not
#    realize it and have every test expensively try and build the probes and
#    fail.  (Currently, stap does a reasonable job of caching but it still takes
#    on the order of 5 seconds or so for our super expensive script with hot
#    cache.)
#
# The net goal is we want to be able to point this script at a systemtap file,
#  a directory tree structure containing the binaries, and have it be able to
#  both invoke that file as well as produce a systemtap script that could be
#  used by others without this script.

import imp, optparse, os.path, re, shutil, struct, subprocess, sys, time
import fcntl
import addrsymfilt
import json

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

        self.objdir = objdir

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

        # - @@namefromargs support
        self.suggested_relname = None

        # - @@outdir support
        self.cached_outdir_expr = None

        # - @@statement breakpoint support
        self.src_file_name = None
        self.method_name = None
        self.src_line = None

        self.cached_file_path = None
        self.cached_file_lines = None

        # - @@lib support / static variables
        self.arg_values = [context.exe_path]
        self.arg_descriptions = ['executable']
        self.known_libs = {'exe': '@1'}

        # - runtime variable definitions
        self.runtime_vars = {}
        self.runtime_descs = {}

        # -- @@stapbuildargs
        self.stap_build_args = []
        # -- @@staprunargs
        self.stap_run_args = []

        # -- @@postprocess
        self.postprocess_script = None

    def _add_static_arg(self, value, description):
        '''
        Define a new stap preprocessor argument with the given value and
        description, returning the text snippet that should be inserted into the
        resulting processed script.

        The value is what we pass to the command line invocation of 'stap'
        and is currently expected to be a string.

        This is done so that the generated .stp scripts are portable.  It does
        not make the generated modules any more or less cachable since a change
        in paths or binaries could easily require a module to be rebuilt.
        (Yes, this is somewhat redundant now given that we are also a driver
        script that must always be run every time now.)
        '''
        self.arg_values.append(value)
        self.arg_descriptions.append(description)
        return '@%d' % (len(self.arg_values),)

    def _def_runtime_var(self, name, value, description):
        '''
        Define a runtime variable.  This is a key/value pair that we tell to
        staprun when inserting the compiled module to parameterize it.
        '''
        self.runtime_vars[name] = value
        self.runtime_descs[name] = description

    def _stmt_stapbuildargs(self, val):
        self.stap_build_args = val.split(',')

    def _stmt_staprunargs(self, val):
        self.stap_run_args = val.split(',')

    def _stmt_postprocess(self, val):
        self.postprocess_script = val

    def _stmt_namefromargs(self, val):
        '''
        Allows the script to define a name for the output directory based on
        a weird custom syntax applied to the arguments intended for the
        command we are wrapping.

        We break the value up on colons, with the bits being:
        [search for this string, then search for this string, then slurp from
        the first character after the end of that string up to but not including
        the first character of this string.]

        The driving example is xpcshell tests where one of the arguments we are
        tunneling through is:

        const _TEST_FILE = ["/home/visbrero/rev_control/hg/comm-central/obj-thunderbird-debug/mozilla/_tests/xpcshell/storage/test/unit/test_statement_executeAsync.js"];

        That fellow follows a '-e' argument that says to execute that JS
        snippet.  So we want to be able to grab the relative path
        "storage/test/unit/test_statement_executeAsync.js" out of there.  The
        script line we expect to accomplish that is:
        //@@namefromargs:_TEST_FILE:/_tests/xpcshell/:"
        '''
        bits = val.split(':')
        seek_strs = bits[:-1]
        term_str = bits[-1]
        
        # flatten the sub-command's arugments out.
        arg_str = ' '.join(self.context.cmd_args)
        idx = 0
        for seek_str in seek_strs:
            idx = arg_str.find(seek_str, idx)
            if idx == -1:
                # this is only acceptable if we are not in a run mode
                if self.context.mode != 'run':
                    return
                # if we are running, this is fatal and we need to explode
                raise Exception('Unable to find seek str: ' + seek_str)
            idx += len(seek_str)
        term_idx = arg_str.find(term_str, idx)
        
        self.context.output_dir = os.path.join(self.context.output_base_dir,
                                               arg_str[idx:term_idx])

    def _stmt_outputdir(self, val):
        '''
        Associates the given global variable name with the output directory.
        Using this mechanism obligates the run mechanism to pass (or cause to
        be passed) an explicit value for the global variable to staprun.
        
        You would use this if your script is going to cause files to be written
        somewhere, like if you were to copy the /proc/PID/maps file.
        '''
        self._def_runtime_var(val, self.context.output_dir,
                              "output directory");

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
            # start on the line after our last match (we already added 1!)
            startLine = self.src_line
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


    def _expr_exe(self, val):
        '''
        Return the path of the executable.
        '''
        return self.known_libs['exe']

    def _expr_exeorlib(self, val):
        '''
        Take "@exeorlib:defaultbinary|bin/failover.so" and convert it to
        a @1/@2/so on.  The magic is that we split the argument on '|' and
        treat all but the last entry as possible binary names (sans dir).  If
        the binary is amongst those explicitly named, we provide its path.  If
        the binary was not named, then we fail over to using the library name
        provided.  The idea is that some binaries (ex: thunderbird-bin) may
        have libraries baked in (ex: libmozalloc.so) whereas some may not
        (ex: xpcshell).

        If the first character is a '!' it inverts the logic so that we
        use the lib if the executable is named.
        '''
        negated = (val[0] == '!')
        if negated:
            val = val[1:]

        bits = val.split('|')
        binary_names = set(bits[:-1])
        failover_lib = bits[-1]
        exe_name = os.path.basename(self.context.exe_path)

        # written for clarity, not conciseness
        if negated:
            if exe_name in binary_names:
                return self._expr_lib(failover_lib)
            return self.known_libs['exe']
        else:
            if exe_name in binary_names:
                return self.known_libs['exe']
            return self._expr_lib(failover_lib)

    def _expr_lib(self, val):
        '''
        Take "@@lib:bin/components/libgklayout.so" and convert it to @1/@2/...
        based on the allocated arg slots.
        '''
        if val in self.known_libs:
            return self.known_libs[val]

        path = self.context.find_lib_file(val)
        argexpr = self._add_static_arg(path, "Path to lib '%s'" % (val,))
        self.known_libs[val] = argexpr
        return argexpr

    def chew_script(self, path):
        self.input_script_path = path

        expr_re = re.compile(r'@@([^:]+):([^\)]*)([,\)])')
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
        
        self.written_script_path = out_path

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
            print '!!!!!!!!!!!! REWRITING !!!!!!!!!!!!!!'
            print '!!!!!!!!!!!! REWRITING !!!!!!!!!!!!!!'
            print '!!!!!!!!!!!! REWRITING !!!!!!!!!!!!!!'
        else:
            print '!!! FILES MATCH !!!', out_path

        self.out_lines = None

        # this is useful to know whether we can try and reuse a kernel module
        self.freshly_written_file = wrote_it

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
            if (seq is not None) and ((min_seq is None) or seq < min_seq):
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

# STAP_BIN_DIR = '/usr/bin'
STAP_BIN_DIR = '/local/code/systemtap/bin'
# (be nice to people who aren't me)
if not os.path.isdir(STAP_BIN_DIR):
    STAP_BIN_DIR = '/usr/bin'

class SystemtapDriverThing(object):
    usage = '''usage: %prog systemtapscript PID/executable [executable args]
    '''

    def __init__(self):
        self.stap_include_dirs = []

    def _build_parser(self):
        parser = optparse.OptionParser(usage=self.usage)

        parser.add_option('--build',
                          dest='mode', action='store_const', const='build',
                          default='run',
                          help='Build the module but do not run it.')
                          
        parser.add_option('--re-run',
                          help='Re-run the chew process for the given directory.',
                          dest='rerunpath',
                          default=None)
        parser.add_option('--out-base-dir',
                          help='Specify a base output directory.',
                          dest='output_base_dir',
                          default='/tmp/mozperfish')
        

        return parser

    def can_reuse_module(self, chewer):
        '''
        Return True if we can reuse the module and make sure the state is all
        available for the run stage.
        '''
        # Look for the JSON file in the object dir root where we store our
        #  chewed script file that tells us where the module lives and what
        #  the compilation arguments were.

        # - New .stp file? Cannot reuse!
        if chewer.freshly_written_file:
            return False

        cache_meta_path = os.path.join(chewer.context.objdir,
                                       'stap_cache_meta.json')

        # - No cache meta-data file? Cannot reuse!
        if not os.path.isfile(cache_meta_path):
            return False

        # - The meta-data file's timestamp is older than the stp file?
        cache_ts = os.stat(cache_meta_path).st_mtime
        script_ts = os.stat(chewer.written_script_path).st_mtime
        if script_ts > cache_ts:
            return False

        # (Load the meta-data)
        try:
            f = open(cache_meta_path, 'r')
            try:
                meta = json.load(f)
            finally:
                f.close()
        except:
            # if the file is full of gibberish, it's no good!
            return False

        # - The module went away?
        module_path = meta['module']
        if not os.path.isfile(module_path):
            return False

        # - The arguments changed?
        # - The files referenced by the arguments changed?
        meta_args = meta['args']
        if len(chewer.arg_values) != len(meta_args):
            return False
        for i, cur_arg_value in enumerate(chewer.arg_values):
            meta_arg_info = meta_args[i]
            # value
            if meta_arg_info['value'] != cur_arg_value:
                print 'Arg', i, 'mismatch!'
                print '  Current:', cur_arg_value
                print '  Cached: ', meta_arg_info['value']
                return False
            # timestamp
            if os.stat(cur_arg_value).st_mtime != meta_arg_info['mtime']:
                print 'Arg', i, 'timestamp problem on', cur_arg_value
                return False
        
        # - We can reuse!  Stash the module name for the run step.
        self.probe_module_path = module_path
        return True
        
    def _write_module_cache(self, chewer):
        meta = {}
        meta['module'] = self.probe_module_path
        meta['args'] = meta_args = []
        for cur_arg_value in chewer.arg_values:
            meta_arg_info = {}
            meta_arg_info['value'] = cur_arg_value
            meta_arg_info['mtime'] = os.stat(cur_arg_value).st_mtime
            meta_args.append(meta_arg_info)

        cache_meta_path = os.path.join(chewer.context.objdir,
                                       'stap_cache_meta.json')
        
        f = open(cache_meta_path, 'w')
        # do a (mortal) human readable dump
        json.dump(meta, f, indent=2)
        f.close()
        
        

    def build_module(self, chewer):
        '''
        Run 'stap' telling it to build a module for insertion by staprun, but
        do not run the module at this time.

        On success update the cache stash in the object directory that will
        tell us where to find the module on our next run and how to validate
        that it is still up-to-date.
        '''
        stap_args = [os.path.join(STAP_BIN_DIR, 'stap'),
                     '-p4']

        for incl_dir in self.stap_include_dirs:
            stap_args.append('-I')
            stap_args.append(incl_dir)

        # the script tells us what arguments it wants
        stap_args.extend(chewer.stap_build_args)

        # the built script
        stap_args.append(chewer.written_script_path)
        # the library paths
        stap_args.extend(chewer.arg_values)

        print ''
        print '!!! Invoking:', repr(stap_args)
        print ''

        # give it a pipe for standard input so it keeps its mitts off our
        #  control-c.
        # give it a pipe for stdout so we can read the location of where the
        #  cached output went
        # give it a pipe for stderr so we can see any interesting error
        #  messages but reduce our burden of confusing that with the 'answer'
        #  of where the module ended up
        pope = subprocess.Popen(stap_args,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        stdout_data, stderr_data = pope.communicate()
        
        print '====\nSTDOUT:'
        print stdout_data
        print '====\nSTDERR:'
        print stderr_data

        if pope.returncode != 0:
            raise Exception('Failure building module')

        self.probe_module_path = None
        for line in stdout_data.splitlines():
            if line.startswith('/') and line.endswith('.ko'):
                self.probe_module_path = line
                break
        if self.probe_module_path is None:
            raise Exception('Somehow failed to get the module path?')

        self._write_module_cache(chewer)


    def go(self):
        '''
        This is the driver function which parses the command line and decides
        what activities need to occur based on the requested mode and the
        state of cached things.

        Major modes:
        - build: Chew the script, use stap to build the kernel module if needed.
        - run: Everything that build suggests plus activating the probes via
           staprun and then either forking off a child process or attaching to
           an existing process.  Trigger a post-processing script afterwards
           if configured.
        - process: Just re-run the processing script assuming we are told the
           right output directory.
        '''
        print '!!!', os.getpid(), 'ARGS YOU GAVE ME:', repr(sys.argv)

        parser = self._build_parser()
        options, args = parser.parse_args()


        # -- Parser inferences...
        if options.rerunpath:
            options.mode = 'process'
        self.mode = options.mode

        # -- Translate modes to actions
        if self.mode == 'build':
            self.doBuild = True
            self.doRun = self.doProcess = False
        elif self.mode == 'run':
            self.doBuild = self.doRun = self.doProcess = True
        elif self.mode == 'process':
            self.doProcess = True
            self.doBuild = self.doRun = False
        else:
            raise Exception('Bad mode: ' + self.mode)

        # we need to know the input script and executable (or pid) for everyone
        if len(args) < 2:
            parser.print_usage()
            return 1

        
        # -- Build Context
        self.build_context(options, args)

        # -- Chew
        chewer = self.process_script(options, args)

        # -- Build
        # (This will cache/reuse cache when possible.)
        if self.doBuild:
            if not self.can_reuse_module(chewer):
                self.build_module(chewer)
            
        # -- Run
        if self.doRun:
            self.run(chewer, args)

        # -- Process
        if self.doProcess:
            # If we are in 'process' mode, the output directory is explicitly
            #  told to us, which is important because there is no other way
            #  we can remotely figure this out correctly.  (Which is also why
            #  we clobber this way down here.)
            if self.mode == 'process':
                chewer.context.output_dir = options.rerunpath
            self.post_process(chewer, self.run_pid)
        return 0


    def build_context(self, options, args):
        # - Figure out attach versus spawn
        # if the second argument is a number then it must be the PID
        if self.doRun and args[1].isdigit():
            self.runMode = 'attach'

            self.run_naming_pid = self.run_pid = int(args[1])

            # use thie pid to get the binary and from that the objdir
            self.proc_dir = '/proc/%d' % (self.run_pid,)
            exe_path = os.path.realpath(os.path.join(self.proc_dir, 'exe'))

        # otherwise it is the path to the executable
        else:
            # (we may not actually be in a run mode, but the semantics are
            #  that of spawn mode)
            self.runMode = 'spawn'

            # use our invocation's process number as the naming pid...
            self.run_naming_pid = os.getpid()
            # Indicate we don't have a pid; this completely prevents us
            #  from performing _any_ address translations for the time
            #  being.  Eventually we could perhaps have probes that
            #  handle the mapping events on the fly (from the log...)
            self.run_pid = None
            exe_path = args[1]

        # systemtap === linux
        pathparts = exe_path.split('/')

        objdir = self._figure_out_objdir(pathparts)

        context = self.context = self._make_context(objdir)
        context.output_base_dir = options.output_base_dir
        context.exe_path = exe_path
        context.mode = self.mode

        if options.rerunpath:
            trace_dir = context.output_dir = options.rerunpath
        else:
            # provide a reasonable default for the directory
            # (the chewer may clobber this)
            trace_dir = os.path.join(options.output_base_dir,
                                     'chewtap-%d' % (self.run_naming_pid,))
            if os.path.exists(trace_dir):
                trace_dir += '-%d' % (int(time.time()),)
            context.output_dir = trace_dir
        
        context.cmd_args = args[1:]


    def process_script(self, options, args):
        # put our built script in the objdir...
        tapscript = args[0]
        built_tapscript = os.path.join(self.context.objdir,
                                       os.path.basename(tapscript))

        chewer = self.chewer = ScriptChewer(self.context)
        chewer.chew_script(tapscript)

        # build and run require updating the script (if required)
        if self.mode != 'process':
            chewer.maybe_write_script(built_tapscript)
            # nuke the directory to avoid stale contents.
            if os.path.exists(self.context.output_dir):
                # but only if we're sure the path is remotely safe...
                if self.context.output_dir.startswith('/tmp/'):
                    shutil.rmtree(self.context.output_dir, True)
            os.makedirs(self.context.output_dir)

        return chewer


    def _attach_pre_run_legwork(self):
        '''
        Steal any information from the /proc/PID directory that we need
        just prior to the run.  This wants to happen after the chewing of the
        script so that any conclusions like the output directory are already
        known.
        
        Currently we need:
        - the maps file that tells us about the memory map
        '''
        shutil.copyfile(os.path.join(self.proc_dir, 'maps'),
                        os.path.join(self.context.output_dir, 'maps'))

    def run(self, chewer, args):
        '''
        Handle either spawning a child process or attaching to an existing
        process while (either way) spinning up an staprun instance.
        '''

        if self.runMode == 'attach':
            self._attach_pre_run_legwork()

        # -- FORK if running and not in attached mode
        if self.runMode == 'spawn':
            # clean out our pipes prior to forking!
            sys.stdout.flush()
            sys.stderr.flush()

            kid_read_pipe, parent_write_pipe = os.pipe()
            naming_pid = kid_pid = pid = os.fork()

            if kid_pid == 0:
                # I am the child!  wait for our parent to tell us it's cool
                #  to invoke the thinger.
                while True:
                    b = os.read(kid_read_pipe, 1)
                    if b == 'x':
                        break
                    time.sleep(0.05)

                sys.stdout.write('@@@ read my 1 byte! execing other thing!\n')
                sys.stdout.flush()
                os.execv(args[1], args[1:])
                # THE PROCESS IS REPLACED BY THE ABOVE, NOTHING MORE EVER
                #  HAPPENS!
            # (I am the parent process if I am here)

            print '!!! forked off child', kid_pid
        else:
            naming_pid = self.run_naming_pid
            pid = self.run_pid
            kid_pid = None

        # -- RUN systemtap
        # - build args
        # assume the user is in the stapdev group
        stap_args = [os.path.join(STAP_BIN_DIR, 'staprun')]

        # add this python script's directory as an include dir for .h files.
        if '/' in sys.argv[0]:
            self.stap_include_dirs.append(os.path.dirname(sys.argv[0]))

        # the script tells us what arguments it wants
        stap_args.extend(chewer.stap_run_args)
        # while -b is a build-time option (that can be overridden at runtime),
        #  -o is a runtime flag.
        if '-b' in chewer.stap_build_args:
            stap_args.append('-o%s' % (os.path.join(chewer.context.output_dir,
                                                    'bulk'),))
        
        # - run
        # The expected use-case is to hit control-c when done, at which point
        #  we want to tell stap to close up shop.
        # If we're not attaching, then we need to spin the dude up.  staprun
        #  is being a jerk in terms of not screwing up the environment,
        #  so we're doing it ourself.  We really want to constrain the
        #  stap invocation to the right process, so we fork so we can know
        #  the child pid before execing.  

        # we need a -v so we can know when it has gone active.
        stap_args.append('-v')
        stap_args.append('-v')

        # - spin up
        stap_args.extend(['-x', '%d' % (pid,)])

        # - add the module path and the module arguments
        stap_args.append(self.probe_module_path)
        for runtime_var_name, runtime_var_value in chewer.runtime_vars.items():
            stap_args.append(runtime_var_name + '=' + runtime_var_value)

        print ''
        print '!!! Invoking:', repr(stap_args)
        print ''

        # give it a pipe for standard input so it keeps its mitts off our
        #  control-c.
        # give it a pipe for stdout so we can tell when it has gotten going
        pope = subprocess.Popen(stap_args,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            # - wait for 'stap' to successfully load the stuff
            # (make the stdout non-blocking)
            stap_stdout_fd = pope.stdout.fileno()
            fl = fcntl.fcntl(stap_stdout_fd, fcntl.F_GETFL)
            fcntl.fcntl(stap_stdout_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            # (keep reading stdout and printing the output until we see
            #  the 'go' output or the process dies.)
            buf = ''
            while True:
                try:
                    while True:
                        nbuf = pope.stdout.read(1024)
                        if not nbuf:
                            break
                        sys.stdout.write(nbuf)
                        sys.stdout.flush()
                        buf += nbuf                        
                except Exception, e:
                    # this happens when we run out of things to read
                    pass

                if buf.find('probe_start() returned 0') != -1:
                    break
                if pope.poll() is not None:
                    # he died!
                    print 'stap creation failed; killing child and leaving'
                    if kid_pid:
                        os.kill(kid_pid, 9)
                    sys.exit(1)
                # truncate the buf on newline bounds
                idx_newline = buf.rfind('\n')
                if idx_newline != -1:
                    buf = buf[idx_newline + 1:]

                # sorta busy-wait...
                time.sleep(0.1)

            # Write to the child so it can begin its exciting life as being
            #  obliterated and replaced by the actual executable we want
            #  to run.
            if self.runMode == 'spawn':
                # flush our output before telling the child so that our
                #  output serializes somewhat...
                print '!!!', os.getpid(), 'writing to child!'
                sys.stdout.flush()
                sys.stderr.flush()
                os.write(parent_write_pipe, 'x')

            print '!!! Hit control-C to terminate the tapscript'
            sys.stdout.flush()


            # wait for something to die off doing our own communicate()
            #  style loop to make sure the stap invocation does not clog
            #  itself up somehow.
            while True:
                try:
                    while True:
                        buf = pope.stdout.read(1024)
                        if not buf:
                            break
                        sys.stdout.write(buf)
                        sys.stdout.flush()
                except Exception, e:
                    pass

                dead_pid, dead_status = os.waitpid(-1, os.WNOHANG)
                if dead_pid == 0:
                    time.sleep(0.1)
                elif dead_pid == kid_pid:
                    print '!!! Happy conclusion!'
                    sys.stdout.flush()
                    pope.terminate()
                    # try and make sure we wait for staprun to clean up
                    #  after itself, and output anything interesting it
                    #  says.
                    print pope.communicate()[0]
                    break
                else: # it was stap!
                    print '!!! stap died', dead_status, 'not post-processing'
                    print 'Any results will be in', chewer.context.output_dir
                    sys.stdout.flush()
                    if kid_pid:
                        os.kill(kid_pid, 9)
                    sys.exit(1)

        except KeyboardInterrupt:
            # (python2.6 required)
            pope.terminate()
            if kid_pid:
                os.kill(kid_pid, 9)

    def post_process(self, chewer, pid):
        if chewer.postprocess_script:
            trace_dir = chewer.context.output_dir
            # provide it with the address sym filter; assuming required.
            procinfo = addrsymfilt.ProcInfo(pid,
                                            os.path.join(trace_dir, 'maps'))

            # first look in the directory the input .stp file came from
            search_path = [
                os.path.dirname(os.path.abspath(chewer.input_script_path))]
            # then check the python path
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
                bulkproc = BulkProcessor(trace_dir)
                modproc = module.Processor()
                modproc.process(trace_dir, bulkproc, procinfo)

class MozMain(SystemtapDriverThing):
    def _figure_out_objdir(self, pathparts):
        # comm-central?
        if pathparts[-4] == 'mozilla':
            objdir = '/'.join(pathparts[:-4])
        # mozilla-central
        else:
            objdir = '/'.join(pathparts[:-3])

        return objdir

    def _make_context(self, objdir):
        return MozChewContext(objdir)

if __name__ == '__main__':
    # change to the directory of the script if specified absolutely...
    m = MozMain()
    sys.exit(m.go())
