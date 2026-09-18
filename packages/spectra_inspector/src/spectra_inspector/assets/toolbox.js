/* Clientside pieces of the plot toolboxes (components/toolbox.py). Dash
   serves this directory automatically and exposes the functions to
   ClientsideFunction("toolbox", <name>). */

window.dash_clientside = Object.assign({}, window.dash_clientside, {
  toolbox: {
    /* The spectrum's live ranges exist only in the browser (the figure prop
       never receives a zoom), so its zoom steps and reset are relayouts here.
       A zoom step scales the energy axis only. Returns the action taken, into
       a sink store. */
    spectrumAction: function (actionClicks, resetClicks, graphId) {
      const noUpdate = window.dash_clientside.no_update;
      const context = window.dash_clientside.callback_context;
      const fired = (context.triggered || []).filter((t) => t.value);
      if (fired.length !== 1) {
        return noUpdate;
      }
      const propId = fired[0].prop_id.replace(/\.n_clicks$/, "");
      const action = propId.startsWith("{")
        ? JSON.parse(propId).index
        : "reset";
      const graph = document.getElementById(graphId);
      const gd = graph && graph.querySelector(".js-plotly-plot");
      if (!gd || !gd._fullLayout) {
        return noUpdate;
      }
      if (action === "reset") {
        Plotly.relayout(gd, {
          "xaxis.autorange": true,
          "yaxis.autorange": true,
        });
        return action;
      }
      const factor = { zoomin: 0.5, zoomout: 2 }[action];
      if (!factor) {
        return noUpdate;
      }
      const [r0, r1] = gd._fullLayout.xaxis.range;
      const centre = (r0 + r1) / 2;
      Plotly.relayout(gd, {
        "xaxis.range": [
          centre + (r0 - centre) * factor,
          centre + (r1 - centre) * factor,
        ],
      });
      return action;
    },

    /* Open or close a folded toolbox and turn its chevron; the class names
       match CHEVRON_OPEN / CHEVRON_CLOSED in components/toolbox.py. */
    toggleCollapse: function (nClicks, isOpen) {
      const noUpdate = window.dash_clientside.no_update;
      if (!nClicks) {
        return [noUpdate, noUpdate];
      }
      const open = !isOpen;
      return [
        open,
        open ? "fa-solid fa-chevron-up me-1" : "fa-solid fa-chevron-down me-1",
      ];
    },
  },
});

/* The polygon tool (components/image_toolbox.py): clicks on an image panel
   place the corners of a shape and a double click removes the nearest one.
   Plotly's own click event is snapped to a pixel and reaches Dash as
   clickData, where two identical clicks in a row are deduplicated, so the
   panels are watched from here instead: one listener on the document, acting
   only while a panel is in polygon mode (dragging off and the axes fixed,
   what view_sync.tool_layout puts on the layout). Plotly re-dispatches every
   click that was not a drag as a single synthetic click event, so a double
   click arrives as two clicks: the first waits POLYGON_DBLCLICK_MS for a
   second one at the same spot before it counts as a single click. Both land
   in the polygon click store as {kind, x, y, n}, the counter making a repeat
   at the same spot still count as a change; pages/inspector.py answers them.
   The store id mirrors inspectorIDs.polygon_click_store. */
const POLYGON_CLICK_STORE = "polygon-click";
const POLYGON_DBLCLICK_MS = 350;
const POLYGON_DBLCLICK_PX = 6;
const polygonClicks = { timer: null, pending: null, n: 0 };

function polygonPanelPoint(event) {
  const target = event.target;
  const gd =
    target && target.closest
      ? target.closest("#image-container .js-plotly-plot")
      : null;
  if (!gd || !gd._fullLayout) {
    return null;
  }
  const fl = gd._fullLayout;
  if (fl.dragmode !== false || !fl.xaxis || !fl.xaxis.fixedrange) {
    return null;
  }
  const rect = gd.getBoundingClientRect();
  const px = event.clientX - rect.left - fl._size.l;
  const py = event.clientY - rect.top - fl._size.t;
  if (px < 0 || py < 0 || px > fl._size.w || py > fl._size.h) {
    return null;
  }
  return {
    x: fl.xaxis.p2d(px),
    y: fl.yaxis.p2d(py),
    clientX: event.clientX,
    clientY: event.clientY,
  };
}

function emitPolygonClick(kind, point) {
  polygonClicks.n += 1;
  window.dash_clientside.set_props(POLYGON_CLICK_STORE, {
    data: { kind: kind, x: point.x, y: point.y, n: polygonClicks.n },
  });
}

document.addEventListener(
  "click",
  (event) => {
    const point = polygonPanelPoint(event);
    if (point === null) {
      return;
    }
    const pending = polygonClicks.pending;
    if (pending !== null) {
      clearTimeout(polygonClicks.timer);
      polygonClicks.timer = null;
      polygonClicks.pending = null;
      const near =
        Math.abs(pending.clientX - point.clientX) <= POLYGON_DBLCLICK_PX &&
        Math.abs(pending.clientY - point.clientY) <= POLYGON_DBLCLICK_PX;
      if (near || event.detail > 1) {
        emitPolygonClick("dblclick", pending);
        return;
      }
      // two quick clicks in different places: both are corners
      emitPolygonClick("click", pending);
    }
    polygonClicks.pending = point;
    polygonClicks.timer = setTimeout(() => {
      polygonClicks.timer = null;
      polygonClicks.pending = null;
      emitPolygonClick("click", point);
    }, POLYGON_DBLCLICK_MS);
  },
  true,
);
