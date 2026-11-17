/* Browser side of the AG Grid tables (components/dataset_table.py and the
   working-directory dialog).

   The search box above a grid is its quick filter, applied here so that typing
   costs no round trip. The grid's other options are kept: the callback writes
   the whole dashGridOptions prop.

   Text columns sort with naturalCompare, which orders digit runs as numbers
   (C-4 before C-31); the python side's natural_key gives the unsorted grid
   the same order.

   A click on the sample map that hits no sample clears the map's filter and
   the active dataset. Plotly reports no click there, so the press and release
   are watched here (in the capture phase: plotly covers the page while a box
   is dragged) and a still one with nothing hovered presses the "Clear" button,
   which works while hidden.

   Enter on a focused row of the working-directory dialog does what a double
   click does. The grid reports double clicks to Dash (cellDoubleClicked) but
   not key presses, so the key is turned into the double click the dialog
   already handles. */
window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.dataset_table = {
  quick_filter: function (text, options) {
    return { ...(options || {}), quickFilterText: text || "" };
  },
  clear: function () {
    return "";
  },
};

window.dashAgGridFunctions = window.dashAgGridFunctions || {};

const naturalCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

window.dashAgGridFunctions.naturalCompare = function (valueA, valueB) {
  return naturalCollator.compare(valueA ?? "", valueB ?? "");
};

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.repeat) {
    return;
  }
  const cell = document.activeElement;
  if (!cell || !cell.classList.contains("ag-cell")) {
    return;
  }
  if (!cell.closest(".si-directory-grid")) {
    return;
  }
  cell.dispatchEvent(
    new MouseEvent("dblclick", { bubbles: true, cancelable: true }),
  );
});

let mapPress = null;

document.addEventListener(
  "mousedown",
  (event) => {
    mapPress = null;
    if (event.button !== 0 || !(event.target instanceof Element)) {
      return;
    }
    const map = event.target.closest(".si-sample-map");
    if (!map || event.target.closest(".modebar, a")) {
      return;
    }
    mapPress = { map: map, x: event.clientX, y: event.clientY };
  },
  true,
);

document.addEventListener(
  "mouseup",
  (event) => {
    const press = mapPress;
    mapPress = null;
    if (!press) {
      return;
    }
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > 3) {
      return;
    }
    const plot = press.map.querySelector(".js-plotly-plot");
    if (!plot || (plot._hoverdata && plot._hoverdata.length)) {
      return;
    }
    const clear = document.querySelector(".si-map-clear");
    if (clear) {
      clear.click();
    }
  },
  true,
);
