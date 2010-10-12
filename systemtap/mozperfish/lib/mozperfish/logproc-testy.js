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
 * Log processing helpers.
 **/

require.def("mozperfish/logproc-testy",
  [
    "exports",
    "mozperfish/causal-chainer",
  ],
  function(
    exports,
    mod_chainer
  ) {

var Phase = mod_chainer.Phase;

var S_FILES_LOADED =
  "TEST-INFO | (xpcshell/head.js) | test 1 pending";
var S_EVENT_LOOP_STARTING =
  "TEST-INFO | (xpcshell/head.js) | running event loop";
var S_QUITTING =
  "TEST-INFO | (xpcshell/head.js) | exiting test";

var RE_ASYNC_TEST_START = /Starting test: (.+)$/;
var RE_ASYNC_TEST_FINISH = /Finished test: (.+)$/;

/**
 * Process the output of xpcshell to its Dump function 
 */
exports.chewXpcshellDumps = function(event, link) {
  var s = event.data.message.trim(), phase, match;
  var new_link;
  if (s == S_FILES_LOADED) {
    phase = this.initPhase = new Phase();
    phase.start = 0;
    phase.end = event.gseq;
    phase.kind = "init";
    phase.name = "load";
  }
  else if (s == S_EVENT_LOOP_STARTING) {
    phase = new Phase();
    phase.start = this.initPhase.end;
    phase.end = event.gseq;
    phase.kind = "init";
    phase.name = "run";
  }
  else if (s == S_QUITTING) {
    phase = new Phase();
    phase.start = event.gseq;
    phase.end = null;
    phase.kind = "shutdown";
    phase.name = "quit";
  }
  // test starting constructs an explicit new causal node
  else if ((match = RE_ASYNC_TEST_START.exec(s))) {
    phase = this.pendingTestPhase = new Phase();
    phase.start = event.gseq;
    phase.end = phase.start; // dummy out for now
    phase.kind = "test";
    phase.name = match[1];
    
    new_link = new mod_chainer.ChainLink(event);
    new_link.synthetic = true;
  }
  // test termination constructs an explicit new causal node!
  else if ((match = RE_ASYNC_TEST_FINISH.exec(s))) {
    this.pendingTestPhase.end = event.gseq;
    this.pendingTestPhase = null;

    new_link = new mod_chainer.ChainLink(event);
    new_link.synthetic = true;
  }
  if (phase)
    this.phases.push(phase);
  if (new_link) {
    link.outlinks.push(new_link);
    new_link.inlinks.push(link);
    new_link.markPrimaryCausalChain();
  }
  return new_link;
};

}); // end require.def
