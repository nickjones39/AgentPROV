// Applies a theme the visitor chose on this site before the first paint (kept in this browser only; no cookie).
// Without a choice the page follows the system setting through prefers-color-scheme.
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  try {
    var choice = window.localStorage.getItem("agentprov-theme");
    if (choice === "light" || choice === "dark") root.setAttribute("data-theme", choice);
  } catch (e) { /* storage blocked: follow the system */ }
})();
