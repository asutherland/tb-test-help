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
var EV_ELOOP_EXECUTE = 4096, EV_ELOOP_SCHEDULE = 4097;
var EV_INPUT_READY = 4128, EV_INPUT_PUMP = 4129;
var EV_XPCJS_CROSS = 4160, EV_JSEXEC_CROSS = 4161;
var EV_PROXY_CALL = 4192;

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
  this.outlinks = [];
}
ChainLink.prototype = {
};

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
  this.pendingTimers = {};
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
      if (thread_events.length && 
          thread_events[thread_events.length - 1].type == EV_ELOOP_SCHEDULE)
        thread_events[thread_events.length - 1].boring = true;

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
    
    // -- processing loop
    var event, semEvent, link, thread_link, parent_link, death = 0, links;
    while ((event = get_next_event())) {
      // save off the thread index; if we unbox we may lose access to the info
      //  because we only poke it back into top-level events.
      var thread_idx = event.thread_idx;
      
      // if this isn't an event loop thing, then the event belongs to the
      //  containing thread's causal chain which we may need to create...
      if (event.type !== EV_ELOOP_EXECUTE) {
        // do not generate chains for boring events...
        if (("boring" in event) && event.boring) {
          this._walk_events(event, null);
          continue;
        }
        if (thread_roots[event.thread_idx] === null) {
          thread_link = thread_roots[event.thread_idx] = new ChainLink(null);
          self.rootLinks.push(thread_link);
        }
        else {
          thread_link = thread_roots[event.thread_idx];
        }
        link = new ChainLink(event);
        thread_link.outlinks.push(link);
        this._walk_events(event, link);
      }
      // - event allocation
      // (we know this msut be an event loop execution, but we can potentially
      //  unwrap it based on how it got tunneled over; for example timer
      //  invocation or asynchronous callback, etc.)
      else {
        if (event.data.threadId in self.pendingEvents &&
            event.data.eventId in self.pendingEvents[event.data.threadId]) {
          links = self.pendingEvents[event.data.threadId][event.data.eventId];
          parent_link = links.shift();
          if (links.length === 0)
            delete self.pendingEvents[event.data.threadId][event.data.eventId];
          // null links tell us that it was a boring event and we should forget
          //  this guy.
          if (parent_link === null)
            continue;
        }
        else {
          // non-events are fine
          if (event.data.eventId === 0)
            continue;
          console.warn("encountered unknown event id!",
                       event.data.eventId, event);
          this._walk_events(event, link);
          continue;
        }
        
        // unwrappable!
        if (event.children.length === 1) {
          switch (event.children[0].type) {
            case EV_TIMER_FIRED:
              // change our concept of the parent link to the origin of the
              //  timer event.
              if (event.data.timerId in self.pendingTimers) {
                parent_link = self.pendingTimers[event.data.timerId];
                delete self.pendingTimers[event.data.timerId];
              }
              else {
                console.warn("encountered unknown timer id!", event);
                continue;
              }
              event = event.children[0];
              break;
            
            case EV_INPUT_READY:
            case EV_INPUT_PUMP:
              event = event.children[0];
              break;
          }
        }
        
        link = new ChainLink(event);
        parent_link.outlinks.push(link);
        
        // unwrap JS crossings...
        if (event.children.length === 1 &&
            (event.children[0].type === EV_XPCJS_CROSS ||
             event.children[0].type === EV_JSEXEC_CROSS)) {
          semEvent = link.semEvent = event.children[0];
        }

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
    var new_context;
    if (thread_idx === undefined)
      thread_idx = event.thread_idx;
    
    // -- scheduling
    if (event.type === EV_TIMER_INSTALLED) {
      this.pendingTimers[event.data.timerId] = link;
    }
    else if (event.type === EV_ELOOP_SCHEDULE) {
      /*
      console.log("event scheduled", event.data.eventId,
                  "on", event.data.threadId,
                  "by", event);
       */
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
    // -- log message
    else if (event.type === EV_LOG_MESSAGE) {
      if (this.logProcessor)
        this.logProcessor(event);
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
        
        context.start = event.gseq;
        context.event = event;
        context.name = event.data.scriptName;
        context.thread_idx = thread_idx;
      }
    }

    var last_gseq = event.gseq;
    for (var i = 0; i < event.children.length; i++) {
      last_gseq =
        this._walk_events(event.children[i], link, thread_idx, context);
    }
    
    if (new_context)
      new_context.end = last_gseq;
    
    return last_gseq;
  },
};
exports.CausalChainer = CausalChainer;

}); // end require.def
