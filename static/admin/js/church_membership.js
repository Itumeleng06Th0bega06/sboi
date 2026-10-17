/*
  Church Membership dashboard: profile tab switching.

  Progressive enhancement only — the profile panel still renders without it.
*/
(function () {
  "use strict";

  function activate(scope, name) {
    scope.querySelectorAll("[data-cm-tab]").forEach(function (tab) {
      var selected = tab.getAttribute("data-cm-tab") === name;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.setAttribute("tabindex", selected ? "0" : "-1");
    });
    scope.querySelectorAll("[data-cm-panel]").forEach(function (panel) {
      var selected = panel.getAttribute("data-cm-panel") === name;
      panel.classList.toggle("is-active", selected);
      if (selected) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
    });
  }

  function init() {
    document.querySelectorAll(".cm-profile").forEach(function (scope) {
      var tabs = Array.prototype.slice.call(
        scope.querySelectorAll("[data-cm-tab]")
      );
      if (!tabs.length) {
        return;
      }
      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          activate(scope, tab.getAttribute("data-cm-tab"));
        });
        tab.addEventListener("keydown", function (event) {
          var index = tabs.indexOf(tab);
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            var next = event.key === "ArrowRight" ? index + 1 : index - 1;
            next = (next + tabs.length) % tabs.length;
            tabs[next].focus();
            activate(scope, tabs[next].getAttribute("data-cm-tab"));
          }
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
