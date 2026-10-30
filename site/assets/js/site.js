// The AgentPROV website's behaviour (D-1000): the theme switch, the evidence filter, the desktop-app tour, the
// platform guess for the download buttons and the copy buttons. Everything works locally in the browser: nothing is
// sent anywhere, and the page reads fully without this script.
(function () {
  "use strict";
  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  // ---------------------------------------------------------------- theme: system, light, dark
  var toggle = $("#theme-toggle");
  var THEMES = ["system", "light", "dark"];
  var NAMES = { system: "follow the system", light: "light", dark: "dark" };
  function currentTheme() { return root.getAttribute("data-theme") || "system"; }
  function labelTheme() {
    if (toggle) toggle.setAttribute("aria-label", "Colour theme: " + NAMES[currentTheme()] + ". Change theme");
  }
  if (toggle) {
    labelTheme();
    toggle.addEventListener("click", function () {
      var next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
      if (next === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", next);
      try {
        if (next === "system") window.localStorage.removeItem("agentprov-theme");
        else window.localStorage.setItem("agentprov-theme", next);
      } catch (e) { /* storage blocked: the choice lasts for this page view */ }
      labelTheme();
    });
  }

  // ---------------------------------------------------------------- evidence filter
  var graph = $("#evidence-graph");
  $$(".seg button[data-filter]").forEach(function (button, _, all) {
    button.addEventListener("click", function () {
      all.forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
      if (graph) graph.setAttribute("data-filter", button.getAttribute("data-filter"));
    });
  });

  // ---------------------------------------------------------------- the desktop-app tour
  var tabs = $$("#tour [role=tab]");
  var panels = tabs.map(function (tab) { return document.getElementById(tab.getAttribute("aria-controls")); });
  var count = $("#tour-count");
  var STAGE_RATIO = 1032 / 1560; // height / width of the main-window screenshots

  function unzoom(panel) {
    var shot = $(".shot", panel);
    if (!shot) return;
    shot.classList.remove("zoomed");
    $$("[data-spot]", panel).forEach(function (el) { el.setAttribute("aria-pressed", "false"); });
    var btn = $(".unzoom", panel);
    if (btn) btn.hidden = true;
  }

  // The point (in % of the stage) that a hotspot sits on: its own position, or for a dialog its position mapped
  // through the dialog's box (92 % of the stage height, centred, with the dialog's own aspect ratio).
  function origin(spot) {
    var x = parseFloat(spot.style.getPropertyValue("--x"));
    var y = parseFloat(spot.style.getPropertyValue("--y"));
    var dlg = spot.closest(".dlg");
    if (!dlg) return [x, y];
    var parts = dlg.style.getPropertyValue("--ar").split("/");
    var ar = parseFloat(parts[0]) / parseFloat(parts[1]);
    var h = 92;
    var w = h * ar * STAGE_RATIO;
    return [50 - w / 2 + (x * w) / 100, (100 - h) / 2 + (y * h) / 100];
  }

  function activate(panel, n) {
    var shot = $(".shot", panel);
    var spot = $(".spot[data-spot='" + n + "']", panel);
    if (!shot || !spot) return;
    panel.classList.add("touched");
    var already = spot.getAttribute("aria-pressed") === "true";
    if (already) { unzoom(panel); return; }
    $$("[data-spot]", panel).forEach(function (el) {
      el.setAttribute("aria-pressed", String(el.getAttribute("data-spot") === String(n)));
    });
    // Scale about the top-left corner, then move the point toward the centre, without uncovering the frame.
    var o = origin(spot);
    var zoom = spot.closest(".dlg") ? 1.55 : 1.85;
    function shift(p) { return Math.min(0, Math.max((1 - zoom) * 100, 50 - zoom * p)); }
    shot.style.setProperty("--zoom", String(zoom));
    shot.style.setProperty("--tx", shift(o[0]) + "%");
    shot.style.setProperty("--ty", shift(o[1]) + "%");
    shot.classList.add("zoomed");
    var btn = $(".unzoom", panel);
    if (btn) btn.hidden = false;
    var box = $(".stagebox", panel);
    var r = box.getBoundingClientRect();
    if (r.top < 60 || r.bottom > window.innerHeight) {
      box.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    }
  }

  // `user` is false only for the first selection on load: scrolling then would move the page away from its top.
  function select(i, focus, user) {
    i = (i + tabs.length) % tabs.length;
    tabs.forEach(function (tab, j) {
      var on = j === i;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
      if (!on && panels[j] && !panels[j].hidden) unzoom(panels[j]);
      if (panels[j]) panels[j].hidden = !on;
    });
    if (focus) tabs[i].focus();
    if (user) tabs[i].scrollIntoView({ block: "nearest", inline: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    if (count) count.textContent = "Step " + (i + 1) + " of " + tabs.length;
  }
  function selected() {
    for (var i = 0; i < tabs.length; i++) if (tabs[i].getAttribute("aria-selected") === "true") return i;
    return 0;
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener("click", function () { select(i, false, true); });
    tab.addEventListener("keydown", function (e) {
      var to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (to === undefined) return;
      e.preventDefault();
      select(to, true, true);
    });
  });
  var prev = $("#tour-prev"), next = $("#tour-next");
  if (prev) prev.addEventListener("click", function () { select(selected() - 1, false, true); });
  if (next) next.addEventListener("click", function () { select(selected() + 1, false, true); });

  panels.forEach(function (panel) {
    if (!panel) return;
    var box = $(".stagebox", panel);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "unzoom";
    btn.textContent = "Show the whole window";
    btn.hidden = true;
    btn.addEventListener("click", function () { unzoom(panel); });
    box.appendChild(btn);
    $$("[data-spot]", panel).forEach(function (el) {
      el.setAttribute("aria-pressed", "false");
      el.addEventListener("click", function () { activate(panel, el.getAttribute("data-spot")); });
    });
    panel.addEventListener("keydown", function (e) { if (e.key === "Escape") unzoom(panel); });
  });
  if (tabs.length) select(0, false, false);

  // ---------------------------------------------------------------- downloads: a guess at the visitor's platform
  var ASSETS = {
    "mac": { file: "AgentPROV-macos-arm64.dmg", title: "Download for macOS", sub: "Apple silicon · macOS 15 or later · disk image" },
    "windows-x64": { file: "AgentPROV-windows-x64.zip", title: "Download for Windows", sub: "x64 · Windows 11 · zip" },
    "windows-arm64": { file: "AgentPROV-windows-arm64.zip", title: "Download for Windows", sub: "ARM64 · Windows 11 · zip" },
    "linux-x64": { file: "AgentPROV-linux-x86_64.tar.gz", title: "Download for Linux", sub: "x86_64 · glibc 2.35 or later" },
    "linux-arm64": { file: "AgentPROV-linux-aarch64.tar.gz", title: "Download for Linux", sub: "aarch64 · glibc 2.39 or later" }
  };

  function apply(key) {
    var item = ASSETS[key];
    if (!item) return;
    var os = key.split("-")[0];
    var card = $(".platform[data-os='" + os + "']");
    if (card) { card.classList.add("match"); var y = $(".yours", card); if (y) y.hidden = false; }
    var link = $(".file[data-asset='" + item.file + "']");
    var primary = $("#dl-primary");
    if (primary && link) {
      primary.href = link.href;
      $("#dl-primary-label").textContent = item.title;
      $("#dl-hero-sub").textContent = item.sub + ". Read the first-launch note below.";
    }
    var hero = $("#hero-download span");
    if (hero) hero.textContent = item.title;
  }

  function guess() {
    var ua = navigator.userAgent || "";
    var data = navigator.userAgentData;
    var platform = (data && data.platform) || navigator.platform || "";
    if (/Android|iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(platform) && navigator.maxTouchPoints > 1)) return null;
    if (/Mac/i.test(platform) || /Macintosh/i.test(ua)) return Promise.resolve("mac");
    if (/Win/i.test(platform) || /Windows/i.test(ua)) {
      if (data && data.getHighEntropyValues) {
        return data.getHighEntropyValues(["architecture"]).then(function (v) {
          return v.architecture === "arm" ? "windows-arm64" : "windows-x64";
        }, function () { return "windows-x64"; });
      }
      return Promise.resolve(/ARM64|aarch64/i.test(ua) ? "windows-arm64" : "windows-x64");
    }
    if (/Linux|X11|CrOS/i.test(platform + " " + ua)) {
      return Promise.resolve(/aarch64|arm64|armv8/i.test(platform + " " + ua) ? "linux-arm64" : "linux-x64");
    }
    return null;
  }
  try {
    var guessed = guess();
    if (guessed) guessed.then(apply, function () {});
  } catch (e) { /* no guess: every download stays listed */ }

  // ---------------------------------------------------------------- copy buttons
  $$("button.copy[data-copy]").forEach(function (button) {
    var source = document.getElementById(button.getAttribute("data-copy"));
    if (!source) return;
    button.addEventListener("click", function () {
      var text = source.innerText.replace(/^\$ /gm, "");
      function done(label) {
        button.textContent = label;
        window.setTimeout(function () { button.textContent = "Copy"; }, 1800);
      }
      function fallback() {
        var range = document.createRange();
        range.selectNodeContents(source);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        done("Selected");
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done("Copied"); }, fallback);
      } else {
        fallback();
      }
    });
  });
})();
