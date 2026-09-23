/* Highlights a screenshot marker and its description together while either
   is hovered (components/annotated_screenshot.py). Delegated from the
   document, since Dash mounts the pages after this script runs. */
const SI_MARKER_ATTR = "data-si-marker";
const SI_MARKER_ACTIVE = "si-marker-active";

function siMarkerSet(event) {
  const el = event.target.closest?.(
    `.si-annotated-badge, .si-annotated-list > li`,
  );
  if (!el) {
    return [];
  }
  const container = el.closest(".si-annotated");
  const number = el.getAttribute(SI_MARKER_ATTR);
  return container
    ? container.querySelectorAll(`[${SI_MARKER_ATTR}="${number}"]`)
    : [];
}

document.addEventListener("mouseover", (event) => {
  siMarkerSet(event).forEach((el) => el.classList.add(SI_MARKER_ACTIVE));
});
document.addEventListener("mouseout", (event) => {
  siMarkerSet(event).forEach((el) => el.classList.remove(SI_MARKER_ACTIVE));
});
