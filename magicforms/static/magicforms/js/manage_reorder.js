(function () {
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof Sortable === "undefined") return;

    document.querySelectorAll("[data-sortable]").forEach(function (root) {
      var url = root.getAttribute("data-reorder-url");
      var list = root.querySelector("[data-sortable-list]");
      if (!url || !list) return;

      Sortable.create(list, {
        handle: ".drag-handle",
        animation: 150,
        draggable: ".mf-sort-item",
        onEnd: function () {
          var ids = Array.prototype.map.call(list.querySelectorAll("[data-id]"), function (el) {
            return parseInt(el.getAttribute("data-id"), 10);
          });
          window.MF.request(url, { body: { order: ids } });
        },
      });
    });
  });
})();
