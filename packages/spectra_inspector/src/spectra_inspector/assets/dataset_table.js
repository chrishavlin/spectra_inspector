/* Browser side of the AG Grid tables (components/dataset_table.py and the
   working-directory dialog).

   The search box above a grid is its quick filter, applied here so that typing
   costs no round trip. The grid's other options are kept: the callback writes
   the whole dashGridOptions prop.

   Enter on a focused row does what a double click does. The grid reports
   double clicks to Dash (cellDoubleClicked) but not key presses, so the key is
   turned into the double click the page already handles. */
window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.dataset_table = {
  quick_filter: function (text, options) {
    return { ...(options || {}), quickFilterText: text || "" };
  },
};

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.repeat) {
    return;
  }
  const cell = document.activeElement;
  if (!cell || !cell.classList.contains("ag-cell")) {
    return;
  }
  if (!cell.closest(".si-grid")) {
    return;
  }
  cell.dispatchEvent(
    new MouseEvent("dblclick", { bubbles: true, cancelable: true }),
  );
});
