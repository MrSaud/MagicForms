/**
 * Public form sections: replace native <details> toggle so section chrome height
 * always includes long checklists (WebKit/Chromium <details> sizing bugs).
 */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function syncSection(section) {
    var btn = section.querySelector(".mf-section-summary");
    var panel = section.querySelector(".mf-section-panel");
    if (!btn || !panel) return;
    var open = section.classList.contains("mf-section--open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      panel.removeAttribute("hidden");
    } else {
      panel.setAttribute("hidden", "hidden");
    }
  }

  onReady(function () {
    var root = document.getElementById("mf-public-form");
    if (!root) return;

    var sections = root.querySelectorAll(".mf-section");
    for (var i = 0; i < sections.length; i++) {
      syncSection(sections[i]);
      (function (section) {
        var btn = section.querySelector(".mf-section-summary");
        if (!btn || btn.tagName !== "BUTTON") return;
        btn.addEventListener("click", function () {
          section.classList.toggle("mf-section--open");
          syncSection(section);
        });
      })(sections[i]);
    }
  });
})();
