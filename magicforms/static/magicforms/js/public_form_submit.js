/**
 * Public form: on first submit, show progress on the primary button and block duplicate submits.
 */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  onReady(function () {
    var form = document.getElementById("mf-public-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      if (form.getAttribute("data-mf-submitting") === "1") {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      form.setAttribute("data-mf-submitting", "1");
      form.classList.add("mf-form--submitting");

      // Buttons are disabled below; keep the clicked submitter's name/value in the POST.
      var submitter = e.submitter;
      if (submitter && submitter.name) {
        var hid = document.createElement("input");
        hid.type = "hidden";
        hid.name = submitter.name;
        hid.value = submitter.value || "1";
        form.appendChild(hid);
      }

      var label = form.getAttribute("data-mf-submitting-label") || "Submitting…";
      var buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
      for (var i = 0; i < buttons.length; i++) {
        var b = buttons[i];
        b.disabled = true;
        b.setAttribute("aria-busy", "true");
      }

      var primary = form.querySelector(".mf-public-form-layout__submit");
      if (primary && primary.tagName === "BUTTON") {
        primary.innerHTML = "";
        var spin = document.createElement("span");
        spin.className = "mf-submit-progress";
        spin.setAttribute("aria-hidden", "true");
        var text = document.createElement("span");
        text.className = "mf-submit-progress__text";
        text.textContent = label;
        primary.appendChild(spin);
        primary.appendChild(text);
      }
    });
  });
})();
