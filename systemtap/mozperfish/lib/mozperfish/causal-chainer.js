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

/**
 * Models a linear run of events in a causal chain without splitting or merging.
 *  The piece tracks incoming and outgoing edges.
 */
function ChainPiece() {
  this.incoming = [];
  this.events = [];
  this.outgoing = [];
}
ChainPiece.prototype = {
};

/**
 * Instantiate a new causal chainer for the given perfish blob.
 * 
 * @args[
 *   @param[perfishBlob PerfishBlob]
 * ]
 */
function CausalChainer(perfishBlob) {
  this.chains = [];
}
CausalChainer.prototype = {
  /**
   * 
   */
  chain: function CausalChainer_chain() {
    
  },
};
exports.CausalChainer = CausalChainer;

}); // end require.def
