/*
 * Form delete confirmation: opens a dialog and only enables the Delete button once the
 * respondent has typed the confirmation word (the server checks it again).
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var opener = document.querySelector("[data-mf-delete-open]");
    var backdrop = document.querySelector("[data-mf-delete-dialog]");
    if (!opener || !backdrop) return;

    var input = backdrop.querySelector("[data-mf-delete-input]");
    var submit = backdrop.querySelector("[data-mf-delete-submit]");
    var cancel = backdrop.querySelector("[data-mf-delete-cancel]");
    var expected = (backdrop.getAttribute("data-mf-delete-word") || "confirm").trim().toLowerCase();

    // The card uses backdrop-filter in some themes; keep the fixed overlay at body level.
    document.body.appendChild(backdrop);

    function sync() {
      var ok = (input.value || "").trim().toLowerCase() === expected;
      submit.disabled = !ok;
    }

    function open() {
      backdrop.hidden = false;
      document.body.style.overflow = "hidden";
      input.value = "";
      sync();
      window.setTimeout(function () {
        input.focus();
      }, 0);
    }

    function close() {
      backdrop.hidden = true;
      document.body.style.overflow = "";
    }

    opener.addEventListener("click", open);
    cancel.addEventListener("click", close);
    input.addEventListener("input", sync);
    backdrop.addEventListener("click", function (ev) {
      if (ev.target === backdrop) close();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !backdrop.hidden) close();
    });
    backdrop.querySelector("form").addEventListener("submit", function (ev) {
      sync();
      if (submit.disabled) ev.preventDefault();
    });
  });
})();
