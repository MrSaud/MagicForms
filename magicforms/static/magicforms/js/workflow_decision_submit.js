/**
 * Workflow approve/reject: on submit, disable related buttons and show a circular
 * loading indicator until the next page loads (full postback).
 * Approve submits show a short undo-window hint when the form provides data-mf-approve-undo-hint.
 */
(function () {
  var undoLiveEl = null;

  function isApproveSubmit(form, submitter) {
    if (
      submitter &&
      submitter.name === "workflow_decision" &&
      String(submitter.value || "").trim() === "approve"
    ) {
      return true;
    }
    var hidden = form.querySelector("input[name='workflow_decision']");
    return !!(
      hidden &&
      String(hidden.value || hidden.getAttribute("value") || "").trim() === "approve"
    );
  }

  function showApproveUndoHint(form) {
    var hint = String(form.getAttribute("data-mf-approve-undo-hint") || "").trim();
    if (!hint) {
      return;
    }
    if (!undoLiveEl) {
      undoLiveEl = document.createElement("div");
      undoLiveEl.id = "mf-workflow-approve-undo-live";
      undoLiveEl.className = "mf-workflow-approve-undo-live";
      undoLiveEl.setAttribute("role", "status");
      undoLiveEl.setAttribute("aria-live", "polite");
      document.body.appendChild(undoLiveEl);
    }
    undoLiveEl.textContent = hint;
    undoLiveEl.classList.add("mf-workflow-approve-undo-live--visible");
  }

  function markBusy(button, form) {
    if (!button || button.getAttribute("data-mf-workflow-busy") === "1") return;
    var raw = (form && form.getAttribute("data-mf-busy-label")) || "";
    var label = String(raw).trim();
    var ariaRaw = (form && form.getAttribute("data-mf-busy-aria-label")) || "";
    var aria = String(ariaRaw).trim();

    /* Inbox uses a hidden input for workflow_decision; submission detail uses two named
     * submit buttons. Disabled submit buttons are omitted from POST, so never disable the
     * clicked button when multiple workflow submitters share one form. */
    var multiNamedSubmitters =
      form &&
      form.querySelectorAll("button[type='submit'][name='workflow_decision']").length > 1;

    button.setAttribute("data-mf-workflow-busy", "1");
    button.dataset.mfWorkflowOrigHtml = button.innerHTML;
    var prevText = (button.textContent || "").trim();
    if (!multiNamedSubmitters) {
      button.disabled = true;
    }
    button.setAttribute("aria-busy", "true");
    if (aria) {
      button.setAttribute("aria-label", aria);
    } else if (prevText) {
      button.setAttribute("aria-label", prevText);
    }

    button.classList.add("mf-button--busy");
    if (!label) {
      button.classList.add("mf-button--busy-no-label");
    }

    while (button.firstChild) {
      button.removeChild(button.firstChild);
    }
    var spin = document.createElement("span");
    spin.className = "mf-workflow-busy-spinner";
    spin.setAttribute("aria-hidden", "true");
    button.appendChild(spin);
    if (label) {
      var lbl = document.createElement("span");
      lbl.className = "mf-workflow-busy-label";
      lbl.textContent = label;
      button.appendChild(lbl);
    }
  }

  function buttonsInScope(form) {
    var inbox = form.closest(".mf-manage-row-actions--inbox-quick");
    if (inbox) {
      return inbox.querySelectorAll("form.mf-workflow-decision button[type='submit']");
    }
    return form.querySelectorAll("button[type='submit'][name='workflow_decision']");
  }

  document.addEventListener(
    "submit",
    function (ev) {
      var form = ev.target;
      if (!form || form.nodeName !== "FORM" || !form.classList.contains("mf-workflow-decision")) {
        return;
      }
      var submitter = ev.submitter;
      if (!submitter || submitter.type !== "submit") {
        return;
      }
      if (form.getAttribute("data-mf-workflow-submitting") === "1") {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      form.setAttribute("data-mf-workflow-submitting", "1");

      if (isApproveSubmit(form, submitter)) {
        showApproveUndoHint(form);
      }

      var list = buttonsInScope(form);
      for (var i = 0; i < list.length; i++) {
        var btn = list[i];
        if (btn === submitter) {
          markBusy(btn, form);
        } else {
          btn.disabled = true;
          btn.classList.add("mf-button--workflow-pending");
        }
      }
    },
    false
  );
})();
