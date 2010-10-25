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
 * The chain link timeline-ish visualization with kitchen sinks and all.
 **/

require.def("mozperfsh/ui-vis-chainlinks",
  [
    "exports",
    "wmsy/wmsy",
  ],
  function(
    exports,
    wmsy
  ) {

var wy = exports.wy =
  new wmsy.WmsyDomain({id: "ui-vis-chainlinks", domain: "mozperfish",
                       clickToFocus: true});

/**
 * A configuration menu which is bound to an object tree describing the set of
 *  configuration options.  The configuration values are exposed to us via
 *  context.  Changes to the configuration are requested via emitting
 *  updateConfig signals.
 */
wy.defineWidget({
  name: "config-menu-root",
  focus: wy.focus.domain.vertical("parameters"),
  constraint: {
    type: "config-menu",
  },
  structure: {
    parameters: wy.vertList({type: "config-menu-parameter"}, wy.SELF),
  },
  style: {
    root: [
      "background-color: #888888;",
      "border: 1px solid #666666;",
      "padding: 4px;",
    ]
  },
});

wy.defineWidget({
  name: "config-menu-parameter",
  focus: wy.focus.container.vertical("values"),
  constraint: {
    type: "config-menu-parameter",
  },
  provideContext: {
    parameterName: "name",
  },
  structure: {
    label: wy.bind("label"),
    values: wy.vertList({type: "config-menu-value"}, "values"),
  },
  style: {
    root: [
      "margin-bottom: 0.5em;",
    ],
    label: [
      "display: block;",
      "background-color: #aaaaaa;",
      "color: black;",
      "padding: 2px;",
    ],
    values: [
      "background-color: #444444;",
      "padding: 2px;",
    ],
    "values-item": [
      "margin-bottom: 2px;",
    ],
  },
});

wy.defineWidget({
  name: "config-menu-value",
  emit: ["updateConfig"],
  constraint: {
    type: "config-menu-value",
  },
  focus: wy.focus.item,
  structure: {
    label: wy.bind("label", {active: wy.computed("isActive")}),
  },
  impl: {
    isActive: function() {
      var context = this.__context;
      return context.config[context.parameterName] == this.obj.value;
    },
  },
  events: {
    root: {
      command: function() {
        this.emit_updateConfig(this.__context.parameterName, this.obj.value);
      },
    },
  },
  style: {
    root: {
      _: [
        "background-color: #666666;",
        "padding: 2px;",
        "cursor: pointer;",
      ],
      ":hover": [
        "background-color: #666688;",
      ],
      ":focused": [
        "outline: 1px dotted blue;",
      ],
    },
    label: {
      _: [
        "color: white;",
      ],
      '[active="true"]': [
        "color: blue;",
      ],
    }
  }
});


/**
 * Visualization that can be parameterized on:
 * - layout algorithm: time/grouped versus free-form force-directed
 * - time base: wall clock vs. global sequence
 * - major grouping: thread vs. causal family
 */
wy.defineWidget({
  name: "vis-chainlinks",
  constraint: {
    type: "vis-chainlinks",
  },
  emit: ["clickedEvent"],
  // expose our config to the config menu.
  provideContext: {
    config: wy.SELF,
  },
  popups: {
    configMenu: {
      constraint: {
        type: "config-menu",
      },
      clickAway: true,
      position: {
        leftBelow: "configButton"
      },
    },
  },
  structure: {
    kanvaz: {}, // so named to avoid confusion about whether it's a canvas. no!
    configButton: wy.button("..."),
  },
  receive: {
    updateConfig: function(name, newValue) {
      console.log("being told to change", name, "to", newValue);
      // bail if we already have the given state
      if (this.obj[name] === newValue)
        return;
      // update our state
      this.obj[name] = newValue;

      // a change in layout algorithm requires a complete rebuild.
      if (name === "layout") {
      }

      this._updateConfig(true);
      if (this.activePopup)
        this.activePopup.update();
    },
  },
  events: {
    configButton: {
      command: function() {
        // If the user clicked on us while the popup was active, don't
        //  re-trigger the popup; the user was probably trying to close us.
        if (this.popupClosedBy === this.configButton_element) {
          this.popupClosedBy = null;
          return;
        }

        // The menu is rendering our parameters and should be positioned
        //  relative to this, the visualization binding.
        var self = this;
        this.activePopup = this.popup_configMenu(this.parameters,
                                                 this,
                                                 function(positiveResult,
                                                          clickedOn) {
          self.activePopup = null;
          self.popupClosedBy = clickedOn;
        });
      }
    }
  },
  impl: {
    /**
     * Meta-data about the visualization's configurable aspects for exposure
     *  for manipulation via wmsy UI.  Since this is about the widget binding
     *  it goes on the widget binding.
     */
    parameters: [
      {
        name: "layout",
        label: "Layout Algorithm",
        values: [
          {
            label: "Vertical Time, Horizontal Grouping",
            value: "timey",
          },
          {
            label: "Force-Directed in 2d",
            value: "force",
          },
        ],
      },
      {
        name: "timebase",
        label: "Time Base",
        values: [
          {
            label: "Wall Clock",
            value: "wall",
          },
          {
            label: "Global Sequence",
            value: "gseq",
          },
        ],
      },
      {
        name: "majorgroup",
        label: "Group By",
        values: [
          {
            label: "Thread",
            value: "thread",
          },
          {
            label: "Causal Family",
            value: "family",
          },
        ],
      },
    ],
    preInit: function() {
      this.activePopup = null;
      this.popupClosedBy = null;
      this._rebuild();
    },
    _rebuild: function() {
      var chainer = this.__context.chainer;
      var self = this;

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
      var vis = this.vis = new pv.Panel()
        .width(WIDTH)
        .height(HEIGHT)
        .canvas(this.kanvaz_element)
        .margin(4)
        .fillStyle("white");
        //.event("mousedown", pv.Behavior.pan());
        //.event("mousewheel", pv.Behavior.zoom());

      var graph = this.graph = vis.add(pv.Layout.Timey) // pv.Layout.Force
        .nodes(nodes)
        .links(links)
        .phases(chainer.phases)
        .contexts(chainer.contexts)
        .zings(chainer.zings)
        .phaseLabelMargin(80)
        .contextIndent(20)
        .eventFromNode(function(n) { return n ? n.event : n; })
        .group(function(d) { return d ? d.thread_idx : -1; })
        .kind(function(d) { return d.semEvent ? d.semEvent.type : -1; });

      this._updateConfig(false);

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

      var gcColor = pv.color("rgba(192, 192, 255, 0.5)");
      var latencyColor = pv.color("rgba(255, 192, 192, 0.5)");
      var zingBar = graph.zing.add(pv.Bar)
        .fillStyle(function(z) {
                     if (z.kind == "gc")
                       return gcColor;
                     else
                       return latencyColor;
                   });

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
        .event("click", function(n) {
                 self.emit_clickedEvent(n.event);
                 console.log("clicked on", n);
               });
        //.event("drag", graph);


      vis.render();
    },
    _timeGseq: function(d) {
      return d ? d.gseq : d;
    },
    _durationGseq: function() {
      return 1;
    },
    _timeWall: function(d) {
      return d ? d.time : d;
    },
    _durationWall: function(e) {
      return e.duration;
    },
    _updateConfig: function(aReset) {
      var config = this.obj;
      switch (config.timebase) {
        case "gseq":
          this.graph.time(this._timeGseq);
          this.graph.duration(this._durationGseq);
          break;

        case "wall":
        default:
          this.graph.time(this._timeWall);
          this.graph.duration(this._durationWall);
          break;
      }

      if (aReset) {
        this.graph.reset();
        this.vis.render();
      }
    },
  },
  style: {
    root: [
      // make us a containing block for position: absolute children
      "position: relative;",
    ],
    configButton: [
      "position: absolute;",
      "right: 0px;",
      "top: 0px;",
    ],
  },
});

}); // end require.def
