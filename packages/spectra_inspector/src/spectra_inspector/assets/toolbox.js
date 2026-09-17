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
