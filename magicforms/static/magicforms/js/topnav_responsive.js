/**
 * Hamburger toggle for [data-mf-topnav] headers (public top bar + manage studio bar).
 */
(function () {
  function closeRoot(root) {
    if (!root.classList.contains("mf-topnav--open")) return;
    root.classList.remove("mf-topnav--open");
    const btn = root.querySelector("[data-mf-topnav-toggle]");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function wireTopnav() {
    document.addEventListener("click", function (e) {
      document.querySelectorAll("[data-mf-topnav].mf-topnav--open").forEach(function (root) {
        if (!root.contains(e.target)) closeRoot(root);
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      const open = document.querySelector("[data-mf-topnav].mf-topnav--open");
      if (!open) return;
      const btn = open.querySelector("[data-mf-topnav-toggle]");
      closeRoot(open);
      if (btn) btn.focus();
    });

    document.querySelectorAll("[data-mf-topnav]").forEach(function (root) {
      const btn = root.querySelector("[data-mf-topnav-toggle]");
      if (!btn) return;
      const panelId = btn.getAttribute("aria-controls");
      const panel = panelId ? document.getElementById(panelId) : null;
      if (!panel) return;

      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        root.classList.toggle("mf-topnav--open");
        const isOpen = root.classList.contains("mf-topnav--open");
        btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
      });

      root.addEventListener("click", function (e) {
        if (!root.classList.contains("mf-topnav--open")) return;
        if (e.target.closest("[data-mf-topnav-toggle]")) return;
        if (e.target.closest("a, button[type='submit'], input, select, textarea, label")) {
          closeRoot(root);
        }
      });
    });

    const mq = window.matchMedia("(min-width: 960px)");
    function onMq() {
      if (mq.matches) {
        document.querySelectorAll("[data-mf-topnav].mf-topnav--open").forEach(closeRoot);
      }
    }
    if (mq.addEventListener) mq.addEventListener("change", onMq);
    else mq.addListener(onMq);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireTopnav);
  } else {
    wireTopnav();
  }
})();
