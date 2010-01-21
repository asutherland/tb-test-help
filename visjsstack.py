
'''
Parse a jsstack.emt emitted trace data, chew it, and push it to the performance
data couch.  This should probably end up a JS file at some point.

The general idea is that each performance run or sample-set gets stored in its
own CouchDB database.  Strictly speaking, there is no reason why we couldn't
cram multiple unrelated data sets into a single db, but there is no real
advantage either.  The only benefit to co-location is to allow the views to
operate in a single space.  This primarily benefits reduce cases for summarizing
aggregate load of a given function.  So we'll plan for that for co-location.

As our current implementation is profiling based and not trace based, there is
little utility in maintaining the sequential ordering of samples.  There is
potentially utility in binning samples in aggregate into time buckets for when
operation proceeds in phases whose duration exceeds our bucket sizes by a
sufficient amount that we get at least one clean bucket without edge effects.

=== Use-Cases

== Overview

* Support a file/class/function-level graph overview of the call
  relationship with hotspots indicated on both nodes and edges.

For functions, implies the ability to find top nodes in the graph and load
connecting segments.  For class/file aggregations, we either need to precompute
the (synthetic) nodes or use reduce functionality to effectively end up with the
same thing.  Precompute wins because it allows for annotations, is easier to
debug, and the reduce approach would eventually end up as a brutalization of the
reduce mechanism.

== Focus

* Pecobro-style time-binned histogram for time the call was the leaf or just in
  the chain.

Implies the ability to retrieve the performance information for the function

* Show localized version of the overview graph.


=== UI mods required (these desires should be moved into the JS)

== Configurable automatic retrieval

We currently automatically fetch comments.  We could make that more generic and
simply enabled by default.  When in performance analysis mode, performance data
from a given perf store would be automatically retrieved when displaying
things.

'''

class InvocInfo(object):
    __slots__ = ["path", "funcname", "line", "calls", "calledby"]
    def __init__(self, path, funcname, line):
        self.path = path
        self.funcname = funcname
        self.line = line

class ProfParser(object):
    def __init__(self):
        pass

    def _chew_block(self, ts, js_lines):
        for line in js_lines:
            line = line.strip()

            # file URLs should be normalized to resource URLs
            if line.startswith("file:"):
                idx = line.find("modules/") + 8
                bits = line[idx:].split(":")
            else if line.startswith("chrome:"):
                idx = line.find("content/") + 8
                bits = line[idx:].split(":")
            else if line.startswith("<NULL"):
                bits = line[line.find(">")+1:].split(":")
                bits[0] = "native"

            path, funcname, lineno = bits
            fmap = self.files.get(path)
            if fmap is None:
                fmap = self.files[path] = {}
            invoc = fmap.get(lineno)
            if invoc is None:
                invoc = fmap[lineno] = InvocInfo(path, funcname, lineno)

    def parse(self, f):
        self.files = {}

        block_ts = None
        block_js_lines = None
        for line in f:
            if line.startswith("***"):
                if block_ts is not None:
                    self._chew_block(block_ts, block_js_lines)
                block_ts = int(line[line.find(':') + 1], 16)
                block_js_lines = []
            elif line.startswith("JS stack:"):
                pass
            else:
                block_js_lines.append(line)
        # close out any pending dude
        if block_ts:
            self._chew_block(block_ts, block_js_lines)
