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

require.def("mozperfish/go-causal-ui",
  [
    "exports",
    "mozperfish/causal-chainer",
    "mozperfish/logproc-testy",
    "mozperfish/pv-layout-timey",
    "wmsy/wmsy",
    "mozperfish/ui-scaffolding",
    "mozperfish/ui-repr",
    "mozperfish/ui-zings",
    "mozperfish/ui-misc",
    "mozperfish/ui-vis-chainlinks",
    "mozperfish/zing-blamer",
  ],
  function(
    exports,
    mod_chainer,
    mod_logtesty,
    _timey,
    wmsy,
    _ui_scaffolding,
    _ui_repr,
    _ui_zings,
    _ui_misc,
    _ui_vis_chainlinks,
    mod_zing_blamer
  ) {

var wy = new wmsy.WmsyDomain({id: "go-causal-ui", domain: "mozperfish",
                              clickToFocus: true});

wy.defineWidget({
  name: "top-level",
  focus: wy.focus.domain.vertical("tabs"),
  constraint: {
    type: "top-level",
  },
  provideContext: {zing_blamer: "zing_blamer"},
  structure: {
    vis: wy.widget({type: "vis-chainlinks"}, "chainer"),
    tabs: wy.widget({type: "tabbox"}, wy.SELF),
  }
});

exports.chewAndShow = function(perfData) {
  console.log("perf data", perfData);
  
  var chainer = new mod_chainer.CausalChainer(perfData,
                                              mod_logtesty.chewXpcshellDumps);
  chainer.chain();
  console.log("chainer", chainer, "pruned", chainer.pruneCount, "boring events");

  var zing_blamer = new mod_zing_blamer.ZingBlamer(chainer);
  zing_blamer.summarize();
  
  var rootObj = {
    chainer: chainer,
    zing_blamer: zing_blamer,
    tabIndex: 0,
    tabs: [
      {kind: "zings", name: "Zings!", zinger: zing_blamer},
      {kind: "about", name: "About"},
    ],
  };
  
  var binder = wy.wrapElement(document.getElementById("body"));
  binder.bind({type: "top-level", obj: rootObj});
};

exports.main = function(jsonBlobPath) {
  var req = new XMLHttpRequest();
  req.open("GET", jsonBlobPath, true);
  req.addEventListener("load", function() {
    if (req.status == 200)
      exports.chewAndShow(JSON.parse(req.responseText));
    else
      console.error("failure getting the data");
  }, false);
  req.send(null);
};

}); // end require.def
