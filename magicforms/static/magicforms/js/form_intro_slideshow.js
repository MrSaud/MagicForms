/**
 * Announcement page gallery: fit images, manual nav, optional auto-advance.
 */
(function () {
  var root = document.querySelector("[data-mf-intro-slideshow]");
  if (!root) return;

  var track = root.querySelector("[data-mf-intro-slideshow-track]");
  var slides = track ? track.querySelectorAll("[data-mf-intro-slide]") : [];
  if (!slides.length) return;

  var prevBtn = root.querySelector("[data-mf-intro-slideshow-prev]");
  var nextBtn = root.querySelector("[data-mf-intro-slideshow-next]");
  var dots = root.querySelectorAll("[data-mf-intro-slideshow-dot]");
  var index = 0;
  var timer = null;
  var autoplayMs = parseInt(root.getAttribute("data-mf-intro-autoplay-ms") || "5000", 10);
  if (!autoplayMs || autoplayMs < 2000) autoplayMs = 5000;

  var reducedMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function clearAutoplay() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function scheduleAutoplay() {
    clearAutoplay();
    if (reducedMotion || slides.length <= 1) return;
    timer = setInterval(function () {
      show(index + 1, true);
    }, autoplayMs);
  }

  function show(i, fromAutoplay) {
    index = (i + slides.length) % slides.length;
    for (var s = 0; s < slides.length; s++) {
      slides[s].hidden = s !== index;
      slides[s].setAttribute("aria-hidden", s !== index ? "true" : "false");
    }
    for (var d = 0; d < dots.length; d++) {
      var on = d === index;
      dots[d].classList.toggle("is-active", on);
      dots[d].setAttribute("aria-selected", on ? "true" : "false");
    }
    if (prevBtn) prevBtn.disabled = slides.length <= 1;
    if (nextBtn) nextBtn.disabled = slides.length <= 1;
    if (!fromAutoplay) scheduleAutoplay();
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      show(index - 1, false);
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      show(index + 1, false);
    });
  }
  for (var di = 0; di < dots.length; di++) {
    (function (dotIdx) {
      dots[dotIdx].addEventListener("click", function () {
        show(dotIdx, false);
      });
    })(di);
  }

  root.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowLeft") {
      show(index - 1, false);
      ev.preventDefault();
    } else if (ev.key === "ArrowRight") {
      show(index + 1, false);
      ev.preventDefault();
    }
  });

  root.addEventListener("mouseenter", clearAutoplay);
  root.addEventListener("mouseleave", scheduleAutoplay);
  root.addEventListener("focusin", clearAutoplay);
  root.addEventListener("focusout", function (ev) {
    if (!root.contains(ev.relatedTarget)) scheduleAutoplay();
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) clearAutoplay();
    else scheduleAutoplay();
  });

  show(0, true);
  scheduleAutoplay();
})();
