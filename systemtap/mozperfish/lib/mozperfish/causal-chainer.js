/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at:
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is Mozilla Messaging Code.
 *
 * The Initial Developer of the Original Code is
 *   The Mozilla Foundation
 * Portions created by the Initial Developer are Copyright (C) 2010
 * the Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *   Andrew Sutherland <asutherland@asutherland.org>
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

/**
 * Process the mozperfish JSON blob to establish causal chains.  The goal is to
 *  assign every event-loop event to a containing a causal chain.
 *
 * Chains are established and linked by trace events that will cause a future
 *  event loop event to execute and the trace events that are the execution
 *  of that promised future event.  Chains may form graphs if a 'chain' causes
 *  multiple outstanding events to exist concurrently.
 *
 * For example, code 'foo' may issue an asynchronous database query which will
 *  trigger a callback.  If the active event for 'foo' terminates without
 *  scheduling any other events, we observe events for the execution of the
 *  asynchronous database execution, and then witness the scheduling and
 *  execution of the callback for 'foo', we can link them all together in
 *  a single causal chain.  In contrast, if code 'bar' were to issue two
 *  asynchronous queries with callbacks, we would perceive that as the splitting
 *  of the chain.  If one of the callbacks were to terminate without scheduling
 *  another future event, we can attempt to model that as the chains merging
 *  back into a single chain.
 **/

require.def("mozperfish/causal-chainer",
  [
    "exports",
  ],
  function(
    exports
  ) {

var EV_TIMER_INSTALLED = 5, EV_TIMER_CLEARED = 6, EV_TIMER_FIRED = 7;
var EV_LOG_MESSAGE = 11;
var EV_GC = 17;
var EV_ELOOP_EXECUTE = 4096, EV_ELOOP_SCHEDULE = 4097;
var EV_INPUT_READY = 4128, EV_INPUT_PUMP = 4129;
var EV_SOCK_READY = 4144, EV_SOCK_ATTACH = 4145, EV_SOCK_DETACH = 4146;
var EV_XPCJS_CROSS = 4160, EV_JSEXEC_CROSS = 4161;
var EV_PROXY_CALL = 4192;
var EV_LATENCY = 8192;

/**
 * Models a linear run of events in a causal chain without splitting or merging.
 *  The piece tracks incoming and outgoing edges.  You can think of this as a
 *  basic block in the compiler parlance if you are so inclined.
 */
function ChainPiece() {
  this.incoming = [];
  this.events = [];
  this.outgoing = [];
}
ChainPiece.prototype = {
};

var MARK_SELECTED = 1, MARK_ANCESTOR = 2, MARK_DESCENDENT = 3;

/**
 * Simple graph atom for the first-pass of causal chain construction.  There is
 *  one cancelable ChainLink for every event top-level event and it has zero or
 *  more links to other ChainLinks.
 *
 * These links will be analyzed and transformed into ChainPieces in a subsequent
 *  processing pass.
 */
function ChainLink(event) {
  this.event = this.semEvent = event;
  this.mark = null;
  this.primary = false;
  this.synthetic = false;
  this.inlinks = [];
  this.outlinks = [];
}
ChainLink.prototype = {
  linkOutgoing: function(other) {
    this.outlinks.push(other);
    other.inlinks.push(this);
    // XXX hideous propagation of ill-named "clusters"
    // (currently just names the thread of the root of the causal chain
    //  which pretty much only happens because we fail to properly attribute
    //  some events on non-main-threads.)
    // (it needs to be on the event so the current groupCluster function,
    //  because it takes an event.  It 'needs' to come from the ChainLink
    //  because the thread root chain link has no event associated/is null.
    //  obviously, lots of potential work here!)
    other.event.cluster = other.cluster = this.cluster;
  },
  _markHelper: function(valattr, val, attrname) {
    var list = this[attrname];
    for (var i = 0; i < list.length; i++) {
      var o = list[i];
      o[valattr] = val;
      o._markHelper(valattr, val, attrname);
    }
  },
  markSelected: function() {
    this.mark = MARK_SELECTED;
    this._markHelper("mark", MARK_ANCESTOR, "inlinks");
    this._markHelper("mark", MARK_DESCENDENT, "outlinks");
  },
  clearMark: function() {
    this.mark = null;
    this._markHelper("mark", null, "inlinks");
    this._markHelper("mark", null, "outlinks");
  },
  markPrimaryCausalChain: function() {
    this.primary = true;
    this._markHelper("primary", true, "inlinks");
  },
};
exports.ChainLink = ChainLink;

function Phase() {
}
Phase.prototype = {
};
exports.Phase = Phase;

function ExecContext() {
  this.children = [];
}
ExecContext.prototype = {
};
exports.ExecContext = ExecContext;

function Zing() {
}
Zing.prototype = {
};

/**
 * Instantiate a new causal chainer for the given perfish blob.
 *
 * @args[
 *   @param[perfishBlob PerfishBlob]
 * ]
 */
function CausalChainer(perfishBlob, logProcessor) {
  this.perfishBlob = perfishBlob;
  this.logProcessor = logProcessor;

  this.rootLinks = [];

  // Broad, non-nestable phases of operation.  currently assumed to be
  //  populated by the logProcessor.
  this.phases = [];

  // Nestable execution contexts associated with specific threads.
  this.contexts = [];

  // Non-nestable specific events with duration associated with specific
  //  threads.  These are interesting even if they are really short (ex: GC),
  //  but may be aggregatable if a lot of them happen in a short time period.
  // The name choice is random because 'mark' already has a specific protovis
  //  usage and pretty much anything will be hand wavy.  Also, this way, I
  //  can maybe make a reference to "the ultimate zing", which watchers of
  //  sealab 2021 will appreciate.
  this.zings = [];

  // Count the number of events that get pruned out of the graph but that
  //  might merit investigation if this number gets really high.
  this.pruneCount = 0;

  /**
   * @dictof[
   *   @key["thread id"]
   *   @value[@dictof[
   *     @key["event id"]
   *     @value[@listof[ChainLink]]
   *   ]]
   * ]
   */
  this.pendingEvents = {};
  /**
   * @dictof[
   *   @key["timer id"]
   *   @value[ChainLink]
   * ]
   */
  this.pendingTimers = {};
  /**
   * Sockets provide an inherently sequential ordering of their links.  As such
   *  every time we see a new socket ready event we update the link associated
   *  with the fd to be that new link.  (And in the base case we set the link
   *  to the link active when the attach was processed.)
   *
   * @dictof[
   *   @key["socket fd"]
   *   @value[ChainLink]
   * ]
   */
  this.pendingSockets = {};
}
CausalChainer.prototype = {
  /**
   * Basic strategy:
   * @itemize[
   *   @item{
   *     Create root causes for any threads that appear to not just be event
   *     loop spinning threads.  This should probably just be the main thread,
   *     but there's no real need to assume.  Event loop spinners should
   *     consist entirely of event-loop executions with their last event being
   *     an event loop dispatch if/when they get shut down.
   *   }
   *   @item{
   *     Process all threads at the same time, consuming events in a
   *     gseq ordered fashion.  Regrettably, the time appears to suffer from
   *     skew issues across processor cores.  This allows us to do the pending
   *     event bookkeeping happily.
   *   }
   *   @item{
   *     Treat actions that may/will result in the execution of future events
   *     as out-links of the given event.  In this pass If an event has an out-link count
   *     greater than 1, 'fork' its causal chain.  If an event has an out-link
   *     of exactly one, it can stay part of the same chain link.  If it's
   *     out-link is zero, then we can potentially fold it back into its
   *     parent.
   *   }
   * ]
   */
  chain: function CausalChainer_chain() {
    var self = this;
    // causal chains for threads when they do non-event-loop top-level stuff.
    var thread_roots = [];

    // -- logic to pick off the events in increasing time order
    var threads = this.perfishBlob.threads;
    var eventLists = [], eventOffsets = [], iThread;

    for (iThread = 0; iThread < threads.length; iThread++) {
      var thread_events = threads[iThread].levents;
      // Mark the last event as boring if it's a thread-shutdown event post
      //  so that we can just ignore it.  (It's boring.)
      // XXX this heuristic is proving annoying so I am disabling it.  It is
      //  seems to be marking a nsHostResolver thread's legitimate activities
      //  as boring because the thread never seems to shutdown according to
      //  our probes.  (And the event is a single 4097.)  If we end up being
      //  more aware of nsHostResolver, we could likely moot this.
      /*
      if (thread_events.length &&
          thread_events[thread_events.length - 1].type == EV_ELOOP_SCHEDULE)
        thread_events[thread_events.length - 1].boring = true;
      */

      eventLists.push(thread_events);
      eventOffsets.push(0);
      thread_roots.push(null);
    }
    function get_next_event() {
      var min_event = null, min_idx = null;
      for (var i = 0; i < threads.length; i++) {
        if (eventOffsets[i] >= eventLists[i].length)
          continue;
        var cand_event = eventLists[i][eventOffsets[i]];
        if (min_event === null || cand_event.gseq < min_event.gseq) {
          min_idx = i;
          min_event = cand_event;
        }
      }
      if (min_event) {
        eventOffsets[min_idx]++;
        min_event.thread_idx = min_idx;
      }
      return min_event;
    }

    // --- processing loop
    var event, semEvent, link, thread_link, parent_link, death = 0, links;
    while ((event = get_next_event())) {
      // save off the thread index; if we unbox we may lose access to the info
      //  because we only poke it back into top-level events.
      var thread_idx = event.thread_idx;

      // -- Event Loop Execution
      // (we know this must be an event loop execution, but we can potentially
      //  unwrap it based on how it got tunneled over; for example timer
      //  invocation or asynchronous callback, etc.)
      if (event.type === EV_ELOOP_EXECUTE) {
        if (event.data.threadId in self.pendingEvents &&
            event.data.eventId in self.pendingEvents[event.data.threadId]) {
          links = self.pendingEvents[event.data.threadId][event.data.eventId];
          parent_link = links.shift();
          if (links.length === 0)
            delete self.pendingEvents[event.data.threadId][event.data.eventId];
          // null links tell us that it was a boring event and we should forget
          //  this guy.
          if (parent_link === null) {
            console.log("skipping boring event", event.gseq);
            continue;
          }
        }
        else {
          // non-events are fine
          if (event.data.eventId === 0)
            continue;
          console.warn("encountered unknown event id!",
                       event.data.eventId, event);
        }

        // - killable!
        // Some events should just be pruned...
        // nsTimerEvents that do not fire, for example
        if (event.data.scriptName === "nsTimerEvent" &&
            event.children.length === 0) {
          // This can happen because of a generation mismatch or cancellation.
          // They effectively did not happen, and clutter up the causality
          //  graph.
          this.pruneCount++;
          continue;
        }

        // - unwrappable!
        // (The theory is that the event we are unwrapping is not bringing any
        //  information to the party that is not already contained inside its
        //  sole child.  Specifically, this holds true for native things like
        //  timers where all the outer event tells us is the C++ class type
        //  that we already know by virtue of having a specific probe for that
        //  type.)
        if (event.children.length === 1) {
          var origin_event = null;
          switch (event.children[0].type) {
            case EV_TIMER_FIRED:
              // change our concept of the parent link to the origin of the
              //  timer event.
              origin_event = event;
              event = event.children[0];
              if (event.data.timerId in self.pendingTimers) {
                var timer_info = self.pendingTimers[event.data.timerId];
                parent_link = timer_info[1];
                // clear only if single shot
                if (timer_info[0])
                  delete self.pendingTimers[event.data.timerId];
              }
              else {
                console.warn("encountered unknown timer id!", event);
                continue;
              }
              break;

            case EV_INPUT_READY:
            case EV_INPUT_PUMP:
              origin_event = event;
              event = event.children[0];
              break;
          }
          // apply any required data propagation
          if (origin_event) {
            event.thread_idx = origin_event.thread_idx;
          }
        }

        link = new ChainLink(event);
        parent_link.linkOutgoing(link);

        // unwrap JS crossings...
        if (event.children.length === 1 &&
            (event.children[0].type === EV_XPCJS_CROSS ||
             event.children[0].type === EV_JSEXEC_CROSS)) {
          semEvent = link.semEvent = event.children[0];
        }

        this._walk_events(event, link);
        continue;
      }
      // -- Socket Loop
      // Note that socket stuff only happens on the socket thread and cannot
      //  have any XPConnect stuff happening, which makes the actions that
      //  happen here directly uninteresting, but necessary to know about
      //  because this is where all the I/O stuff happens.
      else if (event.type === EV_SOCK_READY) {
        if (event.data.fd in this.pendingSockets) {
          // get our progenitor link
          parent_link = this.pendingSockets[event.data.fd];

          // create a new link for the current dude
          link = new ChainLink(event);
          parent_link.linkOutgoing(link);

          // put that link in the pending sockets map because sockets are
          //  inherently sequential
          this.pendingSockets[event.data.fd] = link;

          this._walk_events(event, link);
          continue;
        }
        else {
          console.warn("unknown socket ready fd", event.data.fd, event);
          // fall-through!
        }
      }
      // -- Program logic outside an event loop.
      // if this isn't an event loop thing, then the event belongs to the
      //  containing thread's causal chain which we may need to create...
      {
        // do not generate (synthetic) chains for:
        // - boring events
        // - events that will generate a zing
        if ((("boring" in event) && event.boring) ||
            (event.type === EV_GC || event.type === EV_LATENCY)) {
          this._walk_events(event, null);
          continue;
        }
        if (thread_roots[event.thread_idx] === null) {
          thread_link = thread_roots[event.thread_idx] = new ChainLink(null);
          thread_link.cluster = event.thread_idx;
          self.rootLinks.push(thread_link);
        }
        else {
          thread_link = thread_roots[event.thread_idx];
        }
        link = new ChainLink(event);
        thread_link.linkOutgoing(link);
        this._walk_events(event, link);
      }
    }
  },

  /**
   * Walk an event and all of its children in the context of a given causal
   *  link looking for the creation of new events.
   */
  _walk_events: function CausalChainer__walk_events(event, link,
                                                    thread_idx, context) {
    var new_context, kid_link = link, zing;
    if (thread_idx === undefined)
      thread_idx = event.thread_idx;
    else
      event.thread_idx = thread_idx;

    // -- scheduling
    if (event.type === EV_TIMER_INSTALLED) {
      // A given timer can only have one active thing at a time so the
      //  representation is much simpler than for the runnable scheduling
      //  in the next case.
      this.pendingTimers[event.data.timerId] = [event.data.singleShot, link];
    }
    else if (event.type === EV_ELOOP_SCHEDULE) {
      if (!(event.data.threadId in this.pendingEvents))
        this.pendingEvents[event.data.threadId] = {};
      if (!(event.data.eventId in this.pendingEvents[event.data.threadId]))
        this.pendingEvents[event.data.threadId][event.data.eventId] = [];
      this.pendingEvents[event.data.threadId][event.data.eventId].push(link);
    }
    // -- cancellation
    else if (event.type === EV_TIMER_CLEARED) {
      delete this.pendingTimers[event.data.timerId];
    }
    // -- socket delta action!
    else if (event.type === EV_SOCK_ATTACH) {
      this.pendingSockets[event.data.fd] = link;
    }
    else if (event.type === EV_SOCK_DETACH) {
      delete this.pendingSockets[event.data.fd];
    }
    // -- log message; can create new synthetic link!!
    else if (event.type === EV_LOG_MESSAGE) {
      if (this.logProcessor) {
        var nuevo_linko = this.logProcessor(event, link);
        // if we are given a new link it is what we use for the rest of these
        //  children
        if (nuevo_linko)
          kid_link = link = nuevo_linko;
      }
    }
    // -- exec context!
    else if (event.type === EV_JSEXEC_CROSS) {
      // only bother logging the context if it has children nested under it.
      if (event.children.length) {
        new_context = new ExecContext();
        if (context === undefined) {
          this.contexts.push(new_context);
        }
        else {
          context.children.push(new_context);
        }
        context = new_context;

        context.start = event;
        context.event = event;
        context.name = event.data.scriptName;
        context.thread_idx = thread_idx;

        // create a link for this dude at least for raw visualization purposes
        kid_link = new ChainLink(event);
        link.linkOutgoing(kid_link);
      }
    }
    // -- GC
    else if (event.type === EV_GC) {
      zing = new Zing();
      zing.kind = "gc";
      zing.event = event;
      this.zings.push(zing);
    }
    // -- latency!
    else if (event.type === EV_LATENCY) {
      zing = new Zing();
      zing.kind = "latency";
      zing.event = event;
      this.zings.push(zing);
    }

    var last_event = event;
    for (var i = 0; i < event.children.length; i++) {
      var recurse_retvals =
        this._walk_events(event.children[i], kid_link, thread_idx, context);
      last_event = recurse_retvals[0];
      kid_link = recurse_retvals[1];
    }

    if (new_context)
      new_context.end = last_event;

    return [last_event, kid_link];
  },
};
exports.CausalChainer = CausalChainer;

}); // end require.def
