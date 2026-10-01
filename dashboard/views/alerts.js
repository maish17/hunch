// views/alerts.js - Alert feed, newest first (Mission 2: alert the operator).
// Reads P4.alerts (alerts.json). Titles were written by Python; this only lists them.

P4.views.alerts = function (main) {
  main.appendChild(P4.el("h2", { text: "Alert feed" }));

  var filter = P4.el("select", {},
    P4.el("option", { value: "ALL", text: "All severities" }),
    P4.el("option", { value: "CRITICAL", text: "Critical only" }),
    P4.el("option", { value: "WARNING", text: "Warning and critical" }));
  main.appendChild(P4.el("div", { class: "panel" }, P4.el("label", {}, "Show ", filter)));

  var holder = P4.el("div", { class: "panel table-wrap" });
  main.appendChild(holder);

  function draw() {
    holder.innerHTML = "";
    var wanted = filter.value;
    var rows = P4.alerts.alerts.filter(function (a) {
      if (wanted === "CRITICAL") return a.severity === "CRITICAL";
      if (wanted === "WARNING") return a.severity === "CRITICAL" || a.severity === "WARNING";
      return true;
    });
    if (!rows.length) {
      holder.appendChild(P4.el("div", { class: "empty", text: "No alerts. Every robot is within limits." }));
      return;
    }
    var table = P4.el("table", {}, P4.el("tr", {},
      P4.el("th", { text: "Time" }), P4.el("th", { text: "Severity" }), P4.el("th", { text: "Kind" }),
      P4.el("th", { text: "Robot" }), P4.el("th", { text: "Subsystem / channel" }), P4.el("th", { text: "What happened" })));
    rows.forEach(function (a) {
      table.appendChild(P4.el("tr", {},
        P4.el("td", { class: "small", text: P4.met(a.t_s) }),
        P4.el("td", {}, P4.badge(a.severity)),
        P4.el("td", { class: "small", text: a.kind }),
        P4.el("td", {}, a.robot_id ? P4.el("a", { href: "#robot/" + a.robot_id, text: a.robot_id }) : "-"),
        P4.el("td", { class: "small", text: (a.subsystem || "-") + (a.channel ? " / " + a.channel : "") }),
        P4.el("td", {}, P4.el("div", { text: a.title }), P4.el("div", { class: "small muted", text: a.detail }))));
    });
    holder.appendChild(table);
  }

  filter.addEventListener("change", draw);
  draw();
};
