# Process the output of mozperfish.stp
#
# See mozspeedtrace.stp to understand what the gameplan is and then this file
# for the specifics.
#
# Our outputs are as follows:
# - A big JSON file whose schema is like so: {
#     threads: [
#       {
#         events: [],
#         mevents: []
#       },
#       ... more threads ...
#     ],
#     lastEventEndsAtTime: 0,
#   }

import json, os, os.path

class ProcContext(object):
    '''
    A simple context object that provides known attributes and generic helper
    functions.
    '''
    def __init__(self, srcdir, procinfo):
        self.srcdir = srcdir
        self.procinfo = procinfo

        self.outdir = os.path.join(srcdir, 'out')
        if not os.path.exists(self.outdir):
            os.mkdir(self.outdir)

    def symlink_web_files_to_output_dir(self):
        '''
        Symlink our web interface files into the output directory where we
        are also writing perfdata.json.
        '''
        web_templ_dir = os.path.join(os.path.dirname(__file__), 'webface')        
        for fname in os.listdir(web_templ_dir):
            # ignore emacs scratch files :)
            if fname.endswith('~'):
                continue
            src_file = os.path.join(web_templ_dir, fname)
            if os.path.isfile(src_file):
                dest_link = os.path.join(self.outdir, fname)
                if not os.path.exists(dest_link):
                    os.symlink(src_file, dest_link)
                

    def write_results_file(self, json_obj):
        path = os.path.join(self.outdir, 'perfdata.json')
        f = open(path, 'w')
        json.dump(json_obj, f)
        f.close()

EV_EVENT_LOOP = 0x1000

REPARENTING_EVENTS = set([EV_EVENT_LOOP])

class ThreadProc(object):
    '''
    Tracks per-thread information.
    '''

    def __init__(self, context, tid):
        self.context = context
        self.tid = tid
        # the top-level sequence to report in the output file
        self.next_sequence = 0

        self.prev_top_end_time = 0
        self.top_event_needing_fixup = None

        # create the stack with sentinel.
        # each elment is (depth, list of items at that depth)
        self.stack = [(0, ())]

        #: Structured timeline events reflecting the actual call stack structure
        #   and accordingly with non-overlapping timelines.
        self.events = []
        #: Normalized event-loop events as root events (event if they are nested
        #   inside an existing event loop invocation) as top-level.  Because
        #   we are still using a native stack, re-parented events will be
        #   entirely contained time-wise by a preceding event.
        #  This is computed by transforming the contents of events as a
        #   post-processing pass.
        self.levents = None
        #: memory events; exist outside of the structured event perspective
        self.mevents = []

    def _derive_event_loop_events(self):
        self.levents = levents = []

        def transform_event(event):
            '''
            Copy the event and its children; if a child should be reparented to
            the top-level, contribute it to levents instead of the event we are
            currently processing.
            '''
            clone = event.copy()
            # bail if it has no children and so there is nothing more to do
            if ('children' not in event) or (len(event['children']) == 0):
                return clone
            # clone the children, handling reparenting as needed
            clone['children'] = clone_kids = []
            for kid_event in clone['children']:
                if kid_event['type'] in REPARENTING_EVENTS:
                    levents.append(transform_event(kid_event))
                else:
                    clone_kids.append(transform_event(kid_event))
            return clone

        for top_level_event in self.events:
            levents.append(transform_event(top_level_event))

    def build_json_obj(self):
        self._derive_event_loop_events()
        return {
            'tid': self.tid,
            'events': self.events,
            'levents': self.levents,
            'mevents': self.mevents
            }

    def chew(self, obj):
        ## this is getting out of control, need to normalize by:
        # 1) Having synthetic top-level events just get created with correct
        #    time data.
        # 2) Handling memory event types either completely separately or
        #    exposed as 0 duration.
        obj_depth = obj['depth']

        # -- normalize into output form
        # - delete fields that were just for us
        del obj['tid']
        del obj['depth']

        # - transform units as appropriate
        if 'time' in obj:
            # integer nS => float mS
            obj['time'] *= 0.000001
        else:
            obj['time'] = self.prev_top_end_time

        # - figure out the type of event...
        if 'mtype' in obj:
            # it's a memory event!
            self.mevents.append(obj)
            return

        if 'duration' in obj:
            obj['duration'] *= 0.000001
        else:
            # this is a synthetic inter-space event
            self.top_event_needing_fixup = obj
            self.events.append(obj)
            return

        data = obj['data']
        # - perform address translation on potentially affected fields
        if 'scriptName' in data and data['scriptName'].startswith(':!'):
            data['scriptName'] = \
                self.context.procinfo.transformString(data['scriptName'])
        if ('callerScriptName' in data and
                data['callerScriptName'].startswith(':!')):
            data['callerScriptName'] = \
                self.context.procinfo.transformString(data['callerScriptName'])

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
                if self.top_event_needing_fixup:
                    self.top_event_needing_fixup['duration'] = (
                        obj['time'] - self.top_event_needing_fixup['time'])
                    self.top_event_needing_fixup = None
                self.prev_top_end_time = obj['time'] + obj['duration']
                self.events.append(obj)
            else:
                cur_stack.append(obj)
        else: # obj_depth > cur_depth
            self.stack.append((obj_depth, [obj]))
            

    def allDone(self):
        self.f.write(self.context.templ_bits[1])
        self.f.close()
        self.f = None


class Processor(object):
    def process(self, srcdir, streamer, procinfo):
        '''
        Each thread handles its own processing; we just need to create them
        as needed and close them out when we run out of events.
        '''
        context = ProcContext(srcdir, procinfo)

        thread_procs = {}

        obj = None

        # eat the lines
        for blob in streamer:
            for line in blob.splitlines():
                if line[0] != '{':
                    print 'Ignoring line:', line.rstrip()
                    continue
                # transform trailing stuff...
                line = line.replace(',}', '}')
                try:
                    obj = json.loads(line)
                except Exception, e:
                    print 'BIG TROUBLE IN LITTLE STRING:', line
                    raise e

                tid = obj['tid']
                if tid in thread_procs:
                    tproc = thread_procs[tid]
                else:
                    tproc = thread_procs[tid] = ThreadProc(context, tid)

                tproc.chew(obj)
                    

        lastEventEndsAtTime = obj['time']
        if 'duration' in obj:
            lastEventEndsAtTime += obj['duration']

        # tell the thread procs we have no more lines
        thread_objs = [tp.build_json_obj() for tp in thread_procs.values()]
        json_obj = {
            'threads': thread_objs,
            'lastEventEndsAtTime': lastEventEndsAtTime
            }

        context.write_results_file(json_obj)
        context.symlink_web_files_to_output_dir()
            
            
