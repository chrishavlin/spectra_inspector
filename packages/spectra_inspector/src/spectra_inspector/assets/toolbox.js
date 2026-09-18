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
   place the corners of a shape, a drag moves one, and a double click removes
   a corner or inserts one on a segment. Plotly's own click event is snapped
   to a pixel and reaches Dash as clickData, where two identical clicks in a
   row are deduplicated, so the panels are watched from here instead: one set
   of listeners on the document, acting only while a panel is in polygon mode
   (dragging off and the axes fixed, what view_sync.tool_layout puts on the
   layout).

   Plotly re-dispatches every mouseup that did not drag as a single synthetic
   click event, so a double click arrives as two clicks: the first waits
   POLYGON_DBLCLICK_MS for a second one at the same spot before it counts as a
   single click. A mousedown on a corner starts a drag: the corner follows the
   mouse on every panel through Plotly.react with new shapes only (no image
   redraws, nothing sent), and the release commits it. Every gesture lands in
   the polygon click store as {kind: "click"|"dblclick"|"move", x, y, index,
   n}, the counter making a repeat at the same spot still count as a change;
   pages/inspector.py answers them and re-patches the shapes on every panel.
   The store id mirrors inspectorIDs.polygon_click_store, the shape names
   those in utilities/selection.py. */
const POLYGON_CLICK_STORE = "polygon-click";
const POLYGON_SHAPE_NAME = "polygon";
const POLYGON_VERTEX_NAME = "polygon-vertex";
const POLYGON_DBLCLICK_MS = 350;
const POLYGON_DBLCLICK_PX = 6;
/* how close to a corner, on screen, a mousedown must be to take hold of it */
const POLYGON_VERTEX_PX = 8;
/* how far the mouse must move before a mousedown on a corner is a drag */
const POLYGON_DRAG_START_PX = 3;
const polygonClicks = { timer: null, pending: null, n: 0 };
const polygonDrag = { active: null };

/* the panel under an event target, when it is in polygon mode */
function polygonPanel(target) {
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
  return gd;
}

function polygonPanels() {
  return Array.from(
    document.querySelectorAll("#image-container .js-plotly-plot"),
  ).filter((gd) => gd._fullLayout && gd.layout);
}

/* screen position -> data coordinates on a panel (unclamped) */
function polygonDataPoint(gd, clientX, clientY) {
  const fl = gd._fullLayout;
  const rect = gd.getBoundingClientRect();
  return {
    x: fl.xaxis.p2d(clientX - rect.left - fl._size.l),
    y: fl.yaxis.p2d(clientY - rect.top - fl._size.t),
  };
}

/* data coordinates -> screen position on a panel */
function polygonScreenPoint(gd, x, y) {
  const fl = gd._fullLayout;
  const rect = gd.getBoundingClientRect();
  return {
    x: rect.left + fl._size.l + fl.xaxis.d2p(x),
    y: rect.top + fl._size.t + fl.yaxis.d2p(y),
  };
}

/* the point of a click inside a polygon-mode panel's plot area, or null */
function polygonPanelPoint(event) {
  const gd = polygonPanel(event.target);
  if (gd === null) {
    return null;
  }
  const fl = gd._fullLayout;
  const rect = gd.getBoundingClientRect();
  const px = event.clientX - rect.left - fl._size.l;
  const py = event.clientY - rect.top - fl._size.t;
  if (px < 0 || py < 0 || px > fl._size.w || py > fl._size.h) {
    return null;
  }
  const point = polygonDataPoint(gd, event.clientX, event.clientY);
  point.clientX = event.clientX;
  point.clientY = event.clientY;
  return point;
}

/* the corners as drawn: the centres of the vertex circles, in data units */
function polygonCorners(shapes) {
  return (shapes || [])
    .filter((s) => s.name === POLYGON_VERTEX_NAME)
    .map((s) => [(s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2]);
}

/* mirrors selection._path: an open line, closed from three points */
function polygonPathString(points) {
  const moves = points.map((p) => `${p[0]},${p[1]}`).join(" L ");
  return `M ${moves}${points.length >= 3 ? " Z" : ""}`;
}

/* a panel's shapes with corner `index` moved to (x, y) */
function shapesWithCornerMoved(shapes, index, x, y) {
  const points = polygonCorners(shapes);
  if (index < 0 || index >= points.length) {
    return shapes;
  }
  points[index] = [x, y];
  let seen = 0;
  return shapes.map((s) => {
    if (s.name === POLYGON_SHAPE_NAME) {
      return Object.assign({}, s, { path: polygonPathString(points) });
    }
    if (s.name === POLYGON_VERTEX_NAME) {
      if (seen++ !== index) {
        return s;
      }
      const r = (s.x1 - s.x0) / 2;
      return Object.assign({}, s, {
        x0: x - r,
        x1: x + r,
        y0: y - r,
        y1: y + r,
      });
    }
    return s;
  });
}

/* the corner nearest the mouse on a panel, with its screen distance */
function polygonNearestCorner(gd, clientX, clientY) {
  let best = null;
  polygonCorners(gd.layout.shapes).forEach((p, index) => {
    const at = polygonScreenPoint(gd, p[0], p[1]);
    const distance = Math.hypot(at.x - clientX, at.y - clientY);
    if (best === null || distance < best.distance) {
      best = { index: index, distance: distance };
    }
  });
  return best;
}

function emitPolygonGesture(kind, point, index) {
  polygonClicks.n += 1;
  const data = { kind: kind, x: point.x, y: point.y, n: polygonClicks.n };
  if (index !== undefined) {
    data.index = index;
  }
  window.dash_clientside.set_props(POLYGON_CLICK_STORE, { data: data });
}

function polygonDragCursor(gd, cursor) {
  const rect = gd.querySelector(".nsewdrag");
  if (rect) {
    rect.style.cursor = cursor;
  }
}

/* Redraw a panel with other shapes. Plotly.react rather than Plotly.relayout:
   relayout emits plotly_relayout, which Dash turns into relayoutData and the
   page's sync callback into a server round trip per frame; react keeps the
   image data by reference and only redraws the shape layer. */
function polygonSetShapes(gd, shapes) {
  Plotly.react(
    gd,
    gd.data,
    Object.assign({}, gd.layout, { shapes: shapes }),
    gd._context,
  );
}

function polygonRedrawDrag(drag, point) {
  polygonPanels().forEach((gd) => {
    polygonSetShapes(
      gd,
      shapesWithCornerMoved(gd.layout.shapes, drag.index, point.x, point.y),
    );
  });
}

function polygonRestoreDrag(drag) {
  drag.original.forEach(([gd, shapes]) => {
    polygonSetShapes(gd, shapes);
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
        emitPolygonGesture("dblclick", pending);
        return;
      }
      // two quick clicks in different places: both are corners
      emitPolygonGesture("click", pending);
    }
    polygonClicks.pending = point;
    polygonClicks.timer = setTimeout(() => {
      polygonClicks.timer = null;
      polygonClicks.pending = null;
      emitPolygonGesture("click", point);
    }, POLYGON_DBLCLICK_MS);
  },
  true,
);

document.addEventListener(
  "mousedown",
  (event) => {
    if (event.button !== 0) {
      return;
    }
    const gd = polygonPanel(event.target);
    if (gd === null) {
      return;
    }
    const hit = polygonNearestCorner(gd, event.clientX, event.clientY);
    if (hit === null || hit.distance > POLYGON_VERTEX_PX) {
      return;
    }
    polygonDrag.active = {
      gd: gd,
      index: hit.index,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      frame: null,
      point: null,
      original: polygonPanels().map((p) => [p, p.layout.shapes]),
    };
  },
  true,
);

document.addEventListener(
  "mousemove",
  (event) => {
    const drag = polygonDrag.active;
    if (drag === null) {
      // a grab cursor over a corner says it can be dragged
      const gd = polygonPanel(event.target);
      if (gd !== null) {
        const hit = polygonNearestCorner(gd, event.clientX, event.clientY);
        polygonDragCursor(
          gd,
          hit !== null && hit.distance <= POLYGON_VERTEX_PX ? "grab" : "",
        );
      }
      return;
    }
    if (
      !drag.moved &&
      Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) <
        POLYGON_DRAG_START_PX
    ) {
      return;
    }
    drag.moved = true;
    drag.point = polygonDataPoint(drag.gd, event.clientX, event.clientY);
    if (drag.frame === null) {
      drag.frame = requestAnimationFrame(() => {
        drag.frame = null;
        if (polygonDrag.active === drag && drag.point !== null) {
          polygonRedrawDrag(drag, drag.point);
        }
      });
    }
  },
  true,
);

document.addEventListener(
  "mouseup",
  (event) => {
    const drag = polygonDrag.active;
    if (drag === null) {
      return;
    }
    polygonDrag.active = null;
    if (drag.frame !== null) {
      cancelAnimationFrame(drag.frame);
      drag.frame = null;
    }
    if (!drag.moved) {
      // a plain press on a corner: plotly's synthetic click follows and the
      // click listener decides (a single click on a corner adds nothing)
      return;
    }
    const point = polygonDataPoint(drag.gd, event.clientX, event.clientY);
    polygonRedrawDrag(drag, point);
    emitPolygonGesture("move", point, drag.index);
  },
  true,
);

/* Escape abandons a drag and puts the corner back */
document.addEventListener("keydown", (event) => {
  const drag = polygonDrag.active;
  if (drag === null || event.key !== "Escape") {
    return;
  }
  polygonDrag.active = null;
  if (drag.frame !== null) {
    cancelAnimationFrame(drag.frame);
  }
  if (drag.moved) {
    polygonRestoreDrag(drag);
  }
});
