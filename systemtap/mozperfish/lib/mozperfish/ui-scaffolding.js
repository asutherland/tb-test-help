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
 * UI chrome bits, but we can't call it chrome because everything is called
 *  chrome these days.
 **/

require.def("mozperfsh/ui-scaffolding",
  [
    "exports",
    "wmsy/wmsy",
  ],
  function(
    exports,
    wmsy
  ) {

var wy = exports.wy =
  new wmsy.WmsyDomain({id: "ui-scaffolding", domain: "mozperfish",
                       clickToFocus: true});

wy.defineWidget({
  name: "tabbox",
  focus: wy.focus.container.vertical("headers", "panels"),
  constraint: {
    type: "tabbox",
  },
  structure: {
    box: {
      headers: wy.horizList({type: "tab-header"}, "tabs"),
      panels: wy.widgetList({type: "tab"}, "tabs"),
    }
  },
  receive: {
    switchTab: function(obj) {
      this._switchTab(this.obj.tabs.indexOf(obj));
    }
  },
  impl: {
    postInit: function() {
      this._selectedIndex = null;
      this._switchTab(this.obj.tabIndex);
    },
    _switchTab: function(index) {
      if (this._selectedIndex == index)
        return;
      if (this._selectedIndex != null) {
        this.headers_element.children[this._selectedIndex]
          .removeAttribute("selected");
        this.panels_element.children[this._selectedIndex]
          .removeAttribute("selected");
      }
      this.headers_element.children[index]
        .setAttribute("selected", "true");
      this.panels_element.children[index]
        .setAttribute("selected", "true");
      // ugh, webkit kludge.  I hate you webkit.
      this._selectedIndex = index;
    },
  },
  style: {
    headers: [
      "width: 100%;",
    ],
    panels: [
      "border: 1px solid blue;",
    ],
    'panels-item': {
      _: [
        "display: none;",
      ],
      '[selected="true"]': [
        "display: block;",
      ],
    }
  },
});

wy.defineWidget({
  name: "tab-header",
  focus: wy.focus.item,
  constraint: {
    type: "tab-header",
    obj: {kind: wy.WILD},
  },
  emit: ["switchTab"],
  events: {
    root: {
      command: function() {
        this.emit_switchTab(this.obj);
      },
    }
  },
  structure: {
    label: wy.bind("name"),
  },
  style: {
    root: {
      _: [
        "display: inline-block;",
        "border: 1px solid blue;",
        "border-bottom: 0px;",
        "padding: 0 8px;",
        "margin-right: 2px;",
        "cursor: pointer;",
      ],
      '[selected="true"]': [
        "margin-bottom: -1px;",
        "border-bottom: 1px solid white;",
      ],
      ':focused': [
        "background-color: #eeeeff;",
        "outline: 1px blue dotted;",
      ],
    }
  }
});

}); // end require.def
