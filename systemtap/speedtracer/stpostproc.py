# Process the output of mozspeedtrace.stp
#
# See mozspeedtrace.stp to understand what the gameplan is and then this file
# for the specifics.
#
# Our outputs are as follows:
# - One HTML file per thread with the HTML file being fashioned to cause
#   SpeedTracer to see it as one of its own and volunteer to open it.  We
#   place this file 

import json, os, os.path

class ProcContext(object):
    def __init__(self, srcdir):
        self.srcdir = srcdir

        self.outdir = os.path.join(srcdir, 'out')
        if not os.path.exists(self.outdir):
            os.mkdir(self.outdir)

        self._read_templates()

    def _read_templates(self):
        templ_path = os.path.join(os.path.dirname(__file__), 'template.html')
        f = open(templ_path, 'r')
        data = f.read()
        f.close()

        # look at our elegant templating language! so shiny!
        self.templ_bits = data.split("@@DATA@@")

    def make_file_for_thread(self, tid):
        fname = 'thread_%d.html' % (tid,)
        path = os.path.join(self.outdir, fname)
        return open(path, 'w')

class ThreadProc(object):
    '''
    Tracks per-thread information.  This consists of the 
    '''

    def __init__(self, context, tid):
        self.context = context
        self.tid = tid
        # the top-level sequence to report in the output file
        self.next_sequence = 0

        # create the stack with sentinel.
        # each elment is (depth, list of items at that depth)
        self.stack = [(0, ())]

        self.f = self.context.make_file_for_thread(tid)
        self.f.write(context.templ_bits[0])

    def chew(self, obj):
        obj_depth = obj['depth']

        # -- normalize into output form
        # - delete fields that were just for us
        del obj['tid']
        del obj['depth']

        # - transform units as appropriate
        # integer nS => float mS
        obj['time'] = obj['time'] * 0.000001
        obj['duration'] = obj['duration'] * 0.000001

        # - add fields...
        obj['children'] = ()
        
        cur_depth, cur_stack = self.stack[-1]
        # Anytime we are seeing an object with a depth less than the current
        #  stack, it must be the parent of the current stack.
        if obj_depth < cur_depth:
            if obj_depth != cur_depth - 1:
                raise Exception('Obj depth %d with cur depth %d' %
                                (obj_depth, cur_depth))
            obj['children'] = cur_stack
            self.stack.pop()
            cur_depth, cur_stack = self.stack[-1]
            
        if obj_depth == cur_depth:
            if obj_depth == 0:
                obj['sequence'] = self.next_sequence
                self.next_sequence += 1
                self.f.write(json.dumps(obj)+'\n')
            else:
                cur_stack.append(obj)
        else: # obj_depth > cur_depth
            self.stack.append((obj_depth, [obj]))
            

    def allDone(self):
        self.f.write(self.context.templ_bits[1])
        self.f.close()
        self.f = None


class Processor(object):
    def process(self, srcdir, streamer):
        '''
        Each thread handles its own processing; we just need to create them
        as needed and close them out when we run out of events.
        '''
        context = ProcContext(srcdir)

        thread_procs = {}

        # eat the lines
        for line in streamer:
            if line[0] != '{':
                print 'Ignoring line:', line.rstrip()
                continue
            obj = json.loads(line)

            tid = obj['tid']
            if tid in thread_procs:
                tproc = thread_procs[tid]
            else:
                tproc = thread_procs[tid] = ThreadProc(context, tid)

            tproc.chew(obj)

        # tell the thread procs we have no more lines
        for tproc in thread_procs.values():
            tproc.allDone()
            
            
