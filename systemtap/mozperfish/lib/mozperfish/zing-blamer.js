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
 * Categorizer the list of zings from a CausalChainer.
 **/

require.def("mozperfish/zing-blamer",
  [
    "exports",
  ],
  function(
    exports
  ) {

function ZingBlamer(chainer) {
  this.chainer = chainer;
  this.endOfTime = chainer.perfishBlob.lastEventEndsAtTime;
}
ZingBlamer.prototype = {
  summarize: function() {
    var zings = this.chainer.zings, tally;
    var talliesByKind = {}, latencyTallies = {};
    var overviewItems = [], latencyItems = [];

    for (var i = 0; i < zings.length; i++) {
      var z = zings[i], e = z.event;
      if (z.kind in talliesByKind) {
        tally = talliesByKind[z.kind];
      }
      else {
        tally = talliesByKind[z.kind] = {
          kind: z.kind, count: 0, duration: 0, sub: []
        };
        overviewItems.push(tally);
      }

      tally.count++;
      tally.duration += e.duration;

      if (z.kind == "latency") {
        var latencyReason = e.data.reason, latally;
        if (latencyReason in latencyTallies) {
          latally = latencyTallies[latencyReason];
        }
        else {
          latally = latencyTallies[latencyReason] = {
            reason: latencyReason, count: 0, duration: 0,
            stackalyzer: new Stackalyzer()
          };
          latencyItems.push(latally);
        }
        latally.count++;
        latally.duration += e.duration;

        if (e.data.jsstack) {
          latally.stackalyzer.chewStack(e.data.jsstack, e.duration);
        }
      }
    }

    function countSort(a, b) {
      return b.count - a.count;
    }
    function durationSort(a, b) {
      return b.duration - a.duration;
    }

    talliesByKind.latency.sub = latencyItems;
    latencyItems.sort(durationSort);

    overviewItems.sort(durationSort);
    this.overviewItems = overviewItems;

    /*
    console.log("==== Zing Overview:");
    for (var kind in talliesByKind) {
      tally = talliesByKind[kind];
      console.log(kind,
                  "count:", tally.count,
                  "duration:", tally.duration / 1000, "secs",
                  "(" + tally.duration * 100 / this.endOfTime + "% of runtime)");
    }

    console.log("==== Latency Summary:");
    for (var reason in latencyTallies) {
      tally = latencyTallies[reason];
      console.log(reason,
                  "count:", tally.count,
                  "duration:", tally.duration / 1000, "secs",
                  "(" + tally.duration * 100 / this.endOfTime + "% of runtime)");

      for (var ss in tally.jerkSites) {
        console.log("  ", tally.jerkSites[ss], ":", ss);
      }
    }
    */
  },
};
exports.ZingBlamer = ZingBlamer;

function hashFrame(frame) {
  return frame.scriptName + "-" + frame.scriptLine + "-" + frame.functionName;
}

function sameFrame(a, b) {
  return (a.scriptName === b.scriptName) &&
         (a.scriptLine === b.scriptLine) &&
         (a.functionName == b.functionName);
}

/**
 * Compare two stacks returning the number of matching frames.
 */
function compareStacks(a, b) {
  var i = 0, la = a.length, lb = b.length;
  while (i < la && i < lb) {
    if (!sameFrame(a[i], b[i]))
      return i;
    i++;
  }
  return i;
}

function CommonStack(stack, cost) {
  this.stack = stack;
  this.cost = cost;
  this.count = 1;
  // when we start out we have no callers; we only get callers when we fragment
  //  the stack.
  this.callers = null;
}
CommonStack.prototype = {
  fragmentAt: function(similarity, otherStack, otherCost) {
    var loppedThisStack = this.stack.slice(similarity);
    var loppedOtherStack = otherStack.slice(similarity);

    this.stack = this.stack.slice(0, similarity);

    var origCallers = this.callers;
    this.callers = new Stackalyzer();
    // if we already had a set of callers, cram it in
    if (origCallers) {
      var callerCommon = new CommonStack(loppedThisStack, this.cost);
      callerCommon.count = this.count;
      callerCommon.callers = origCallers;
      this.callers.cramExistingCommonStack(callerCommon);
    }
    else {
      this.callers.chewStack(loppedThisStack, this.cost, this.count);
    }
    this.callers.chewStack(loppedOtherStack, otherCost);
  }
};

/**
 * Incremental stack frame analyzer with the goal of distilling interesting call
 *  sites out of the stack frames we receive.
 *
 * Things a human might notice/do:
 * @itemize[
 *   @item{
 *     Ignore irrelevant root frames that are always there like app event loop
 *     stuff.  By default they should be hidden.
 *   }
 *   @item{
 *     Elide library abstraction gunk, noting that this is not really a problem
 *     for our pure JS callstacks.  Basically, we don't need to see fsync,
 *     the NSPR wrapper for fsync, the C++ wrapper class's NSPR wrapper, and so
 *     on in the backtrace.  We would either need heuristics/data on what
 *     is a library or what is actual interesting user code.
 *   }
 *   @item{
 *     Segregate (varying) callers from the 'blamey' call chain/tree.
 *   }
 * ]
 *
 * We currently use a simplified implementation because we only get JS
 *  callstacks so most of the boring gunk is already gone.  (Perhaps a little
 *  too much, actually...)  We just build a 'common stack' rooted at each of
 *  the root frames.  Whenever we see a new stack that deviates from the common
 *  stack implied by the root frame, we lop the rest of the common stack into a
 *  map of callers.  For simplicity, we just recursively use Stackalyzer to
 *  work that bit.
 *
 * All frames are just keyed by concatenating the string reps of the
 *  file/line/script with dashes in between using hashFrame.
 */
function Stackalyzer() {
  this.rootFrames = {};
  this.displayList = null;
}
Stackalyzer.prototype = {
  /**
   * @args[
   *   @param[stack @listof[@dict[
   *     @param[scriptName String]
   *     @param[scriptLine Number]
   *     @param[functionName]
   *   ]]]
   *   @param[count #:optional Number]
   * ]
   */
  chewStack: function(stack, cost, count) {
    if (!count)
      count = 1;
    var rootHash = hashFrame(stack[0]);
    if (rootHash in this.rootFrames) {
      var common = this.rootFrames[rootHash];
      var similarity = compareStacks(stack, common.stack);
      // - Split if they're not totally the same
      // (This will attribute count=1/cost=cost to the new child but not to the
      //  base, we do that below.)
      if (similarity < common.stack.length)
        common.fragmentAt(similarity, stack, cost);
      // Add count and cost after fragmenting so that the new stack's values
      //  don't get attributed to the lopped off bit.
      common.count += count;
      common.cost += cost;
    }
    else {
      this.rootFrames[rootHash] = new CommonStack(stack, cost);
    }
  },
  /**
   * Cram an existing common stack in assuming that all invariants are already
   *  golden and we are empty.  Used by CommonStack when fragmenting.
   */
  cramExistingCommonStack: function(common) {
    var rootHash = hashFrame(common.stack[0]);
    this.rootFrames[rootHash] = common;
  },

  /**
   * Flatten the rootFrames into a list sorted by cost.  This is not recursive
   *  because the assumption is that the display binding will itself be
   *  recursive and invoke this for sub-widgets as needed.
   */
  normalizeForDisplay: function() {
    var dlist = this.displayList = [];
    for (var key in this.rootFrames) {
      var common = this.rootFrames[key];
      dlist.push(common);
    }

    dlist.sort(function(a, b) {
                 return b.cost - a.cost;
               });
  },
};

}); // end require.def
