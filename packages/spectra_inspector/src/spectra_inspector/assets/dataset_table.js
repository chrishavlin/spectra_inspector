/* Browser side of the AG Grid tables (components/dataset_table.py and the
   working-directory dialog).

   The search box above a grid is its quick filter, applied here so that typing
   costs no round trip. The grid's other options are kept: the callback writes
   the whole dashGridOptions prop.

   Text columns sort with naturalCompare, which orders digit runs as numbers
   (C-4 before C-31); the python side's natural_key gives the unsorted grid
   the same order.

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
