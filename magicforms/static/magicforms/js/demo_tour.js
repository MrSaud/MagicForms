(function () {
  // Tabbed walkthroughs on the public product tour. Without this script every panel stays visible.
  function enhance(root) {
    var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (tab) {
      return document.getElementById(tab.getAttribute("aria-controls"));
    });
    if (!tabs.length) return;

    function select(index, focus) {
      tabs.forEach(function (tab, i) {
        var active = i === index;
        tab.setAttribute("aria-selected", active ? "true" : "false");
        tab.setAttribute("tabindex", active ? "0" : "-1");
        tab.classList.toggle("is-done", i < index);
        if (panels[i]) panels[i].hidden = !active;
      });
      if (focus) tabs[index].focus();
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () {
        select(i, false);
      });
      tab.addEventListener("keydown", function (ev) {
        var rtl = window.getComputedStyle(root).direction === "rtl";
        var next = null;
        if (ev.key === "ArrowRight") next = rtl ? i - 1 : i + 1;
        else if (ev.key === "ArrowLeft") next = rtl ? i + 1 : i - 1;
        else if (ev.key === "Home") next = 0;
        else if (ev.key === "End") next = tabs.length - 1;
        if (next === null) return;
        ev.preventDefault();
        select((next + tabs.length) % tabs.length, true);
      });
    });

    root.classList.add("is-enhanced");
    var current = tabs.findIndex(function (tab) {
      return tab.getAttribute("aria-selected") === "true";
    });
    select(current < 0 ? 0 : current, false);
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mf-tabs]"), enhance);
  });
})();
