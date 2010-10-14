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
 * Contribute a pv.Layout.Timey layout thing to the protovis namespace.  Not
 *  that I actually expect this to involve into something anyone else wants
 *  to use, but why preclude it?  (Obviously the require.def wrapping would
 *  need to come off, of course...)
 * 
 * This is being written based off the idioms of the force-directed layout
 *  code.
 **/

require.def("mozperfish/pv-layout-timey", [], function() {

/**
 *
 */
pv.Layout.Timey = function() {
  pv.Layout.Network.call(this);
  var that = this;
  
  (this.phase = new pv.Mark()
      .data(function() { return that.phases(); })
      .left(function (n) { return n.x; })
      .top(function (n) { return n.y; })
      .width(function (n) { return n.dx; })
      .height(function (n) { return n.dy; })
      ).parent = this;
  
  (this.context = new pv.Mark()
      .data(function() { return that.flattened_contexts; })
      .left(function (n) { return n.x; })
      .top(function (n) { return n.y; })
      .width(function (n) { return n.dx; })
      .height(function (n) { return n.dy; })
      ).parent = this;
      
};

pv.Layout.Timey.prototype = pv.extend(pv.Layout.Network)
     .property("phases")
     .property("contexts")
     .property("phaseLabelMargin", Number)
     .property("contextIndent", Number);

pv.Layout.Timey.prototype.eventFromNode = function(v) {
  this._eventFromNode = v;
  return this;
};

pv.Layout.Timey.prototype.time = function(v) {
  this._time = v;
  return this;
};

pv.Layout.Timey.prototype.group = function(v) {
  this._group = v;
  return this;
};

pv.Layout.Timey.prototype.kind = function(v) {
  this._kind = v;
  return this;
};


pv.Layout.Timey.prototype.defaults = new pv.Layout.Timey()
    .extend(pv.Layout.Network.prototype.defaults)
    .property("phaseLabelMargin", 80)
    .property("contextIndent", 60);

pv.Layout.Timey.prototype.buildImplied = function(s) {
  // superclass returns true if we've already built ourselves.
  if (pv.Layout.Network.prototype.buildImplied.call(this, s))
    return;
  
  var nodes = s.nodes, links = s.links, phases = s.phases,
      contexts = s.contexts, contextIndent = s.contextIndent,
      eventFromNode = this._eventFromNode,
      timeAccessor = this._time, groupAccessor = this._group,
      kindAccessor = this._kind,
      l_margin = s.phaseLabelMargin,
      w = s.width, h = s.height, i;
  
  function nodeTimeAccessor(d) {
    return timeAccessor(eventFromNode(d));
  }
  
  var timeScale = pv.Scale.linear()
                      .domain(nodes, nodeTimeAccessor, nodeTimeAccessor)
                      .range(0, h);
  var groupScale = pv.Scale.ordinal()
                        .domain(nodes, groupAccessor)
                        .split(l_margin, w);

  console.log("timeScale", timeScale.domain(), timeScale.range(),
              "groupScale", groupScale.domain(), groupScale.range());
  
  var groupRange = groupScale.range();
  var groupSpan = groupRange[1] - groupRange[0];
  var groupRightOffset = groupSpan/2, groupLeftOffset = -groupSpan/2;

  var eventDisplace = pv.Scale.ordinal()
                          .domain(nodes, kindAccessor)
                          .split(groupRightOffset - 60, groupRightOffset);
  
  console.log("groupSpan", groupSpan,
       "eventDisplace", eventDisplace.domain(), eventDisplace.range());
  
  // nodes
  for (i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    var e = eventFromNode(n);
    n.x = groupScale(groupAccessor(n)) + eventDisplace(kindAccessor(n));
    n.y = timeScale(timeAccessor(e));
  }
  
  // phases
  for (i = 0; i < phases.length; i++) {
    var p = phases[i];
    p.x = 0;
    p.dx = w;
    p.y = timeScale(timeAccessor(p.start));
    if (p.end === null)
      p.dy = h - p.y;
    else
      p.dy = timeScale(timeAccessor(p.end)) - p.y;
  }
  
  // contexts
  var flattened_contexts = this.flattened_contexts = [];
  function recurseContext(c, l, r) {
    c.x = l;
    c.dx = r - l;
    c.y = timeScale(timeAccessor(c.start));
    c.dy = c.safe_dy = timeScale(timeAccessor(c.end)) - c.y;
    
    flattened_contexts.push(c);
    
    var nl = l + contextIndent;
    if (nl > r)
      return;
    
    // 'i' is safe in here if var'd, but hey...
    for (var j = 0; j < c.children.length; j++) {
      if (!j) {
        // use the first child to figure out how much vertical space our box
        //  has before its child box will show up...
        c.safe_dy = timeScale(timeAccessor(c.children[j].start)) - c.y;
      }
      
      recurseContext(c.children[j], nl, r);
    }
  }
  for (i = 0; i < contexts.length; i++) {
    var tlc = contexts[i];
    var groupBase = groupScale(groupAccessor(tlc));
    flattened_contexts.push(tlc);
    recurseContext(tlc,
                   groupBase + groupLeftOffset,
                   groupBase + groupRightOffset);
  }
  
};

}); // end require.def
