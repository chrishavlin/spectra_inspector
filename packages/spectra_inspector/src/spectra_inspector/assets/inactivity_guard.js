/* The idle clock behind the "still working?" overlay
   (components/inactivity_guard.py, which explains what it is for).

   Any input stamps the time; a slow poll compares the stamp against the
   timeout the layout put on the guard element and opens the modal once it is
   exceeded. Comparing wall-clock stamps rather than counting ticks keeps the
   answer right when the browser throttles a background tab's timers or the
   machine sleeps. While the modal is up input is not stamped, so moving the
   mouse towards a button does not count as an answer. */
const SI_INACTIVITY_GUARD_ID = "si-inactivity-guard";
const SI_INACTIVITY_MODAL_ID = "si-inactivity-modal";
const SI_INACTIVITY_POLL_MS = 1000;
const SI_INACTIVITY_EVENTS = [
  "mousemove",
  "mousedown",
  "keydown",
  "wheel",
  "touchstart",
  "scroll",
];

(function () {
  let lastActivity = Date.now();
  let prompting = false;

  function stamp() {
    if (!prompting) {
      lastActivity = Date.now();
    }
  }

  /* Read on every poll: Dash mounts the layout after this script runs. */
  function timeoutMs() {
    const guard = document.getElementById(SI_INACTIVITY_GUARD_ID);
    const seconds = guard ? Number(guard.dataset.timeoutSeconds) : 0;
    return seconds > 0 ? seconds * 1000 : 0;
  }

  function poll() {
    const timeout = timeoutMs();
    if (prompting || timeout === 0) {
      return;
    }
    if (Date.now() - lastActivity >= timeout) {
      prompting = true;
      window.dash_clientside.set_props(SI_INACTIVITY_MODAL_ID, {
        is_open: true,
      });
    }
  }

  for (const eventName of SI_INACTIVITY_EVENTS) {
    document.addEventListener(eventName, stamp, {
      capture: true,
      passive: true,
    });
  }
  window.setInterval(poll, SI_INACTIVITY_POLL_MS);

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    inactivityGuard: {
      /* Continue: close the modal and start the clock again */
      dismiss: function () {
        prompting = false;
        lastActivity = Date.now();
        return false;
      },
    },
  });
})();
