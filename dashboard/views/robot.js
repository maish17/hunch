// views/robot.js - Single-robot detail: health table, latest prediction, and one
// time-series plot per channel with baseline and WARNING / CRITICAL bands (Missions 1, 3, 4).
// Reads robot_<ID>.json, fetched on first view via P4.loadRobot().

P4.views.robot = function (main, robotId) {
  var ids = Object.keys(P4.index.files.robots).sort();
  robotId = robotId || ids[0];

  var picker = P4.el("select", {});
  ids.forEach(function (id) { picker.appendChild(P4.el("option", { value: id, text: id })); });
  picker.value = robotId;
  picker.addEventListener("change", function () { location.hash = "#robot/" + picker.value; });
  main.appendChild(P4.el("div", { class: "panel" }, P4.el("label", {}, "Robot ", picker)));

  var holder = P4.el("div", {}, P4.el("div", { class: "empty", text: "Loading " + robotId + "..." }));
  main.appendChild(holder);

  P4.loadRobot(robotId).then(function (d) {
    holder.innerHTML = "";
    holder.appendChild(P4.el("h2", {}, d.robot_id + " ", P4.badge(d.snapshot.status),
      P4.el("span", { class: "muted small", text: "  " + d.status + "  |  mode " + (d.op_mode || "-") +
        "  |  mission " + (d.mission_id || "none") + "  |  health score " + (d.snapshot.health_score === null ? "-" : d.snapshot.health_score) })));

    if (d.latest_prediction) holder.appendChild(predictionPanel(d.latest_prediction));
    holder.appendChild(healthTable(d.snapshot));
    holder.appendChild(plots(d));
  }).catch(P4.showError);
};

function predictionPanel(p) {
  var ttf = p.predicted_ttf_s === null ? "no trend" :
    P4.minutes(p.predicted_ttf_s) + " (80%: " + P4.minutes(p.predicted_ttf_interval_s.low) + " to " + P4.minutes(p.predicted_ttf_interval_s.high) + ")";
  var candidates = p.candidates.map(function (c) { return c.fault_mode + " " + c.score.toFixed(2); }).join(",  ");
  return P4.el("div", { class: "panel" },
    P4.el("h3", {}, "Latest prediction ", P4.badge(p.severity)),
    P4.el("div", {}, "Suspected: ", P4.el("strong", { text: p.fault_mode }), " on " + p.component + " (" + p.subsystem + "), confidence " + p.confidence.toFixed(2)),
    P4.el("div", { text: "Time to failure when issued at " + P4.met(p.made_at_t_s) + ": " + ttf }),
    P4.el("div", { class: "small muted", text: "All candidates: " + candidates }),
    P4.el("div", { class: "small muted", text: "Evidence: " + p.evidence_window.channels.join(", ") +
      "  |  thermal residual " + P4.fmt(p.residuals.thermal_residual_c, 1) + " degC  |  voltage residual " + P4.fmt(p.residuals.voltage_residual_v, 2) + " V" }));
}

function healthTable(snapshot) {
  var table = P4.el("table", {}, P4.el("tr", {},
    P4.el("th", { text: "Subsystem" }), P4.el("th", { text: "Component" }), P4.el("th", { text: "Channel" }),
    P4.el("th", { text: "Value" }), P4.el("th", { text: "Baseline" }), P4.el("th", { text: "Deviation" }),
    P4.el("th", { text: "Status" }), P4.el("th", { text: "Rule" })));
  snapshot.subsystems.forEach(function (sub) {
    sub.components.forEach(function (comp) {
      comp.channels.forEach(function (ch) {
        table.appendChild(P4.el("tr", {},
          P4.el("td", {}, sub.subsystem + " ", P4.badge(sub.status)),
          P4.el("td", { class: "small", text: comp.component }),
          P4.el("td", { class: "small", text: ch.channel }),
          P4.el("td", { class: "num", text: P4.fmt(ch.value, 2) + " " + ch.units }),
          P4.el("td", { class: "num", text: P4.fmt(ch.baseline, 2) }),
          P4.el("td", { class: "num", text: P4.fmt(ch.deviation, 2) }),
          P4.el("td", {}, P4.badge(ch.status)),
          P4.el("td", { class: "small muted", text: ch.rule || "" })));
      });
    });
  });
  return P4.el("div", { class: "panel table-wrap" },
    P4.el("h3", { text: "Health at " + P4.met(snapshot.t_s) + " (judged against the " + snapshot.op_mode + " baseline)" }), table);
}

function plots(d) {
  var box = P4.el("div", { class: "panel" }, P4.el("h3", { text: "Last 2 hours (1-minute means)" }),
    P4.el("div", { class: "legend" },
      P4.el("span", { text: "solid = measured" }), P4.el("span", { text: "dashed = mode baseline" }),
      P4.el("span", { style: "color:var(--warning)", text: "amber = WARNING limit" }),
      P4.el("span", { style: "color:var(--critical)", text: "red = CRITICAL limit" }),
      P4.el("span", { style: "color:var(--info)", text: "vertical = events (hover)" })));
  var grid = P4.el("div", { class: "plots" });
  d.series.channels.forEach(function (ch) {
    var markers = d.markers.filter(function (m) { return m.channel === null || m.channel === ch.channel; });
    grid.appendChild(P4.plot({
      title: ch.label, units: ch.units, t: d.series.t_s, value: ch.value, baseline: ch.baseline,
      warningLow: ch.warning_low, warningHigh: ch.warning_high, criticalLow: ch.critical_low, criticalHigh: ch.critical_high,
      markers: markers }));
  });
  box.appendChild(grid);
  return box;
}
