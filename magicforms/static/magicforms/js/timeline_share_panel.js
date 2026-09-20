/**
 * Open the timeline share <details> panel (Share timeline button + hash deep link).
 */
(function () {
  function openSharePanel() {
    var el = document.getElementById("mf-timeline-share");
    if (!el || el.nodeName !== "DETAILS") return;
    el.open = true;
    if (typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var trigger = document.querySelector("[data-mf-open-timeline-share]");
    if (trigger) {
      trigger.addEventListener("click", function (ev) {
        ev.preventDefault();
        openSharePanel();
      });
    }
    if (window.location.hash === "#mf-timeline-share") {
      openSharePanel();
    }
  });
})();
