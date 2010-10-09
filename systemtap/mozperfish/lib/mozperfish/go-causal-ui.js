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
    "mozperfish/pv-layout-timey",
  ],
  function(
    exports,
    mod_chainer,
    _timey
  ) {

function visChainLinks(chainer) {
  var nodes = [];
  var links = [];
  
  // depth-first traversal
  function walkLink(link) {
    if ("index" in link)
      return;
    link.index = nodes.length;
    nodes.push(link);
    
    for (var i = 0; i < link.outlinks.length; i++) {
      var other = link.outlinks[i];
      walkLink(other);
      links.push({
        source: link.index,
        target: other.index,
      });
    }
  }
  for (var i = 0; i < chainer.rootLinks.length; i++) {
    walkLink(chainer.rootLinks[i]);
  }
  
  var WIDTH = 1024, HEIGHT = 1024;
  var vis = new pv.Panel()
    .width(WIDTH)
    .height(HEIGHT)
    .margin(4)
    .fillStyle("white")
    .event("mousedown", pv.Behavior.pan())
    .event("mousewheel", pv.Behavior.zoom());
  
  var graph = vis.add(pv.Layout.Timey) // pv.Layout.Force
    .nodes(nodes)
    .links(links)
    .time(function(d) { return d.event ? d.event.gseq : 0; })
    .group(function(d) { return d.event ? d.event.thread_idx : -1; });
  
  var colors = pv.Colors.category20();
  
  graph.link.add(pv.Line);

  graph.node.add(pv.Dot)
    .shape("circle")
    .shapeSize(6)
    .fillStyle(function(d) { return colors(d.semEvent ? d.semEvent.type : 0); })
    .strokeStyle(function() { return this.fillStyle().darker(); })
    .lineWidth(1)
    .title(function(d) { return d.event ? d.event.gseq : 0; })
    .event("mousedown", pv.Behavior.drag())
    .event("click", function(d) { console.log("clicked on", d); });
    //.event("drag", graph);

  vis.render();  
}

exports.chewAndShow = function(perfData) {
  console.log("perf data", perfData);
  
  var chainer = new mod_chainer.CausalChainer(perfData);
  chainer.chain();
  console.log("chainer", chainer);
  visChainLinks(chainer);
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
