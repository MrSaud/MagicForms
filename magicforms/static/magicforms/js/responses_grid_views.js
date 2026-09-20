(function () {
  var root = document.getElementById("mf-responses-grid-views");
  if (!root) return;

  var formPk = root.getAttribute("data-form-pk");
  var baseUrl = root.getAttribute("data-base-url") || "/manage/responses-grid/";
  var submittedFrom = root.getAttribute("data-submitted-from") || "";
  var submittedTo = root.getAttribute("data-submitted-to") || "";
  var sortKey = root.getAttribute("data-sort-key") || "";
  var sortOrder = root.getAttribute("data-sort-order") || "";

  function selectedColumnKeys() {
    var boxes = root.querySelectorAll("[data-mf-grid-col]:checked");
    var keys = [];
    boxes.forEach(function (el) {
      if (el.value) keys.push(el.value);
    });
    return keys;
  }

  function buildGridUrl(opts) {
    var params = new URLSearchParams();
    params.set("form", formPk);
    if (opts.viewPk) {
      params.set("view", String(opts.viewPk));
    } else if (opts.cols && opts.cols.length) {
      params.set("cols", opts.cols.join(","));
    }
    if (submittedFrom) params.set("submitted_from", submittedFrom);
    if (submittedTo) params.set("submitted_to", submittedTo);
    if (sortKey) {
      params.set("sort", sortKey);
      params.set("order", sortOrder || "asc");
    }
    return baseUrl + "?" + params.toString() + "#mf-responses-grid-table";
  }

  function syncSaveFormCols() {
    var hidden = root.querySelector("[data-mf-grid-save-cols]");
    if (hidden) {
      hidden.value = selectedColumnKeys().join(",");
    }
  }

  root.querySelectorAll("[data-mf-grid-col]").forEach(function (el) {
    el.addEventListener("change", syncSaveFormCols);
  });

  var applyColsBtn = root.querySelector("[data-mf-grid-apply-cols]");
  if (applyColsBtn) {
    applyColsBtn.addEventListener("click", function () {
      var keys = selectedColumnKeys();
      if (!keys.length) {
        window.alert("Select at least one column.");
        return;
      }
      window.location.href = buildGridUrl({ cols: keys });
    });
  }

  var applyViewBtn = root.querySelector("[data-mf-grid-apply-view]");
  var viewSelect = root.querySelector("[data-mf-grid-view-select]");
  if (applyViewBtn && viewSelect) {
    applyViewBtn.addEventListener("click", function () {
      var v = (viewSelect.value || "").trim();
      if (v) {
        window.location.href = buildGridUrl({ viewPk: v });
      } else {
        var all = (root.getAttribute("data-all-cols") || "").split(",").filter(Boolean);
        window.location.href = buildGridUrl({ cols: all.length ? all : selectedColumnKeys() });
      }
    });
  }

  var allBtn = root.querySelector("[data-mf-grid-cols-all]");
  if (allBtn) {
    allBtn.addEventListener("click", function () {
      root.querySelectorAll("[data-mf-grid-col]").forEach(function (el) {
        el.checked = true;
      });
      syncSaveFormCols();
    });
  }

  var noneBtn = root.querySelector("[data-mf-grid-cols-none]");
  if (noneBtn) {
    noneBtn.addEventListener("click", function () {
      root.querySelectorAll("[data-mf-grid-col]").forEach(function (el) {
        el.checked = false;
      });
      syncSaveFormCols();
    });
  }

  var saveForm = root.querySelector("[data-mf-grid-save-form]");
  if (saveForm) {
    saveForm.addEventListener("submit", function () {
      syncSaveFormCols();
      var keys = selectedColumnKeys();
      if (!keys.length) {
        window.alert("Select at least one column before saving.");
        return false;
      }
      return true;
    });
  }

  syncSaveFormCols();
})();
