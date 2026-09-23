/* Closes hover tooltips the mouse has left (components/tooltip.py).

   dbc.Tooltip listens for mouseover and mouseout on its target and mirrors
   its open flag into a ref from a passive effect. A mouseout that arrives
   after the show timer fired but before that effect ran is ignored, and the
   tooltip stays open until the target is hovered and left once more. The
   component's is_open prop only seeds its state, so the one way to close it
   from outside is another mouseout on the target.

   While any tooltip is mounted, every SWEEP_MS each shown one is checked
   against the element under the pointer, and gets that mouseout when the
   element is in neither its target nor its body. The stranded tooltip shows
   after the pointer's last move, so a pointer event cannot be the trigger;
   the mutation observer starts the sweeps when a tooltip mounts and they
   stop once none is left (a hidden tooltip unmounts). The tooltip's id is
   {"type": HOVER_TOOLTIP_TYPE, "index": <target DOM id>}, as
   hover_tooltip_id builds it. The mouseout does not bubble: a toolbox row is
   the target of its own tooltip and contains its buttons, and a bubbling one
   from a button would close the row's tooltip while the pointer is still in
   the row. A mouseout sent before the effect has run is ignored like the
   real one was, and the next sweep sends another. */
const HOVER_TOOLTIP_TYPE = "hover-tooltip";
const SWEEP_MS = 200;

const pointer = { x: NaN, y: NaN };
let sweepTimer = null;

function hoverTooltipTarget(tip) {
  if (!tip.id.startsWith("{")) {
    return null;
  }
  let id;
  try {
    id = JSON.parse(tip.id);
  } catch {
    return null;
  }
  if (id.type !== HOVER_TOOLTIP_TYPE || typeof id.index !== "string") {
    return null;
  }
  return document.getElementById(id.index);
}

function sweepTooltips() {
  sweepTimer = null;
  const tips = document.querySelectorAll(".tooltip");
  if (tips.length === 0) {
    return;
  }
  if (!Number.isNaN(pointer.x)) {
    const under = document.elementFromPoint(pointer.x, pointer.y);
    for (const tip of tips) {
      if (!tip.classList.contains("show")) {
        continue;
      }
      const target = hoverTooltipTarget(tip);
      if (
        target === null ||
        (under !== null && (target.contains(under) || tip.contains(under)))
      ) {
        continue;
      }
      target.dispatchEvent(new MouseEvent("mouseout", { bubbles: false }));
    }
  }
  sweepTimer = setTimeout(sweepTooltips, SWEEP_MS);
}

function scheduleSweep() {
  if (sweepTimer === null) {
    sweepTimer = setTimeout(sweepTooltips, SWEEP_MS);
  }
}

document.addEventListener(
  "mousemove",
  (event) => {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
  },
  true,
);

new MutationObserver(scheduleSweep).observe(document.body, {
  childList: true,
  subtree: true,
});
