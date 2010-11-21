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
 *  chrome these days.  Most of this stuff will ideally be able to move into
 *  the wmsy widget library.
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
    },
    openTab: function(obj, showImmediately, relTabObj) {
      // Here's the sitch: view slices are inherently single-consumer
      //  entitities, but we have two (headers_slice, panels_slice) fronting a
      //  single Array (obj.tabs).  We could just mutate tabs and call update,
      //  but our rebuild logic has no optimized paths; it nukes everything and
      //  then rebuilds.
      // So we just tell both headers and panels about the change.

      // - figure out where to insert the tab
      var index;
      if (relTabObj === true)
        index = this._selectedIndex + 1;
      else if (relTabObj)
        index = this.obj.tabs.indexOf(relTabObj) + 1;
      else
        index = this.obj.tabs.length;

      // - perform the splice on the array
      var objs = [obj];
      this.obj.tabs.splice(index, 0, obj);
      // - tell the view slices what we have wrought
      this.headers_slice.splice(index, 0, objs);
      this.panels_slice.splice(index, 0, objs);

      if (this._selectedIndex === index)
        this._selectedIndex++;

      if (showImmediately)
        this._switchTab(index);
    },
    closeTab: function(obj) {
      this._closeTab(this.obj.tabs.indexOf(obj));
    },
  },
  impl: {
    // we want to happen after the initial update pass so the child tabs exist.
    postInitUpdate: function() {
      this._selectedIndex = null;
      // mark all the tabs except the tab index one as non-focusable.
      var panels = this.panels_element.children;
      for (var i = 0; i < panels.length; i++) {
        panels[i].binding.__focusEnable(false);
      }
      // and switch to that one...
      this._switchTab(this.obj.tabIndex);
    },
    _switchTab: function(index) {
      if (this._selectedIndex == index)
        return;
      var panelNode;
      if (this._selectedIndex != null) {
        this.headers_element.children[this._selectedIndex]
          .removeAttribute("selected");
        panelNode = this.panels_element.children[this._selectedIndex];
        panelNode.removeAttribute("selected");
        panelNode.binding.__focusEnable(false);
      }
      var headerNode = this.headers_element.children[index];
      headerNode.setAttribute("selected", "true");
      // for automatically selected tabs this is needed, idempotent for others
      headerNode.binding.focus();

      panelNode = this.panels_element.children[index];
      panelNode.setAttribute("selected", "true");
      panelNode.binding.__focusEnable(true);

      this._selectedIndex = index;
    },
    _closeTab: function(index) {
      this.obj.tabs.splice(index, 1);
      // - tell the view slices what we have wrought
      this.headers_slice.splice(index, 1);
      this.panels_slice.splice(index, 1);

      // If we deleted the selected tab, switch to...
      if (index === this._selectedIndex) {
        this._selectedIndex = null;
        // the one to the left of it
        if (index > 0)
          this._switchTab(index - 1);
        // the one replacing it
        else if (index < this.obj.tabs.length)
          this._switchTab(index);
      }
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
        "padding: 2px;",
      ],
      '[selected="true"]': [
        "display: block;",
      ],
    },
  },
});

wy.defineWidget({
  name: "tab-header",
  focus: wy.focus.item,
  constraint: {
    type: "tab-header",
    obj: {kind: wy.WILD},
  },
  emit: ["switchTab", "closeTab"],
  events: {
    root: {
      command: function() {
        this.emit_switchTab(this.obj);
      },
    },
    close: {
      click: function() {
        this.emit_closeTab(this.obj);
      }
    }
  },
  structure: {
    label: wy.bind("name"),
    close: "X",
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
    },
    // really really really need an icon
    close: {
      _: [
        "margin-left: 0.6em;",
        "color: gray;",
      ],
      ":hover": [
        "color: red;",
        "outline: 1px solid red;",
      ],
    }
  }
});

}); // end require.def
