(function () {
  function initAssigneeSelect(el) {
    if (!el || el.dataset.tsInitialized === "1") return;
    if (typeof TomSelect === "undefined") return;

    var url = el.getAttribute("data-search-url");
    if (!url) return;

    el.dataset.tsInitialized = "1";
    // "Route to" (js-route-to-ts) picks exactly one person; the assignee/share pickers stay multi-select.
    var single = el.classList.contains("js-route-to-ts");

    new TomSelect(el, {
      plugins: single ? [] : ["remove_button"],
      persist: false,
      create: false,
      maxItems: single ? 1 : null,
      valueField: "id",
      labelField: "text",
      searchField: ["text"],
      maxOptions: 50,
      loadThrottle: 250,
      preload: "focus",
      hideSelected: !single,
      closeAfterSelect: single,
      dropdownParent: "body",
      load: function (query, callback) {
        var q = (query || "").trim();
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        var u = url + sep + "q=" + encodeURIComponent(q);
        fetch(u, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        })
          .then(function (r) {
            if (!r.ok) throw new Error("bad status");
            return r.json();
          })
          .then(function (data) {
            callback((data && data.results) || []);
          })
          .catch(function () {
            callback();
          });
      },
    });
  }

  function initAllAssigneeSelects() {
    document
      .querySelectorAll(
        "select.js-workflow-assignees-ts, select.js-mf-grid-share-ts, select.js-route-to-ts"
      )
      .forEach(initAssigneeSelect);
  }

  function syncTomSelectForSubmit(form) {
    var select = form.querySelector("select.js-mf-grid-share-ts");
    if (!select) return;
    var ts = select.tomselect;
    var syncInput = form.querySelector('input[name="share_user_ids_sync"]');
    var values = [];
    if (ts) {
      var raw = ts.getValue();
      if (Array.isArray(raw)) {
        values = raw.map(String);
      } else if (raw) {
        values = [String(raw)];
      }
    } else {
      Array.from(select.selectedOptions || []).forEach(function (opt) {
        if (opt.value) values.push(String(opt.value));
      });
    }
    select.disabled = false;
    Array.from(select.options).forEach(function (opt) {
      opt.selected = values.indexOf(String(opt.value)) >= 0;
    });
    values.forEach(function (id) {
      var sid = String(id);
      var found = false;
      Array.from(select.options).forEach(function (opt) {
        if (String(opt.value) === sid) {
          opt.selected = true;
          found = true;
        }
      });
      if (!found) {
        var opt = document.createElement("option");
        opt.value = sid;
        opt.textContent = sid;
        opt.selected = true;
        select.appendChild(opt);
      }
    });
    if (syncInput) {
      syncInput.value = values.join(",");
    }
  }

  document.addEventListener(
    "submit",
    function (ev) {
      var form = ev.target;
      if (!form || form.nodeName !== "FORM") return;
      if (
        form.querySelector("select.js-mf-grid-share-ts") ||
        form.classList.contains("mf-timeline-share-form") ||
        form.classList.contains("mf-responses-grid-views__share-form")
      ) {
        syncTomSelectForSubmit(form);
      }
    },
    true
  );

  document.addEventListener("DOMContentLoaded", function () {
    initAllAssigneeSelects();
    document.querySelectorAll("details").forEach(function (detailsEl) {
      detailsEl.addEventListener("toggle", function () {
        if (detailsEl.open) {
          initAllAssigneeSelects();
        }
      });
    });
  });
})();
