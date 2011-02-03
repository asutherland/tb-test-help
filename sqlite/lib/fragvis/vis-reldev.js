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
 * Portions created by the Initial Developer are Copyright (C) 2011
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
 * Visualize the relative page/disk delta between b-tree pages that should
 *  otherwise be sequentially ordered.
 */

define(
  [
    "wmsy/wmsy",
    "wmsy/opc/protovis",
    "exports"
  ],
  function(
    $wmsy,
    $pv,
    exports
  ) {

var wy = exports.wy =
  new wmsy.WmsyDomain({id: "vis-reldev", domain: "fragvis",
                       clickToFocus: true});

wy.defineWidget({
  name: "vis-reldev",
  doc: "Relative b-tree page seek deviation, bound to a named thing.",
  constraint: {
    type: "vis",
    kind: "reldev",
  },
  structure: {
    kanvaz: {},
  },
  impl: {
    postInitUpdate: function() {
      this._build();
    },
    _build: function() {
      var lowestPage = this.obj.lowestPage,
          highestPage = this.obj.highestPage,
          orderedPages = this.obj.orderedPages;
      var maxdelta = highestPage - lowestPage;

      var W = 600, H = Math.ceil(orderedPages / W) * W;

      var vis = this.vis = new $pv.Panel()
        .width(W)
        .height(H);

      var scale = $pv.linear()
        .domain(-maxDelta, -32, 0, 32, maxDelta)
        .range("#f00", "#ff0", "#fff", "#0ff", "#0f0");

      vis.add($pv.Image)
        .imageWidth(W)
        .imageHeight(H)
        .image(function(x, y) {
                 var i = y * W + x;
                 var delta = i ? (orderedPages[i] - orderedPages[i - 1]) : 0;
                 return scale(delta);
               });
    },
  },
});

}); // end define
