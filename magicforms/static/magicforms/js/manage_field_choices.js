(function () {
  function fieldTypeValue(form) {
    var el =
      form.querySelector("select[data-mf-choices-toggle]") ||
      form.querySelector('select[name="field_type"]') ||
      document.getElementById("id_field_type");
    if (!el || !form.contains(el)) return "";
    return String(el.value || "").trim().toLowerCase();
  }

  function needsChoices(v) {
    return v === "select" || v === "radio" || v === "checklist";
  }

  function needsOptionsLayout(v) {
    return v === "radio" || v === "checklist";
  }

  function isDisplayOnly(v) {
    return v === "hint" || v === "label" || v === "break";
  }

  function isBreakField(v) {
    return v === "break";
  }

  function setDisabledDeep(root, disabled) {
    if (!root) return;
    root.querySelectorAll("input, select, textarea, button").forEach(function (n) {
      n.disabled = disabled;
    });
  }

  function injectChoicesEditor(wrap) {
    if (wrap.querySelector('textarea[name="choices_text"]')) return;
    wrap.innerHTML =
      '<label class="mf-label" for="id_choices_text">Choices text</label>' +
      '<p class="mf-hint">For dropdown, radio, or checklist: one option per line.</p>' +
      '<textarea name="choices_text" id="id_choices_text" class="mf-input mf-input--textarea" rows="5" placeholder="One option per line"></textarea>';
  }

  function injectOptionsLayoutEditor(wrap, form) {
    if (wrap.querySelector('select[name="options_layout"]')) return;
    var v = fieldTypeValue(form);
    var defVal = v === "radio" ? "horizontal" : "vertical";
    var oh = defVal === "horizontal" ? ' selected="selected"' : "";
    var ov = defVal === "vertical" ? ' selected="selected"' : "";
    wrap.innerHTML =
      '<label class="mf-label" for="id_options_layout">Display options</label>' +
      '<p class="mf-hint">For radio and checklist: arrange choices in a row or a column.</p>' +
      '<select name="options_layout" id="id_options_layout" class="mf-input mf-input--select">' +
      '<option value="horizontal"' +
      oh +
      ">Horizontal</option>" +
      '<option value="vertical"' +
      ov +
      ">Vertical</option>" +
      "</select>";
  }

  function clearClientInjected(wrap) {
    if (wrap.getAttribute("data-has-server-field") === "1") return;
    wrap.innerHTML = "";
  }

  function syncChoices(form) {
    var wrap = document.getElementById("mf-choices-wrap");
    if (!wrap || !form) return;

    var v = fieldTypeValue(form);
    var show = needsChoices(v);

    if (show) {
      wrap.classList.remove("is-hidden");
      if (wrap.getAttribute("data-has-server-field") !== "1") {
        injectChoicesEditor(wrap);
      }
      setDisabledDeep(wrap, false);
    } else {
      wrap.classList.add("is-hidden");
      clearClientInjected(wrap);
      setDisabledDeep(wrap, true);
    }
  }

  function syncOptionsLayout(form) {
    var wrap = document.getElementById("mf-options-layout-wrap");
    if (!wrap || !form) return;

    var v = fieldTypeValue(form);
    var show = needsOptionsLayout(v);

    if (show) {
      wrap.classList.remove("is-hidden");
      if (wrap.getAttribute("data-has-server-field") !== "1") {
        injectOptionsLayoutEditor(wrap, form);
      }
      setDisabledDeep(wrap, false);
    } else {
      wrap.classList.add("is-hidden");
      clearClientInjected(wrap);
      setDisabledDeep(wrap, true);
    }
  }

  function syncDisplayOnly(form) {
    var v = fieldTypeValue(form);
    var displayOnly = isDisplayOnly(v);
    var breakField = isBreakField(v);
    var names = ["required", "placeholder", "mapping_key", "help_text"];
    if (breakField) {
      names = names.concat(["label", "hint", "inline"]);
    }
    names.forEach(function (name) {
      var el = form.querySelector('[name="' + name + '"]');
      if (!el) return;
      var wrap = el.closest(".mf-field") || el.closest(".mf-manage-field-group__choices");
      if (!wrap) {
        wrap = el.parentElement;
      }
      if (wrap && wrap.classList) {
        if (displayOnly) {
          wrap.classList.add("is-hidden");
        } else {
          wrap.classList.remove("is-hidden");
        }
      }
      // Do not disable hidden inputs — they must still POST for display-only fields.
      if (displayOnly && el.type === "hidden") {
        return;
      }
      el.disabled = displayOnly;
    });

    var inlineEl = form.querySelector('[name="inline"]');
    if (inlineEl) {
      var inlineWrap = inlineEl.closest(".mf-field");
      if (breakField) {
        inlineEl.checked = false;
        inlineEl.disabled = true;
        if (inlineWrap && inlineWrap.classList) {
          inlineWrap.classList.add("is-hidden");
        }
      } else {
        inlineEl.disabled = false;
        if (inlineWrap && inlineWrap.classList) {
          inlineWrap.classList.remove("is-hidden");
        }
      }
    }
  }

  function sync(form) {
    syncChoices(form);
    syncOptionsLayout(form);
    syncDisplayOnly(form);
  }

  function init() {
    var form = document.getElementById("mf-field-editor-form");
    if (!form) return;

    sync(form);
    form.addEventListener("change", function () {
      sync(form);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
