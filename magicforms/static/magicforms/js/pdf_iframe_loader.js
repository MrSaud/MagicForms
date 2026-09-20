/**
 * PDF inline viewers: show a loading overlay until the iframe fires `load`.
 * Iframes use `data-pdf-src` (no `src`) so the load handler is always attached before fetch starts.
 * When the viewer sits inside `<details class="mf-submission-doc-details">`, fetch starts when the panel opens.
 */
(function () {
  function hideLoading(wrap) {
    if (!wrap) return;
    wrap.classList.add("mf-doc-viewer-wrap--ready");
    var loading = wrap.querySelector(".mf-doc-viewer-loading");
    if (loading) {
      loading.setAttribute("aria-busy", "false");
    }
  }

  function hideThumbLoading(frameWrap) {
    if (!frameWrap) return;
    frameWrap.classList.add("mf-doc-thumb__frame-wrap--ready");
    var loading = frameWrap.querySelector(".mf-doc-thumb-loading");
    if (loading) loading.setAttribute("aria-busy", "false");
  }

  function markThumbFailed(frameWrap) {
    if (!frameWrap) return;
    frameWrap.classList.add("mf-doc-thumb__frame-wrap--failed");
    var loading = frameWrap.querySelector(".mf-doc-thumb-loading");
    if (loading) {
      loading.setAttribute("aria-busy", "false");
      var text = loading.querySelector(".mf-doc-thumb-loading__text");
      if (text) text.textContent = "Preview unavailable";
    }
  }

  function startThumbIframe(iframe) {
    if (!iframe || iframe.getAttribute("data-mf-thumb-init") === "1") return;
    var url = (iframe.getAttribute("data-pdf-src") || "").trim();
    if (!url) return;
    var frameWrap = iframe.closest(".mf-doc-thumb__frame-wrap");
    iframe.setAttribute("data-mf-thumb-init", "1");
    var loading = frameWrap && frameWrap.querySelector(".mf-doc-thumb-loading");
    if (loading) loading.setAttribute("aria-busy", "true");
    var done = false;
    function finish(ok) {
      if (done) return;
      done = true;
      if (ok) {
        hideThumbLoading(frameWrap);
      } else {
        markThumbFailed(frameWrap);
      }
    }
    iframe.addEventListener(
      "load",
      function () {
        finish(true);
      },
      { once: true }
    );
    iframe.addEventListener(
      "error",
      function () {
        finish(false);
      },
      { once: true }
    );
    window.setTimeout(function () {
      finish(true);
    }, 120000);
    iframe.setAttribute("src", url);
  }

  function startPdfIframe(iframe) {
    if (!iframe || iframe.getAttribute("data-mf-pdf-init") === "1") return;
    var wrap = iframe.closest(".mf-doc-viewer-wrap");
    if (!wrap) return;
    var url = iframe.getAttribute("data-pdf-src");
    if (!url) return;
    iframe.setAttribute("data-mf-pdf-init", "1");
    var loading = wrap.querySelector(".mf-doc-viewer-loading");
    if (loading) loading.setAttribute("aria-busy", "true");
    var fallbackMs = 120000;
    var done = false;
    function finish() {
      if (done) return;
      done = true;
      hideLoading(wrap);
    }
    iframe.addEventListener("load", finish, { once: true });
    iframe.addEventListener("error", finish, { once: true });
    window.setTimeout(finish, fallbackMs);
    iframe.setAttribute("src", url);
  }

  function bindDetailsPanel(details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;
      details.querySelectorAll("iframe.mf-doc-viewer[data-pdf-src]").forEach(startPdfIframe);
    });
    if (details.open) {
      details.querySelectorAll("iframe.mf-doc-viewer[data-pdf-src]").forEach(startPdfIframe);
    }
  }

  function initVisibleWrappers() {
    document.querySelectorAll(".mf-doc-viewer-wrap").forEach(function (wrap) {
      var det = wrap.closest("details.mf-submission-doc-details");
      if (det && !det.open) return;
      var iframe = wrap.querySelector("iframe.mf-doc-viewer[data-pdf-src]");
      if (iframe) startPdfIframe(iframe);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document
      .querySelectorAll("iframe.mf-doc-thumb-iframe[data-pdf-src]")
      .forEach(startThumbIframe);
    document.querySelectorAll("details.mf-submission-doc-details").forEach(bindDetailsPanel);
    initVisibleWrappers();
  });
})();
