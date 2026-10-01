// views/workorders.js - P5 garage bays, the priority queue, and every work order with its
// embedded evidence (Missions 5, 6). Reads P4.workOrders (work_orders.json).

P4.views.workorders = function (main) {
  var feed = P4.workOrders, garage = feed.garage;
  main.appendChild(P4.el("h2", { text: "Work orders and P5 garage (" + garage.garage_id + ", capacity " + garage.capacity + ")" }));

  var bays = P4.el("div", { class: "grid" });
  garage.bays.forEach(function (b) {
    bays.appendChild(P4.el("div", { class: "card " + (b.state === "EMPTY" ? "NORMAL" : "WARNING") },
      P4.el("div", { class: "row" }, P4.el("strong", { text: b.bay_id }), P4.el("span", { text: b.state })),
      P4.el("div", { class: "small", text: b.robot_id ? b.robot_id + "  |  " + b.work_order_id : "Free" }),
      b.est_release_t_s ? P4.el("div", { class: "small muted", text: "Estimated release " + P4.met(b.est_release_t_s) }) : null));
  });
  main.appendChild(P4.el("div", { class: "panel" }, P4.el("h3", { text: "Bays" }), bays));

  var queue = P4.el("div", { class: "panel table-wrap" }, P4.el("h3", { text: "Queue (front first)" }));
  if (!garage.queue.length) {
    queue.appendChild(P4.el("div", { class: "empty", text: "Queue is empty." }));
  } else {
    var table = P4.el("table", {}, P4.el("tr", {},
      P4.el("th", { text: "#" }), P4.el("th", { text: "Work order" }), P4.el("th", { text: "Robot" }),
      P4.el("th", { text: "Severity" }), P4.el("th", { text: "Predicted time to failure" }), P4.el("th", { text: "Queued at" })));
    garage.queue.forEach(function (q) {
      table.appendChild(P4.el("tr", {},
        P4.el("td", { class: "num", text: String(q.position) }), P4.el("td", { text: q.work_order_id }),
        P4.el("td", {}, P4.el("a", { href: "#robot/" + q.robot_id, text: q.robot_id })),
        P4.el("td", {}, P4.badge(q.severity)), P4.el("td", { text: P4.minutes(q.predicted_ttf_s) }),
        P4.el("td", { class: "small", text: P4.met(q.queued_t_s) })));
    });
    queue.appendChild(table);
  }
  main.appendChild(queue);

  main.appendChild(P4.el("h3", { text: "Work orders" }));
  if (!feed.work_orders.length) main.appendChild(P4.el("div", { class: "panel empty", text: "No work orders." }));
  feed.work_orders.forEach(function (wo) { main.appendChild(workOrderPanel(wo)); });
};

function workOrderPanel(wo) {
  var f = wo.suspected_failure, act = wo.recommended_action;
  var details = P4.el("details", {},
    P4.el("summary", {}, P4.el("strong", { text: wo.work_order_id }), "  " + wo.robot.robot_id + "  ", P4.badge(wo.severity),
      "  " + wo.status + "  |  " + f.label + " (" + f.component + ")  |  failure in " + P4.minutes(wo.predicted_ttf_s) + " at creation"),
    P4.el("p", { text: wo.evidence.summary }),
    P4.el("div", { class: "small", text: "Confidence " + f.confidence.toFixed(2) + "  |  created " + P4.met(wo.created_t_s) +
      "  |  predicted failure " + (wo.predicted_failure_t_s === null ? "-" : P4.met(wo.predicted_failure_t_s)) }),
    P4.el("div", { class: "small", text: "Recommended action: " + act.code + " - " + act.text +
      " (about " + P4.minutes(act.est_repair_s) + (act.parts.length ? "; parts: " + act.parts.join(", ") : "") + ")" }));

  var grid = P4.el("div", { class: "plots" });
  wo.evidence.channels.forEach(function (ch) {
    var t = ch.points.map(function (p) { return p[0]; });
    function flat(v) { return t.map(function () { return v; }); }
    grid.appendChild(P4.plot({ title: ch.label, units: ch.units, t: t, value: ch.points.map(function (p) { return p[1]; }),
      baseline: flat(ch.baseline), warningHigh: flat(ch.warning_limit), criticalHigh: flat(ch.critical_limit) }));
  });
  details.appendChild(grid);

  var history = P4.el("ul", { class: "small" });
  wo.history.forEach(function (h) {
    history.appendChild(P4.el("li", { text: P4.met(h.t_s) + "  " + (h.from_status || "new") + " -> " + h.to_status + "  (" + h.by + ") " + h.note }));
  });
  details.appendChild(P4.el("div", { class: "small muted", text: "History" }));
  details.appendChild(history);
  return P4.el("div", { class: "panel" }, details);
}
