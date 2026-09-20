/**
 * External POST — Test API: inline progress + themed result in #mf-outbound-test.
 */
(function () {
  var section = document.getElementById("mf-outbound-test");
  if (!section) return;

  var progress = document.getElementById("mf-outbound-test-progress");
  var progressText = progress && progress.querySelector(".mf-outbound-test-progress__text");
  var resultPanel = document.getElementById("mf-outbound-test-result");
  var resultPanelBaseClass =
    "mf-card mf-card--soft mf-stack mf-outbound-test-result";
  var customForm = document.getElementById("mf-outbound-test-custom-form");
  var customSendBtn = document.getElementById("mf-outbound-test-custom-send");

  var labels = {
    success: section.getAttribute("data-mf-label-success") || "Success",
    failed: section.getAttribute("data-mf-label-failed") || "Failed",
    resultTitle: section.getAttribute("data-mf-label-result") || "Test result",
    url: section.getAttribute("data-mf-label-url") || "URL",
    reqHeaders: section.getAttribute("data-mf-label-req-headers") || "Request headers (redacted)",
    reqBody: section.getAttribute("data-mf-label-req-body") || "Request body",
    response: section.getAttribute("data-mf-label-response") || "Response",
    noResponse: section.getAttribute("data-mf-label-no-response") || "No response body returned.",
    hint403: section.getAttribute("data-mf-hint-403") || "",
    sending: section.getAttribute("data-mf-label-sending") || "Sending request…",
    notReady:
      section.getAttribute("data-mf-not-ready-message") ||
      "Save the endpoint URL and integration settings first.",
  };

  function isTestReady() {
    return section.getAttribute("data-test-ready") === "1";
  }

  function testButtons() {
    return section.querySelectorAll(
      "form[data-mf-outbound-test] button[type=submit], #mf-outbound-test-custom-send"
    );
  }

  function setBusy(busy, message) {
    testButtons().forEach(function (btn) {
      if (busy) {
        btn.setAttribute("data-mf-was-disabled", btn.disabled ? "1" : "0");
        btn.disabled = true;
      } else {
        btn.disabled = btn.getAttribute("data-mf-was-disabled") === "1";
        btn.removeAttribute("data-mf-was-disabled");
      }
      btn.setAttribute("aria-busy", busy ? "true" : "false");
    });
    if (!progress) return;
    if (busy) {
      progress.removeAttribute("hidden");
      if (progressText) progressText.textContent = message || labels.sending;
    } else {
      progress.setAttribute("hidden", "");
    }
  }

  function setResultState(ok) {
    if (!resultPanel) return;
    resultPanel.className =
      resultPanelBaseClass + " mf-outbound-test-result--" + (ok ? "ok" : "fail");
  }

  function appendBlock(parent, labelText, contentNode) {
    var block = document.createElement("div");
    block.className = "mf-outbound-test-result__block";
    var label = document.createElement("p");
    label.className = "mf-outbound-test-result__label";
    label.textContent = labelText;
    block.appendChild(label);
    block.appendChild(contentNode);
    parent.appendChild(block);
    return block;
  }

  function appendCodeBlock(parent, labelText, text) {
    var pre = document.createElement("pre");
    pre.className = "mf-outbound-test-result__code";
    pre.textContent = text;
    return appendBlock(parent, labelText, pre);
  }

  function renderResult(result) {
    if (!resultPanel) return;
    setResultState(!!result.ok);
    resultPanel.innerHTML = "";
    resultPanel.removeAttribute("hidden");

    var header = document.createElement("div");
    header.className = "mf-outbound-test-result__header";
    var title = document.createElement("h3");
    title.className = "mf-outbound-test-result__title";
    title.textContent = labels.resultTitle;
    var badge = document.createElement("span");
    badge.className = "mf-outbound-test-result__badge";
    badge.setAttribute("aria-hidden", "true");
    badge.textContent = result.ok ? labels.success : labels.failed;
    header.appendChild(title);
    header.appendChild(badge);
    resultPanel.appendChild(header);

    var meta = document.createElement("p");
    meta.className = "mf-outbound-test-result__meta";
    var kind = document.createElement("span");
    kind.className = "mf-outbound-test-result__kind";
    kind.textContent = result.kind || "";
    meta.appendChild(kind);
    if (result.status !== undefined && result.status !== null && result.status !== "") {
      var status = document.createElement("span");
      status.className = "mf-outbound-test-result__status";
      status.textContent = "HTTP " + result.status;
      meta.appendChild(status);
    }
    resultPanel.appendChild(meta);

    if (!result.ok && result.error) {
      var err = document.createElement("p");
      err.className = "mf-outbound-test-result__error";
      err.textContent = result.error;
      resultPanel.appendChild(err);
    }

    if (result.request_url) {
      var url = document.createElement("p");
      url.className = "mf-outbound-test-result__url";
      url.textContent = result.request_url;
      appendBlock(resultPanel, labels.url, url);
    }

    if (result.request_headers_display) {
      appendCodeBlock(resultPanel, labels.reqHeaders, result.request_headers_display);
    }

    if (result.request_body) {
      appendCodeBlock(resultPanel, labels.reqBody, result.request_body);
    }

    var respBlock = document.createElement("div");
    respBlock.className =
      "mf-outbound-test-result__block mf-outbound-test-result__block--response";
    var respLabel = document.createElement("p");
    respLabel.className = "mf-outbound-test-result__label";
    respLabel.textContent = labels.response;
    respBlock.appendChild(respLabel);
    if (result.response) {
      var respPre = document.createElement("pre");
      respPre.className =
        "mf-outbound-test-result__code mf-outbound-test-result__code--response";
      respPre.textContent = result.response;
      respBlock.appendChild(respPre);
    } else {
      var empty = document.createElement("p");
      empty.className = "mf-outbound-test-result__empty";
      empty.textContent = labels.noResponse;
      respBlock.appendChild(empty);
    }
    resultPanel.appendChild(respBlock);

    if (!result.ok && Number(result.status) === 403 && labels.hint403) {
      var hint = document.createElement("p");
      hint.className = "mf-outbound-test-result__hint";
      hint.textContent = labels.hint403;
      resultPanel.appendChild(hint);
    }

    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showError(message) {
    if (!resultPanel) return;
    setResultState(false);
    resultPanel.innerHTML = "";
    resultPanel.removeAttribute("hidden");

    var header = document.createElement("div");
    header.className = "mf-outbound-test-result__header";
    var title = document.createElement("h3");
    title.className = "mf-outbound-test-result__title";
    title.textContent = labels.resultTitle;
    var badge = document.createElement("span");
    badge.className = "mf-outbound-test-result__badge";
    badge.textContent = labels.failed;
    header.appendChild(title);
    header.appendChild(badge);
    resultPanel.appendChild(header);

    var err = document.createElement("p");
    err.className = "mf-outbound-test-result__error";
    err.textContent = message;
    resultPanel.appendChild(err);
    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function handleTestResponse(res, data) {
    if (!data) {
      showError(labels.failed + (res.status ? " (HTTP " + res.status + ")" : ""));
      return;
    }
    if (data.result) {
      renderResult(data.result);
      return;
    }
    if (data.error) {
      showError(data.error);
      return;
    }
    showError(labels.failed);
  }

  function runTest(form) {
    if (!form || !form.action) return;
    if (!isTestReady()) {
      showError(labels.notReady);
      return;
    }

    var label = form.getAttribute("data-mf-progress-label") || labels.sending;
    setBusy(true, label);

    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": window.MF.csrfToken(form),
      },
    })
      .then(function (res) {
        return res
          .json()
          .then(function (data) {
            return { res: res, data: data };
          })
          .catch(function () {
            return { res: res, data: null };
          });
      })
      .then(function (payload) {
        setBusy(false);
        handleTestResponse(payload.res, payload.data);
      })
      .catch(function () {
        setBusy(false);
        showError(labels.failed);
      });
  }

  function bindTestForm(form) {
    if (!form || form.getAttribute("data-mf-outbound-test-bound") === "1") return;
    form.setAttribute("data-mf-outbound-test-bound", "1");
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      runTest(form);
    });
  }

  section.querySelectorAll("form[data-mf-outbound-test]").forEach(bindTestForm);

  if (customForm) {
    bindTestForm(customForm);
    if (customSendBtn) {
      customSendBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        runTest(customForm);
      });
    }
  }
})();
