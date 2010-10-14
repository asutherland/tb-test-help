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
            reason: latencyReason, count: 0, duration: 0, jerkSites: {}};
          latencyItems.push(latally);
        }
        latally.count++;
        latally.duration += e.duration;
        
        if (e.data.jsstack) {
          var stackString = JSON.stringify({z: e.data.jsstack});
          if (stackString in latally.jerkSites)
            latally.jerkSites[stackString]++;
          else
            latally.jerkSites[stackString] = 1;
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

}); // end require.def
