/**
 * Polls submission thread messages on manage detail so new posts appear without a full refresh.
 */
(function () {
  var POLL_MS = 5000;
  var root = document.getElementById("submission-thread");
  if (!root) return;
  var url = root.getAttribute("data-mf-thread-poll-url");
  if (!url) return;
  var ul = root.querySelector(".mf-thread-messages");
  if (!ul) return;

  function maxIdOnPage() {
    var max = 0;
    ul.querySelectorAll("li[data-message-id]").forEach(function (li) {
      var id = parseInt(li.getAttribute("data-message-id"), 10);
      if (!isNaN(id) && id > max) max = id;
    });
    return max;
  }

  function removeEmptyPlaceholder() {
    var empty = ul.querySelector(".mf-thread-messages__empty");
    if (empty) empty.remove();
  }

  function appendMessage(m) {
    if (ul.querySelector('li[data-message-id="' + m.id + '"]')) return;
    removeEmptyPlaceholder();
    var li = document.createElement("li");
    li.className = "mf-thread-messages__item";
    li.setAttribute("data-message-id", String(m.id));

    var meta = document.createElement("div");
    meta.className = "mf-thread-messages__meta";

    var author = document.createElement("span");
    author.className = "mf-thread-messages__author";
    author.textContent = m.author_username || "";
    meta.appendChild(author);

    if (m.author_full_name) {
      var fn = document.createElement("span");
      fn.className = "mf-muted";
      fn.textContent = "(" + m.author_full_name + ")";
      meta.appendChild(fn);
    }

    var dateEl = document.createElement("span");
    dateEl.className = "mf-thread-messages__date";
    if (m.created_title) dateEl.setAttribute("title", m.created_title);
    dateEl.textContent = m.created_display || "";
    meta.appendChild(dateEl);

    var bodyDiv = document.createElement("div");
    bodyDiv.className = "mf-thread-messages__body";
    bodyDiv.innerHTML = m.body_html || "";

    li.appendChild(meta);
    li.appendChild(bodyDiv);
    ul.appendChild(li);
  }

  function poll() {
    var since = maxIdOnPage();
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    fetch(url + sep + "since=" + encodeURIComponent(String(since)), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("thread poll " + r.status);
        return r.json();
      })
      .then(function (data) {
        var msgs = data.messages || [];
        msgs.forEach(appendMessage);
      })
      .catch(function () {});
  }

  poll();
  window.setInterval(poll, POLL_MS);
})();
