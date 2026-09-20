(function () {
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function workflowPillClass(state) {
    if (state === "completed") return "mf-pill--inbox-completed";
    if (state === "rejected") return "mf-pill--inbox-rejected";
    return "mf-pill--inbox-progress";
  }

  function workflowLabel(state, labels) {
    if (state === "completed") return labels.completed;
    if (state === "rejected") return labels.rejected;
    return labels.progress;
  }

  function showOpenAiNotice(root, data) {
    var noticeEl = root.querySelector("[data-inbox-ai-openai]");
    var msg = (data.openai_message || "").trim();
    if (!noticeEl) return;
    if (msg) {
      noticeEl.hidden = false;
      noticeEl.textContent = msg;
      if (data.openai_used === false && data.ai_available) {
        noticeEl.setAttribute("data-openai-fallback", "true");
      } else {
        noticeEl.removeAttribute("data-openai-fallback");
      }
    } else {
      noticeEl.hidden = true;
      noticeEl.textContent = "";
      noticeEl.removeAttribute("data-openai-fallback");
    }
  }

  function renderResults(root, data) {
    var resultsEl = root.querySelector("[data-inbox-ai-results]");
    var replyEl = root.querySelector("[data-inbox-ai-reply]");
    if (!resultsEl || !replyEl) return;

    showOpenAiNotice(root, data);

    replyEl.hidden = false;
    replyEl.textContent = data.reply || "";

    var labels = {
      step: root.getAttribute("data-label-step") || "Step",
      open: root.getAttribute("data-label-open") || "Open",
      viewAll: root.getAttribute("data-label-view-all") || "View all in inbox",
      unread: root.getAttribute("data-label-unread") || "New thread message",
      completed: root.getAttribute("data-label-completed") || "Completed",
      rejected: root.getAttribute("data-label-rejected") || "Rejected",
      progress: root.getAttribute("data-label-progress") || "In progress",
      noResults: root.getAttribute("data-label-no-results") || "No matches.",
    };

    function roleBadgesHtml(labels) {
      if (!labels || !labels.length) return "";
      return (
        '<span class="mf-inbox-meta-roles mf-inbox-meta-roles--lead">' +
        labels
          .map(function (role) {
            return '<span class="mf-badge">' + escapeHtml(role) + "</span>";
          })
          .join("") +
        "</span>"
      );
    }

    var applyLink = root.querySelector("[data-inbox-ai-apply]");
    if (applyLink && data.apply_filters_url) {
      applyLink.href = data.apply_filters_url;
      applyLink.hidden =
        !data.plan ||
        (!data.plan.q &&
          !data.plan.form_id &&
          !data.plan.step_id &&
          !data.plan.workflow_state &&
          !data.plan.submitted_from &&
          !data.plan.submitted_to &&
          !data.plan.tag &&
          !data.plan.field_name &&
          !data.plan.category_id);
    }

    var results = data.results || [];
    if (!results.length) {
      resultsEl.innerHTML =
        '<p class="mf-muted mf-body-text">' + escapeHtml(labels.noResults) + "</p>";
      return;
    }

    var html = '<ul class="mf-inbox-ai-results mf-card mf-card--glass">';
    results.forEach(function (row) {
      var title = escapeHtml(row.entity_name) + " — " + escapeHtml(row.form_title);
      var step = row.step_label
        ? '<span class="mf-inbox-step"><span class="mf-inbox-step-label">' +
          escapeHtml(labels.step) +
          "</span> " +
          escapeHtml(row.step_label) +
          "</span>"
        : "";
      var unread = row.has_unread_thread
        ? '<span class="mf-inbox-thread-badge" title="' +
          escapeHtml(labels.unread) +
          '" role="img" aria-label="' +
          escapeHtml(labels.unread) +
          '"></span>'
        : "";
      var email = row.submitter_email
        ? '<span class="mf-muted mf-inbox-ai-result-email">' + escapeHtml(row.submitter_email) + "</span>"
        : "";
      var category = row.category_name
        ? '<span class="mf-muted mf-inbox-ai-result-email">' + escapeHtml(row.category_name) + "</span>"
        : "";
      var tags =
        row.tag_labels && row.tag_labels.length
          ? '<span class="mf-inbox-ai-result-tags">' +
            row.tag_labels
              .map(function (t) {
                return '<span class="mf-pill mf-pill--private-tag">' + escapeHtml(t) + "</span>";
              })
              .join("") +
            "</span>"
          : "";
      var fields =
        row.field_snippets && row.field_snippets.length
          ? '<ul class="mf-inbox-ai-result-fields">' +
            row.field_snippets
              .map(function (f) {
                return (
                  "<li><span class=" +
                  '"mf-inbox-ai-result-field-label">' +
                  escapeHtml(f.label) +
                  "</span>: " +
                  escapeHtml(f.value) +
                  "</li>"
                );
              })
              .join("") +
            "</ul>"
          : "";
      var wf = workflowLabel(row.workflow_state, labels);
      html +=
        '<li class="mf-inbox-ai-result">' +
        '<div class="mf-inbox-ai-result-main">' +
        '<div class="mf-inbox-row-title-line">' +
        unread +
        '<a class="mf-manage-row-title" href="' +
        escapeHtml(row.manage_url) +
        '">' +
        title +
        "</a>" +
        "</div>" +
        step +
        roleBadgesHtml(row.role_labels) +
        '<div class="mf-muted mf-inbox-meta-line"><code class="mf-code">' +
        escapeHtml(row.reference) +
        "</code>" +
        email +
        category +
        "</div>" +
        tags +
        fields +
        "</div>" +
        '<div class="mf-inbox-ai-result-side">' +
        '<span class="mf-pill mf-pill--inbox-status ' +
        workflowPillClass(row.workflow_state) +
        '">' +
        escapeHtml(wf) +
        "</span>" +
        '<time class="mf-muted mf-inbox-date-corner">' +
        escapeHtml(row.submitted_display) +
        "</time>" +
        '<a class="mf-button mf-button--primary mf-button--small" href="' +
        escapeHtml(row.manage_url) +
        '">' +
        escapeHtml(labels.open) +
        "</a>" +
        "</div>" +
        "</li>";
    });
    html += "</ul>";
    resultsEl.innerHTML = html;
  }

  function setInboxAiLoading(root, on) {
    var loadingEl = root.querySelector("[data-inbox-ai-loading]");
    var chatEl = root.querySelector("[data-inbox-ai-chat]");
    var errorEl = root.querySelector("[data-inbox-ai-error]");
    var noticeEl = root.querySelector("[data-inbox-ai-openai]");
    if (errorEl) errorEl.hidden = true;
    if (noticeEl && on) noticeEl.hidden = true;
    if (loadingEl) loadingEl.hidden = !on;
    if (chatEl) chatEl.classList.toggle("mf-inbox-ai__chat--busy", !!on);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("mf-inbox-ai");
    if (!root) return;

    var form = root.querySelector("[data-inbox-ai-form]");
    var input = root.querySelector("[data-inbox-ai-input]");
    var submitBtn = root.querySelector("[data-inbox-ai-submit]");
    var errorEl = root.querySelector("[data-inbox-ai-error]");
    var loadingTextEl = root.querySelector("[data-inbox-ai-loading-text]");
    var chatUrl = root.getAttribute("data-chat-url");
    if (!form || !input || !chatUrl) return;

    setInboxAiLoading(root, false);

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var question = (input.value || "").trim();
      if (!question) {
        input.focus();
        return;
      }

      if (submitBtn) submitBtn.disabled = true;
      if (loadingTextEl) {
        loadingTextEl.textContent = root.getAttribute("data-label-searching") || "Searching…";
      }
      setInboxAiLoading(root, true);
      root.open = true;

      var body = new FormData();
      body.append("question", question);
      var csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
      if (csrfInput) body.append("csrfmiddlewaretoken", csrfInput.value);

      fetch(chatUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": window.MF.csrfToken(form),
        },
        credentials: "same-origin",
        body: body,
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error(data.message || "Request failed");
            return data;
          });
        })
        .then(function (data) {
          setInboxAiLoading(root, false);
          renderResults(root, data);
          var total = data.total_count || 0;
          var shown = (data.results || []).length;
          var countEl = root.querySelector("[data-inbox-ai-count]");
          if (countEl) {
            var tpl = root.getAttribute("data-label-count") || "%(shown)s of %(total)s";
            countEl.textContent = tpl.replace("%(shown)s", String(shown)).replace("%(total)s", String(total));
            countEl.hidden = false;
          }
        })
        .catch(function (err) {
          setInboxAiLoading(root, false);
          if (errorEl) {
            errorEl.hidden = false;
            errorEl.textContent =
              err.message || root.getAttribute("data-label-error") || "Something went wrong.";
          }
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  });
})();
