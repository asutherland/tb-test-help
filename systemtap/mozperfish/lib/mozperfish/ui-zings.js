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
 * Zing blamer UI exposure.
 **/

require.def("mozperfsh/ui-zings",
  [
    "exports",
    "wmsy/wmsy",
  ],
  function(
    exports,
    wmsy
  ) {

var wy = exports.wy =
  new wmsy.WmsyDomain({id: "ui-zings", domain: "mozperfish",
                       clickToFocus: true});

wy.defineWidget({
  name: "zing-tab",
  focus: wy.focus.container.vertical("overviews"),
  constraint: {
    type: "tab",
    obj: {kind: "zings"},
  },
  structure: {
    overviews: wy.vertList({type: "zing-overview"},
                           ["zinger", "overviewItems"]),
  },
  style: {
    root: [
      "margin: 1px;",
    ],
  },
});

var cssGoodness = {
  '[goodness="good"]': "",
  '[goodness="warn"]': "color: goldenrod;",
  '[goodness="bad"]': "color: red;",
};

wy.defineWidget({
  name: "zing-overview",
  focus: wy.focus.nestedItem.vertical("kids"),
  constraint: {
    type: "zing-overview",
  },
  structure: {
    row: {
      what: wy.bind("kind"),
      count: [wy.bind("count", "#", {goodness: wy.computed("countgood")}),
              " times"],
      duration: [wy.bind("duration", "#.##",
                         {goodness: wy.computed("durationgood")}),
                 " ms"],
      percentage: [wy.computed("percentage", "#.##"), "% of runtime"],
    },
    kids: wy.vertList({type: "zing-latency"}, "sub"),
  },
  impl: {
    percentage: function() {
      return this.obj.duration * 100 /
               this.__context.zing_blamer.endOfTime;
    },
    countgood: function() {
      var count = this.obj.count;
      if (count > 1000)
        return "bad";
      if (count > 100)
        return "warn";
      return "good";
    },
    durationgood: function() {
      var duration = this.obj.duration;
      if (duration > 5000)
        return "bad";
      if (duration > 1000)
        return "warn";
      return "good";
    },
  },
  style: {
    root: {
      ":focused": {
        "row": [
          "background-color: #eeeeff;",
          "outline: 1px blue dotted;",
        ],
      }
    },
    kids: [
      "margin-left: 1em;",
      "border-top: 1px solid #eeeeee;",
      "border-bottom: 1px solid #eeeeee;",
    ],
    row: {
      _: [
        "display: block; width: 100%;",
      ],
      ":hover": [
        "background-color: #eeeeee;",
      ],
    },
    what: "display: inline-block; width: 15em; padding: 0px 0.5em;",
    count: [
      "display: inline-block; width: 6em; padding: 0px 0.5em;",
      "text-align: right;",
    ],
    count0: cssGoodness,
    duration: [
      "display: inline-block; width: 7em; padding: 0px 0.5em;",
      "text-align: right;",
    ],
    duration0: cssGoodness,
    percentage: [
      "display: inline-block; width: 10em; padding: 0px 0.5em;",
      "text-align: right;"
    ],
  }
});

wy.defineWidget({
  name: "zing-latency",
  focus: wy.focus.item,
  constraint: {
    type: "zing-latency",
  },
  emit: ["openTab"],
  structure: {
    reason: wy.bind("reason"),
    count: [wy.bind("count", "#", {goodness: wy.computed("countgood")}),
            " times"],
    duration: [wy.bind("duration", "#.##",
                       {goodness: wy.computed("durationgood")}),
               " ms"],
    percentage: [wy.computed("percentage", "#.##"), "% of runtime"],
  },
  impl: {
    percentage: function() {
      return this.obj.duration * 100 /
               this.__context.zing_blamer.endOfTime;
    },
    countgood: function() {
      var count = this.obj.count;
      if (count > 1000)
        return "bad";
      if (count > 100)
        return "warn";
      return "good";
    },
    durationgood: function() {
      var duration = this.obj.duration;
      if (duration > 5000)
        return "bad";
      if (duration > 1000)
        return "warn";
      return "good";
    },
  },
  events: {
    root: {
      command: function() {
        this.emit_openTab({
          name: this.obj.reason,
          kind: "stack-breakout",
          stackalyzer: this.obj.stackalyzer,
        }, true, true);
      }
    },
  },
  style: {
    root: {
      _: [
        "display: block; width: 100%;",
      ],
      ":hover": [
        "background-color: #eeeeee;",
      ],
      ":focused": [
        "background-color: #eeeeff;",
        "outline: 1px blue dotted;",
      ],
    },
    reason: "display: inline-block; width: 14em; padding: 0px 0.5em;",
    count: [
      "display: inline-block; width: 6em; padding: 0px 0.5em;",
      "text-align: right;",
    ],
    count0: cssGoodness,
    duration: [
      "display: inline-block; width: 7em; padding: 0px 0.5em;",
      "text-align: right;",
    ],
    duration0: cssGoodness,
    percentage: [
      "display: inline-block; width: 10em; padding: 0px 0.5em;",
      "text-align: right;"
    ],
  }
});

wy.defineWidget({
  name: "zing-stack-breakout-tab",
  constraint: {
    type: "tab",
    obj: {kind: "stack-breakout"},
  },
  focus: wy.focus.container.vertical("stackalyzer"),
  structure: {
    label: "Callers:",
    stackalyzer: wy.widget({type: "stackalyzer"}, "stackalyzer"),
  },
  style: {
    root: [
      "margin: 4px;",
    ],
  },
});

wy.defineWidget({
  name: "stackalyzer",
  constraint: {
    type: "stackalyzer",
  },
  focus: wy.focus.container.vertical("commonStacks"),
  structure: {
    commonStacks: wy.vertList({type: "common-stack"}, "displayList")
  },
  impl: {
    preInit: function() {
      this.obj.normalizeForDisplay();
    },
  },
  style: {
    "commonStacks-item": {
      _: [
        "border: 1px solid gray;",
        "border-radius: 3px;",
        "padding: 4px;",
        "margin-bottom: 2px;",
      ],
      ":focused": [
        //"border: 1px solid blue;",
        "outline: 1px dotted blue;",
        "background-color: #eeeeff;",
      ]
    }
  },
});

wy.defineWidget({
  name: "common-stack",
  doc: "stack display with cost/count info associated with stack",
  constraint: {
    type: "common-stack",
  },
  focus: wy.focus.item,
  structure: {
    stack: wy.vertList({type: "JSStackFrame"}, "stack"),
    cost: {
      duration: [wy.bind("cost", "#.##"), " ms"],
      count: [wy.bind("count", "#"), " times"],
    }
  },
  style: {
    root: [
    ],
    stack: [
      "display: inline-block;",
    ],
    cost: [
      "float: right;",
      "text-align: right;",
    ],
    duration: [
    ],
  },
});


}); // end require.def
