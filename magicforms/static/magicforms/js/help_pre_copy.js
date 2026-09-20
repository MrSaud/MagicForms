/**
 * Studio help: copy button on each .mf-help-pre code block.
 */
(function () {
  var docRoot = document.querySelector(".mf-help-doc");
  if (!docRoot) {
    return;
  }

  var copyLabel = docRoot.getAttribute("data-mf-copy-label") || "Copy";
  var copiedLabel = docRoot.getAttribute("data-mf-copied-label") || "Copied";

  var iconCopy =
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  var iconCheck =
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

  function copyText(text, onOk) {
    if (!text) {
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(onOk).catch(fallback);
      return;
    }
    fallback();

    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        onOk();
      } catch (e) {
        /* ignore */
      }
      document.body.removeChild(ta);
    }
  }

  function showCopied(btn) {
    btn.classList.add("mf-help-pre-copy--done");
    btn.innerHTML = iconCheck;
    btn.setAttribute("aria-label", copiedLabel);
    btn.setAttribute("title", copiedLabel);
    window.setTimeout(function () {
      btn.classList.remove("mf-help-pre-copy--done");
      btn.innerHTML = iconCopy;
      btn.setAttribute("aria-label", copyLabel);
      btn.setAttribute("title", copyLabel);
    }, 1600);
  }

  docRoot.querySelectorAll("pre.mf-help-pre").forEach(function (pre) {
    if (pre.closest(".mf-help-pre-wrap")) {
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "mf-help-pre-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mf-help-pre-copy";
    btn.innerHTML = iconCopy;
    btn.setAttribute("aria-label", copyLabel);
    btn.setAttribute("title", copyLabel);
    wrap.insertBefore(btn, pre);

    btn.addEventListener("click", function () {
      var text = (pre.textContent || "").replace(/\r\n/g, "\n");
      copyText(text, function () {
        showCopied(btn);
      });
    });
  });
})();
