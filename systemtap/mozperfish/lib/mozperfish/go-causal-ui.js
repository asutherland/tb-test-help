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
    "mozperfish/ui-repr",
  ],
  function(
    exports,
    mod_chainer,
    mod_logtesty,
    _timey,
    mod_ui_repr
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
    .fillStyle("white");
    //.event("mousedown", pv.Behavior.pan());
    //.event("mousewheel", pv.Behavior.zoom());
  
  var graph = vis.add(pv.Layout.Timey) // pv.Layout.Force
    .nodes(nodes)
    .links(links)
    .phases(chainer.phases)
    .contexts(chainer.contexts)
    .phaseLabelMargin(80)
    .contextIndent(20)
    .eventFromNode(function(n) { return n ? n.event : n; })
    //.time(function(d) { return d ? d.gseq : d; })
    .time(function(d) { return d ? d.time : d; })
    .group(function(d) { return d.event ? d.event.thread_idx : -1; })
    .kind(function(d) { return d.semEvent ? d.semEvent.type : -1; });
  
  var normalLinkColor = pv.color("rgba(0,0,0,.2)");
  var selectedLinkColor = pv.color("rgba(255,0,0,.5)");
  var primaryLinkColor = pv.color("rgba(0,0,255,0.5)");
  graph.link.strokeStyle(function(arr, l) {
                           if (l.targetNode.mark)
                             return selectedLinkColor;
                           else if (l.targetNode.primary)
                             return primaryLinkColor;
                           else
                             return normalLinkColor;
                         });
  
  var colors = pv.Colors.category20();

  var initColor = pv.color("hsl(30, 50%, 94%)");
  var runColor = pv.color("hsl(90, 50%, 94%)");
  var quitColor = pv.color("hsl(0, 50%, 94%)");
  var testAColor = pv.color("hsl(240, 50%, 94%)");
  var testBColor = pv.color("hsl(270, 50%, 94%)");
  var otherColor = pv.color("hsl(0, 0%, 94%)");
  var phaseBar = graph.phase.add(pv.Bar)
    .fillStyle(function(p) {
                 if (p.kind == "init") {
                   if (p.name == "load")
                     return initColor;
                   else
                     return runColor;
                 }
                 else if (p.kind == "test") {
                   if (this.index % 2)
                     return testAColor;
                   else
                     return testBColor;
                 }
                 else if (p.kind == "shutdown") {
                   return quitColor;
                 }
                 else {
                   return otherColor;
                 }
               })
    .event("click", function (p) {
             selectifyNode(null);
           });
  phaseBar.add(pv.Label)
    .top(function() { return phaseBar.top(); })
    .left(function() { return phaseBar.left(); })
    .textAlign("left")
    .textBaseline("top")
    .textStyle("black")
    .text(function(p) { return p.kind + ": " + p.name; });
  
  var zebraContextA = pv.color("rgba(128, 128, 128, 0.2)");
  var zebraContextB = pv.color("rgba(160, 160, 160, 0.2)");
  var contextBar = graph.context.add(pv.Bar)
    .fillStyle(function(c) {
                 if (this.index % 2)
                   return zebraContextA;
                 else
                   return zebraContextB;
               });
  contextBar.add(pv.Label)
    .top(function() { return contextBar.top(); })
    .left(function() { return contextBar.left(); })
    .textAlign("left")
    .textBaseline("top")
    .textStyle("black")
    .text(function(c) { return c.name; })
    // Only show the label if we have enough visible space before our first
    //  child.
    .visible(function (c) { return c.safe_dy > 6; });
  
  
  graph.link.add(pv.Line);

  var curSelected;
  function selectifyNode(d) {
    if (curSelected)
      curSelected.clearMark();
    if (d)
      d.markSelected();

    curSelected = d;
    vis.render();
  };
  
  var MARK_SELECTED = 1, MARK_ANCESTOR = 2, MARK_DESCENDENT = 3;
  var ancestorColor = pv.color("hsl(0, 100%, 75%)"),
      selectedColor = pv.color("hsl(0, 100%, 50%)"),
      descendentColor = pv.color("hsl(0, 100%, 38%)");
  graph.node.add(pv.Dot)
    .shape(function(d) {
             if (d.mark)
               return "square";
             return "circle";
           })
    .shapeSize(function(d) {
                 if (d.mark)
                   return 12;
                 return 6;
               })
    .fillStyle(function(d) { 
                 switch (d.mark) {
                   case MARK_ANCESTOR:
                     return ancestorColor;
                   case MARK_SELECTED:
                     return selectedColor;
                   case MARK_DESCENDENT:
                     return descendentColor;
                   default:
                     return colors(d.semEvent ? d.semEvent.type : 0);
                 }
               })
    .strokeStyle(function(d) { 
                 if (d.primary)
                   return primaryLinkColor;
                 switch (d.mark) {
                   case MARK_ANCESTOR:
                   case MARK_SELECTED:
                   case MARK_DESCENDENT:
                     return selectedColor;
                   default:
                     return this.fillStyle().darker();
                 }
               })
    .lineWidth(1)
    .title(function(d) { return d.event ? d.event.gseq : 0; })
    //.event("mousedown", pv.Behavior.drag())
    .event("mouseover", selectifyNode)
    .event("click", function(d) { console.log("clicked on", d); });
    //.event("drag", graph);


  vis.render();  
}

exports.chewAndShow = function(perfData) {
  console.log("perf data", perfData);
  
  var chainer = new mod_chainer.CausalChainer(perfData,
                                              mod_logtesty.chewXpcshellDumps);
  chainer.chain();
  console.log("chainer", chainer, "pruned", chainer.pruneCount, "boring events");
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
