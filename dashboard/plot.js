// plot.js - a tiny SVG time-series plot with baseline and limit bands. No library.
// P4.plot(options) returns a <div class="plot"> you can append anywhere.
//
// options = {
//   title, units,
//   t: [seconds...],                         x values (shared by every line)
//   value, baseline,                         arrays, null = gap
//   warningLow, warningHigh, criticalLow, criticalHigh,   arrays or undefined
//   markers: [{t_s, severity, label}]        optional vertical lines
// }
// Limits are already absolute numbers per point (Python did the maths).

(function () {
  var SVG = "http://www.w3.org/2000/svg";
  var W = 320, H = 140, LEFT = 40, RIGHT = 6, TOP = 6, BOTTOM = 18;

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG, tag);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    return node;
  }

  function finiteValues(arrays) {
    var out = [];
    arrays.forEach(function (arr) {
      (arr || []).forEach(function (v) { if (v !== null && v !== undefined && isFinite(v)) out.push(v); });
    });
    return out;
  }

  // Build an SVG path, starting a new segment after every null (sensor dropout or n/a).
  function pathFor(t, values, x, y) {
    var d = "", penDown = false;
    for (var i = 0; i < t.length; i++) {
      var v = values[i];
      if (v === null || v === undefined) { penDown = false; continue; }
      d += (penDown ? " L" : " M") + x(t[i]).toFixed(1) + " " + y(v).toFixed(1);
      penDown = true;
    }
    return d;
  }

  P4.plot = function (o) {
    var lines = [
      { data: o.criticalLow, cls: "crit" }, { data: o.criticalHigh, cls: "crit" },
      { data: o.warningLow, cls: "warn" }, { data: o.warningHigh, cls: "warn" },
      { data: o.baseline, cls: "baseline" }, { data: o.value, cls: "value" }
    ];
    var all = finiteValues(lines.map(function (l) { return l.data; }));
    var yMin = all.length ? Math.min.apply(null, all) : 0;
    var yMax = all.length ? Math.max.apply(null, all) : 1;
    if (yMax - yMin < 1e-9) { yMin -= 1; yMax += 1; }
    var pad = (yMax - yMin) * 0.06; yMin -= pad; yMax += pad;
    var tMin = o.t[0], tMax = o.t[o.t.length - 1] || tMin + 1;

    function x(t) { return LEFT + (t - tMin) / (tMax - tMin || 1) * (W - LEFT - RIGHT); }
    function y(v) { return TOP + (yMax - v) / (yMax - yMin) * (H - TOP - BOTTOM); }

    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    svg.appendChild(svgEl("line", { class: "axis", x1: LEFT, x2: W - RIGHT, y1: H - BOTTOM, y2: H - BOTTOM }));
    svg.appendChild(svgEl("line", { class: "axis", x1: LEFT, x2: LEFT, y1: TOP, y2: H - BOTTOM }));

    [yMax - pad, (yMax + yMin) / 2, yMin + pad].forEach(function (v) {
      var label = svgEl("text", { x: LEFT - 4, y: y(v) + 3, "text-anchor": "end" });
      label.textContent = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
      svg.appendChild(label);
    });
    [[tMin, "start"], [tMax, "end"]].forEach(function (pair) {
      var label = svgEl("text", { x: x(pair[0]), y: H - 4, "text-anchor": pair[1] });
      label.textContent = P4.met(pair[0]).substring(0, 7);
      svg.appendChild(label);
    });

    lines.forEach(function (line) {
      if (!line.data) return;
      var d = pathFor(o.t, line.data, x, y);
      if (d) svg.appendChild(svgEl("path", { class: line.cls, d: d }));
    });

    (o.markers || []).forEach(function (m) {
      if (m.t_s < tMin || m.t_s > tMax) return;   // e.g. a predicted failure in the future
      var mark = svgEl("line", { class: "marker " + (m.severity || ""), x1: x(m.t_s), x2: x(m.t_s), y1: TOP, y2: H - BOTTOM });
      var tip = svgEl("title", {}); tip.textContent = P4.met(m.t_s) + "  " + m.label;
      mark.appendChild(tip);
      svg.appendChild(mark);
    });

    var box = P4.el("div", { class: "plot" },
      P4.el("div", { class: "title" }, o.title + " ", P4.el("span", { class: "muted", text: "(" + o.units + ")" })));
    box.appendChild(svg);
    return box;
  };
})();
