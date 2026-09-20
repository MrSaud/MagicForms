(function () {
  function readRules() {
    var el = document.getElementById("mf-visibility-rules");
    if (!el) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  /**
   * For a group of inputs with the same name: if all are checkboxes, return selected
   * values as strings. Single HTML boolean checkbox (value "on" or "") maps to ["yes"].
   * Returns null if this is not an all-checkbox name group (e.g. select, file).
   */
  function selectedCheckboxGroupValues(form, controlKey) {
    var all = form.querySelectorAll('[name="' + controlKey + '"]');
    if (!all.length) return null;
    if (all[0].type !== "checkbox") return null;
    var i;
    for (i = 0; i < all.length; i++) {
      if (all[i].type !== "checkbox") return null;
    }
    if (all.length === 1) {
      if (!all[0].checked) return [];
      var one = String(all[0].value || "").trim();
      if (one === "on" || one === "") return ["yes"];
      return [one];
    }
    var out = [];
    for (i = 0; i < all.length; i++) {
      if (!all[i].checked) continue;
      out.push(String(all[i].value || "").trim());
    }
    return out;
  }

  function scalarControlValue(form, controlKey) {
    var first = form.querySelector('[name="' + controlKey + '"]');
    if (!first) return "";

    if (first.type === "radio") {
      var checked = form.querySelector(
        'input[name="' + controlKey + '"]:checked'
      );
      return checked ? String(checked.value || "").trim() : "";
    }

    if (first.type === "file") {
      return first.files && first.files.length
        ? String(first.files[0].name || "").trim()
        : "";
    }

    return String(first.value || "").trim();
  }

  function ruleMatches(rule, form) {
    var vals = rule.values || [];
    var sel = selectedCheckboxGroupValues(form, rule.control);
    if (sel !== null) {
      if (!sel.length) return vals.indexOf("") !== -1;
      var j;
      for (j = 0; j < sel.length; j++) {
        if (vals.indexOf(sel[j]) !== -1) return true;
      }
      return vals.indexOf(sel.join("\n")) !== -1;
    }
    var v = scalarControlValue(form, rule.control);
    return vals.indexOf(v) !== -1;
  }

  function applyRules(form, rules) {
    rules.forEach(function (rule) {
      var wrap = form.querySelector(
        '[data-mf-field-key="' + rule.target + '"]'
      );
      if (!wrap) return;

      var show = ruleMatches(rule, form);
      wrap.hidden = !show;

      var controls = wrap.querySelectorAll("input, select, textarea");
      controls.forEach(function (el) {
        el.disabled = !show;
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("form.mf-form");
    if (!form) return;

    var rules = readRules();
    if (!rules.length) return;

    applyRules(form, rules);

    form.addEventListener("change", function () {
      applyRules(form, rules);
    });

    form.addEventListener(
      "input",
      function (e) {
        if (
          e.target &&
          e.target.name &&
          e.target.name.indexOf("f_") === 0
        ) {
          applyRules(form, rules);
        }
      },
      true
    );
  });
})();
