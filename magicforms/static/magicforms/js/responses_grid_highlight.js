/* Per-user row highlighting on the responses grid. */
(function () {
  "use strict";

  var body = document.querySelector("[data-grid-hl-url]");
  if (!body) return;
  var url = body.getAttribute("data-grid-hl-url");
  var roots = Array.prototype.slice.call(document.querySelectorAll("[data-grid-hl]"));
  if (!roots.length) return;
  var COLORS = ["yellow", "green", "blue", "red", "purple", "orange", "gray"];

  function setOpen(root, open) {
    var pal = root.querySelector("[data-grid-hl-palette]");
    var tog = root.querySelector("[data-grid-hl-toggle]");
    var cell = root.closest("td");
    if (pal) pal.hidden = !open;
    if (tog) tog.setAttribute("aria-expanded", open ? "true" : "false");
    if (cell) cell.classList.toggle("mf-responses-table__td--hl-open", open);
  }

  function closeAll(except) {
    roots.forEach(function (root) {
      if (root === except) return;
      setOpen(root, false);
    });
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-grid-hl]")) closeAll(null);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll(null);
  });

  roots.forEach(function (root) {
    var toggle = root.querySelector("[data-grid-hl-toggle]");
    var palette = root.querySelector("[data-grid-hl-palette]");
    var dot = root.querySelector("[data-grid-hl-dot]");
    var row = root.closest("[data-grid-hl-row]");
    if (!toggle || !palette || !row) return;

    toggle.addEventListener("click", function () {
      var willOpen = palette.hidden;
      closeAll(root);
      setOpen(root, willOpen);
    });

    palette.querySelectorAll("[data-grid-hl-color]").forEach(function (sw) {
      sw.addEventListener("click", function () {
        if (root.classList.contains("mf-inbox-highlight--busy")) return;
        var color = sw.getAttribute("data-grid-hl-color") || "";
        var data = new FormData();
        data.append("submission_id", row.getAttribute("data-submission-id") || "");
        data.append("color", color);
        root.classList.add("mf-inbox-highlight--busy");
        fetch(url, {
          method: "POST",
          headers: { "X-CSRFToken": window.MF.csrfToken() },
          credentials: "same-origin",
          body: data,
        })
          .then(function (r) { return r.json(); })
          .then(function (resp) {
            if (!resp || !resp.ok) return;
            COLORS.forEach(function (c) {
              row.classList.remove("mf-responses-table__row--hl-" + c);
              if (dot) dot.classList.remove("mf-inbox-highlight__dot--" + c);
            });
            if (color) {
              row.classList.add("mf-responses-table__row--hl-" + color);
              if (dot) dot.classList.add("mf-inbox-highlight__dot--" + color);
            }
            setOpen(root, false);
          })
          .catch(function () {})
          .finally(function () {
            root.classList.remove("mf-inbox-highlight--busy");
          });
      });
    });
  });
})();
