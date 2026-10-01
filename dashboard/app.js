// app.js - loads the feed files and switches between the four views.
// Everything lives on one global object, P4, so the view files can share helpers.
// No frameworks and no build step: plain functions, fetch(), and DOM calls.

var P4 = {
  feedUrl: null,     // URL of feed_index.json currently shown
  base: null,        // folder that the index's file names are relative to
  index: null,       // feed_index.json
  fleet: null,       // fleet_board.json
  alerts: null,      // alerts.json
  workOrders: null,  // work_orders.json
  robots: {},        // robot_id -> robot_<ID>.json (fetched when first viewed)
  views: {},         // view name -> render function, registered by views/*.js
  refreshTimer: null
};

// ---------- small helpers used by every view ----------

// el("div", {class: "card"}, child1, "text", ...) -> a DOM element
P4.el = function (tag, attrs) {
  var node = document.createElement(tag);
  for (var key in (attrs || {})) {
    if (key === "text") node.textContent = attrs[key];
    else if (key === "html") node.innerHTML = attrs[key];
    else node.setAttribute(key, attrs[key]);
  }
  for (var i = 2; i < arguments.length; i++) {
    var child = arguments[i];
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
};

P4.badge = function (status) {
  return P4.el("span", { class: "badge " + status, text: status });
};

// Seconds since scenario start -> "T+03:05:00"
P4.met = function (tS) {
  var h = Math.floor(tS / 3600), m = Math.floor((tS % 3600) / 60), s = Math.floor(tS % 60);
  function two(n) { return (n < 10 ? "0" : "") + n; }
  return "T+" + two(h) + ":" + two(m) + ":" + two(s);
};

P4.minutes = function (seconds) {
  return seconds === null || seconds === undefined ? "-" : Math.round(seconds / 60) + " min";
};

P4.fmt = function (value, digits) {
  return value === null || value === undefined ? "-" : Number(value).toFixed(digits === undefined ? 2 : digits);
};

P4.getJson = function (url) {
  return fetch(url, { cache: "no-store" }).then(function (response) {
    if (!response.ok) throw new Error(response.status + " " + response.statusText + " for " + url);
    return response.json();
  });
};

// ---------- loading ----------

P4.load = function (feedUrl) {
  P4.feedUrl = feedUrl;
  P4.base = feedUrl.substring(0, feedUrl.lastIndexOf("/") + 1);
  P4.robots = {};
  return P4.getJson(feedUrl).then(function (index) {
    P4.index = index;
    return Promise.all([
      P4.getJson(P4.base + index.files.fleet_board),
      P4.getJson(P4.base + index.files.alerts),
      P4.getJson(P4.base + index.files.work_orders)
    ]);
  }).then(function (files) {
    P4.fleet = files[0];
    P4.alerts = files[1];
    P4.workOrders = files[2];
    document.getElementById("sim-clock").textContent =
      P4.index.label + "  |  " + P4.index.sim_time + "  (" + P4.met(P4.index.t_s) + ")";
  });
};

// Robot detail files are larger, so fetch one only when it is first needed.
P4.loadRobot = function (robotId) {
  if (P4.robots[robotId]) return Promise.resolve(P4.robots[robotId]);
  var file = P4.index.files.robots[robotId];
  if (!file) return Promise.reject(new Error("No detail file for " + robotId));
  return P4.getJson(P4.base + file).then(function (detail) {
    P4.robots[robotId] = detail;
    return detail;
  });
};

// ---------- routing: #fleet, #robot/P2-02, #alerts, #workorders ----------

P4.route = function () {
  var parts = (location.hash || "#fleet").substring(1).split("/");
  var name = P4.views[parts[0]] ? parts[0] : "fleet";
  var tabs = document.querySelectorAll(".tabs a");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].classList.toggle("active", tabs[i].getAttribute("data-view") === name);
  }
  var main = document.getElementById("view");
  main.innerHTML = "";
  try {
    P4.views[name](main, parts[1]);
  } catch (err) {
    P4.showError(err);
  }
};

P4.showError = function (err) {
  var main = document.getElementById("view");
  main.innerHTML = "";
  main.appendChild(P4.el("div", { class: "panel error", text: "Could not show this view:\n" + err.message +
    "\n\nServe the repo root (make dashboard) rather than opening the file directly." }));
};

P4.start = function () {
  var select = document.getElementById("feed-select");
  var fromQuery = new URLSearchParams(location.search).get("feed");
  if (fromQuery) {
    select.appendChild(P4.el("option", { value: fromQuery, text: "Run: " + fromQuery }));
    select.value = fromQuery;
  }
  select.addEventListener("change", function () {
    P4.load(select.value).then(P4.route).catch(P4.showError);
  });
  window.addEventListener("hashchange", P4.route);
  P4.load(select.value).then(P4.route).catch(P4.showError);

  // A live run rewrites its feed files every batch; re-read them every 10 s.
  P4.refreshTimer = setInterval(function () {
    if (P4.index && !P4.index.is_fixture) P4.load(P4.feedUrl).then(P4.route).catch(P4.showError);
  }, 10000);
};
