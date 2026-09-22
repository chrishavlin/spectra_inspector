/* The Apply buttons of the image panels (components/energy_range_slider.py
   and components/composite_image.py). A change to a panel's controls marks
   its Apply as pending from here, with no server round trip per slider tick;
   the figure builder that answers the click puts the idle props back. The
   colour and class mirror APPLY_PENDING_PROPS in energy_range_slider.py, and
   layout.css animates the class. */
const APPLY_PENDING_COLOR = "primary";
const APPLY_PENDING_CLASS = "si-apply-pending";

/* The index every triggered prop belongs to, or null when they disagree.

   A user's change reaches a marker as the changed control alone, or batched
   with the slider move the element sync callback answers a dropdown pick
   with: one or two props of one control. A panel's insertion or removal
   never reaches them (prevent_initial_call covers a new panel's own outputs,
   and a removal re-fires neither marker), but a call reporting several
   controls is not a user's change and marks nothing. */
function triggeredIndex() {
  const triggered = window.dash_clientside.callback_context.triggered || [];
  let index = null;
  for (const t of triggered) {
    const propId = t.prop_id;
    if (!propId.startsWith("{")) {
      return null;
    }
    const id = JSON.parse(propId.slice(0, propId.lastIndexOf(".")));
    const key = String(id.index);
    if (index !== null && key !== index) {
      return null;
    }
    index = key;
  }
  return index;
}

window.dash_clientside = Object.assign({}, window.dash_clientside, {
  applyButton: {
    /* single-channel panel: the dropdown, the slider and Apply share an
       index, so this is a MATCH callback returning the button's props */
    markPending: function () {
      const noUpdate = window.dash_clientside.no_update;
      if (triggeredIndex() === null) {
        return [noUpdate, noUpdate];
      }
      return [APPLY_PENDING_COLOR, APPLY_PENDING_CLASS];
    },

    /* composite panel: the channel controls are indexed "<panel>-<channel>"
       while Apply is indexed by panel, so every control is an ALL input and
       the triggered index says which panel's Apply to mark. The last
       argument is the list of Apply ids, in the order of the outputs. */
    markPanelPending: function (...args) {
      const noUpdate = window.dash_clientside.no_update;
      const applyIds = args[args.length - 1] || [];
      const noUpdates = applyIds.map(() => noUpdate);
      const index = triggeredIndex();
      if (index === null) {
        return [noUpdates, noUpdates];
      }
      const panel = parseInt(index.split("-")[0], 10);
      const pos = applyIds.findIndex((applyId) => applyId.index === panel);
      if (pos < 0) {
        return [noUpdates, noUpdates];
      }
      const colors = noUpdates.slice();
      const classes = noUpdates.slice();
      colors[pos] = APPLY_PENDING_COLOR;
      classes[pos] = APPLY_PENDING_CLASS;
      return [colors, classes];
    },
  },
});
