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
 * Static wmsy presentations of the core data representations; nothing
 *  analytical or interactive in here.
 **/

require.def("mozperfsh/ui-repr",
  [
    "exports",
    "wmsy/wmsy",
  ],
  function(
    exports,
    wmsy
  ) {

var wy = exports.wy =
  new wmsy.WmsyDomain({id: "ui-repr", domain: "mozperfish",
                       clickToFocus: true});

wy.defineWidget({
  name: "JSStackFrame",
  constraint: {
    type: "JSStackFrame",
  },
  structure: {
    scriptName: wy.bind("scriptName"),
    scriptLine: ["line ", wy.bind("scriptLine")],
    functionName: wy.bind("functionName"),
  },
  style: {
    // Taking colors from syntax-js-proton.css from narscribblus/jstut which is
    //  based on the proton vim theme:
    //  http://vimcolorschemetest.googlecode.com/svn/colors/proton.vim
    scriptName: [
      "display: inline-block;",
      "width: 13em;",
      "padding: 0 0.5em;",
      "color: #607080;",
    ],
    scriptLine: [
      "display: inline-block;",
      "width: 4em;",
      "padding: 0 0.5em;",
      "text-align: right;",
      "color: #508040;",
    ],
    functionName: [
      "display: inline-block;",
      "width: 16em;",
      "padding: 0 0.5em;",
      "color: #b08020;",
    ],
  },
});

wy.defineWidget({
  name: "JSStack",
  constraint: {
    type: "JSStack",
  },
  structure: {
    header: "JS Stack:",
    frames: wy.vertList({type: "JSStackFrame"}, wy.SELF),
  },
  style: {
    frames: [
      "margin-left: 1em;",
    ],
  }
});

wy.defineWidget({
  name: "JSStack",
  constraint: {
    type: "JSStack",
    obj: null,
  },
  structure: {
    message: "No JS stack available.",
  },
});


wy.defineWidget({
  name: "native-stack-frame",
  doc: "a native stack frame, does nothing but maybe someday dxr/mxr?",
  constraint: {
    type: "native-stack-frame",
  },
  structure: {
    location: wy.bind(wy.SELF),
  }
});

wy.defineWidget({
  name: "native-stack",
  constraint: {
    type: "native-stack",
  },
  structure: {
    header: "Native Stack:",
    frames: wy.vertList({type: "native-stack-frame"}, wy.SELF),
  },
  style: {
    frames: [
      "margin-left: 1em;",
      "color: gray;",
    ],
  },
});

wy.defineWidget({
  name: "native-stack",
  constraint: {
    type: "native-stack",
    obj: null,
  },
  structure: {
    message: "No native stack available.",
  }
});

var EV_ELOOP_EXECUTE = 4096, EV_ELOOP_SCHEDULE = 4097;

var eventNameMap = wy.defineLocalizedMap("event names", {
  5: "Timer Installed",
  6: "Timer Cleared",
  7: "Timer Fired",
  11: "Log Message",
  17: "Garbage Collection",
  4096: "Runnable Executed",
  4097: "Runnable Scheduled",
  4128: "Input Ready",
  4129: "Input Pump",
  4144: "Socket Transport Ready",
  4145: "Socket Transport Attached",
  4146: "Socket Transport Detached",
  4160: "XPConnect calling JS",
  4161: "Native calling JS",
  4192: "Proxied Call",
  8192: "Latency Notification",
}, "Unknown Event: #0");

wy.defineWidget({
  name: "event-tab",
  constraint: {
    type: "tab",
    obj: { kind: "event" },
  },
  structure: {
    event: wy.widget({type: "event"}, "event"),
  }
});

wy.defineWidget({
  name: "event-generic",
  doc: "generic event dump fallback",
  constraint: {
    type: "event",
    obj: { type: wy.WILD },
  },
  structure: {
    eventType: "",
  },
  impl: {
    postInit: function() {
      this.eventType_element.textContent = eventNameMap.lookup(this.obj.type);
    }
  },
});

wy.defineWidget({
  name: "event-eloop-execute",
  doc: "event loop execution of a native, just show the native info",
  constraint: {
    type: "event",
    obj: { type: EV_ELOOP_EXECUTE },
  },
  structure: {
    header: ["event loop: ", wy.bind(["data", "scriptName"])],
    kids: wy.vertList({type: "event"}, "children"),
  },
  style: {
    // this is the script name... perhaps we should switch to named?
    header1: [
      "color: #607080;",
    ],
    kids: [
      "margin-left: 1em;",
    ],
    "kids-item": [
      "border: 1px solid gray;",
      "margin-bottom: 0.5em;",
      "padding: 2px;",
    ],
  },
});

wy.defineWidget({
  name: "event-eloop-schedule",
  doc: "event loop scheduling; show the stacks",
  constraint: {
    type: "event",
    obj: { type: EV_ELOOP_SCHEDULE },
  },
  structure: {
    header: "Runnable Scheduled",
    jsStack: wy.widget({type: "JSStack"}, ["data", "jsstack"]),
    nativeStack: wy.widget({type: "native-stack"}, ["data", "stack"]),
  },
  style: {
    header: [
      "display: block;",
      "margin-bottom: 4px;",
    ],
    // this is the script name... perhaps we should switch to named?
    header1: [
      "color: #607080;",
    ],
    jsStack: "margin-bottom: 4px;",
  },
});


}); // end require.def
