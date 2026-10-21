// source.js - the "Scenarios" panel: generate a run and view it, without the terminal.
// Talks to the local server started by `make dashboard` (p4maint/server.py):
//   GET /api/scenarios, POST /api/generate, GET /api/job
// If those don't answer (GitHub Pages, or a plain file server) the panel stays hidden.

(function () {
  var pollTimer = null;
  var lastJob = null;

  function $(id) { return document.getElementById(id); }

  // Load a feed into the dashboard, add it to the Data menu, and keep it on reload.
  P4.showFeed = function (feedUrl, label) {
    var select = $("feed-select");
    var existing = Array.prototype.find.call(select.options, function (o) { return o.value === feedUrl; });
    if (!existing) select.appendChild(P4.el("option", { value: feedUrl, text: label }));
    select.value = feedUrl;
    history.replaceState(null, "", "?feed=" + encodeURIComponent(feedUrl) + (location.hash || "#fleet"));
    return P4.load(feedUrl).then(P4.route).catch(P4.showError);
  };

  function when(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function row(scenario, job) {
    var running = job && job.state === "running";
    var thisOne = running && job.scenario === scenario.id;
    var result = scenario.run
      ? "Last run " + when(scenario.run.generated_at) + ": " + scenario.run.score
      : "Not generated yet";

    var generate = P4.el("button", { type: "button", class: "btn primary", text: scenario.run ? "Regenerate" : "Generate" });
    generate.disabled = running;
    generate.addEventListener("click", function () { startRun(scenario.id); });

    var view = P4.el("button", { type: "button", class: "btn", text: "View" });
    view.disabled = !(scenario.run && scenario.run.feed) || thisOne;
    view.addEventListener("click", function () {
      P4.showFeed(scenario.run.feed, "Run: " + scenario.id);
      $("source-panel").hidden = true;
    });

    var more = P4.el("details", { class: "small muted" }, P4.el("summary", { text: "Details" }),
      P4.el("p", { text: scenario.description }));

    return P4.el("li", { class: "source-row" + (thisOne ? " busy" : "") },
      P4.el("div", { class: "source-text" },
        P4.el("strong", { text: scenario.id }),
        P4.el("div", { class: "small", text: scenario.overview }),
        P4.el("div", { class: "small muted", text: thisOne ? "Generating... " + Math.round(job.seconds) + " s (about 20 s)" : result }),
        more),
      P4.el("div", { class: "source-buttons" }, generate, view));
  }

  function render(data) {
    var list = $("source-list");
    list.innerHTML = "";
    data.scenarios.forEach(function (s) { list.appendChild(row(s, data.job)); });
    var job = data.job;
    var status = $("source-status");
    if (!job) status.textContent = "Pick a scenario, press Generate, then View.";
    else if (job.state === "running") status.textContent = "Generating " + job.scenario + "...";
    else if (job.state === "failed") status.textContent = "Last run failed: " + job.message;
    else status.textContent = "Finished " + job.scenario + " in " + job.seconds + " s: " + job.message;
  }

  function refresh() {
    return P4.getJson("/api/scenarios").then(function (data) {
      $("source-toggle").hidden = false;
      render(data);
      return data;
    });
  }

  function startRun(id) {
    fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" },
                             body: JSON.stringify({ scenario: id }) })
      .then(function (response) { return response.json().then(function (body) { return [response.status, body]; }); })
      .then(function (pair) {
        if (pair[0] !== 202) { $("source-status").textContent = pair[1].error || "Could not start"; return; }
        refresh();
        poll();
      });
  }

  function poll() {
    clearInterval(pollTimer);
    pollTimer = setInterval(function () {
      P4.getJson("/api/job").then(function (data) {
        var job = data.job;
        if (job && job.state === "running") { refresh(); return; }
        clearInterval(pollTimer);
        refresh().then(function (list) {
          // When a run finishes, open it straight away.
          if (job && job.state === "done" && (!lastJob || lastJob.started_at !== job.started_at)) {
            var done = list.scenarios.find(function (s) { return s.id === job.scenario; });
            if (done && done.run && done.run.feed) {
              $("source-panel").hidden = true;
              P4.showFeed(done.run.feed, "Run: " + done.id);
            }
          }
          lastJob = job;
        });
      });
    }, 2000);
  }

  P4.source = {
    init: function () {
      var toggle = $("source-toggle");
      toggle.addEventListener("click", function () {
        var panel = $("source-panel");
        panel.hidden = !panel.hidden;
        if (!panel.hidden) refresh();
      });
      refresh().then(function (data) {
        lastJob = data.job;
        if (data.job && data.job.state === "running") poll();
      }).catch(function () { /* no local server: panel stays hidden */ });
    }
  };
})();
