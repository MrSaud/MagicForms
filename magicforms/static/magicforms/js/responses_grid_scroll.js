(function () {
  var anchorId = "mf-responses-grid-table";

  function shouldScrollToGrid() {
    if (location.hash === "#" + anchorId) return true;
    return /[?&]sort=/.test(location.search);
  }

  function scrollToGrid() {
    var el = document.getElementById(anchorId);
    if (!el || !shouldScrollToGrid()) return;
    el.scrollIntoView({ block: "start", behavior: "auto" });
  }

  function run() {
    requestAnimationFrame(function () {
      requestAnimationFrame(scrollToGrid);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
