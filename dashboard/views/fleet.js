// views/fleet.js - Fleet board: summary tiles + one card per robot (Missions 1, 4, 6).
// Reads P4.fleet (fleet_board.json). Clicking a card opens that robot's detail view.

P4.views.fleet = function (main) {
  var board = P4.fleet;
  main.appendChild(P4.el("h2", { text: "Fleet board" }));

  var s = board.summary;
  var tiles = P4.el("div", { class: "tiles" });
  [["Robots", s.robots_total], ["In service", s.in_service], ["Standby ready", s.standby_available],
   ["In maintenance", s.in_maintenance], ["Open work orders", s.open_work_orders],
   ["Missions uncovered", s.missions_uncovered]].forEach(function (pair) {
    tiles.appendChild(P4.el("div", { class: "tile" },
      P4.el("div", { class: "num", text: String(pair[1]) }), P4.el("div", { class: "lbl", text: pair[0] })));
  });
  main.appendChild(tiles);

  var grid = P4.el("div", { class: "grid" });
  board.robots.forEach(function (r) {
    var chips = P4.el("div", { class: "chips" });
    for (var subsystem in r.subsystems) {
      var chip = P4.badge(r.subsystems[subsystem]);
      chip.textContent = subsystem;
      chip.title = subsystem + ": " + r.subsystems[subsystem];
      chips.appendChild(chip);
    }
    var card = P4.el("a", { class: "card " + r.health_status, href: "#robot/" + r.robot_id, style: "text-decoration:none;color:inherit" },
      P4.el("div", { class: "row" },
        P4.el("strong", { text: r.robot_id }),
        P4.badge(r.health_status)),
      P4.el("div", { class: "row small" },
        P4.el("span", { text: r.status_label + (r.standby ? " (available)" : "") }),
        P4.el("span", { class: "muted", text: "score " + (r.health_score === null ? "-" : r.health_score) + "  |  SOC " + P4.fmt(r.soc_pct, 1) + "%" })),
      P4.el("div", { class: "small muted", text: (r.mission_label || "No mission") + "  |  " + (r.op_mode || "-") + "  |  " + r.location_zone }),
      chips,
      P4.el("div", { class: "small", style: "margin-top:6px", text: r.headline }),
      r.open_work_order_id ? P4.el("div", { class: "small muted", text: "Work order " + r.open_work_order_id }) : null);
    grid.appendChild(card);
  });
  main.appendChild(grid);
};
