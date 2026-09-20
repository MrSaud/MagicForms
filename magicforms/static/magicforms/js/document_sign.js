/*
 * Post-submit document page: render the merged PDF with pdf.js and let the respondent
 * right-click (or long-press) a point to draw a signature that is stamped there.
 *
 * Coordinates sent to the server are fractions of the displayed page (origin top-left);
 * the server maps them into PDF space and re-renders the merged document.
 */
(function () {
  "use strict";

  var readJson = window.MF.readJson;
  var fmt = window.MF.fmt;
  var el = window.MF.el;

  // ---------------------------------------------------------------- signature pad

  function SignaturePad(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.drawing = false;
    this.hasInk = false;
    this.last = null;
    this.color = "#101828";
    this.bind();
    this.resize();
  }

  SignaturePad.prototype.setColor = function (color) {
    this.color = color || "#101828";
    this.ctx.strokeStyle = this.color;
  };

  SignaturePad.prototype.resize = function () {
    var rect = this.canvas.getBoundingClientRect();
    var ratio = Math.max(window.devicePixelRatio || 1, 1);
    var w = Math.max(Math.round(rect.width), 200);
    var h = Math.max(Math.round(rect.height), 120);
    this.canvas.width = w * ratio;
    this.canvas.height = h * ratio;
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.ctx.lineCap = "round";
    this.ctx.lineJoin = "round";
    this.ctx.lineWidth = 2.4;
    this.ctx.strokeStyle = this.color;
    this.clear();
  };

  SignaturePad.prototype.clear = function () {
    this.ctx.save();
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.restore();
    this.hasInk = false;
  };

  SignaturePad.prototype.point = function (ev) {
    var rect = this.canvas.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  };

  SignaturePad.prototype.bind = function () {
    var self = this;
    this.canvas.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      self.canvas.setPointerCapture(ev.pointerId);
      self.drawing = true;
      self.last = self.point(ev);
      self.ctx.beginPath();
      self.ctx.moveTo(self.last.x, self.last.y);
      self.ctx.lineTo(self.last.x + 0.1, self.last.y + 0.1);
      self.ctx.stroke();
      self.hasInk = true;
    });
    this.canvas.addEventListener("pointermove", function (ev) {
      if (!self.drawing) return;
      ev.preventDefault();
      var p = self.point(ev);
      var mid = { x: (self.last.x + p.x) / 2, y: (self.last.y + p.y) / 2 };
      self.ctx.quadraticCurveTo(self.last.x, self.last.y, mid.x, mid.y);
      self.ctx.stroke();
      self.ctx.beginPath();
      self.ctx.moveTo(mid.x, mid.y);
      self.last = p;
    });
    function stop(ev) {
      if (!self.drawing) return;
      self.drawing = false;
      self.last = null;
    }
    this.canvas.addEventListener("pointerup", stop);
    this.canvas.addEventListener("pointercancel", stop);
    this.canvas.addEventListener("pointerleave", stop);
  };

  SignaturePad.prototype.toDataURL = function () {
    return this.canvas.toDataURL("image/png");
  };

  // ---------------------------------------------------------------- document signer

  function DocumentSigner(root) {
    this.root = root;
    this.i18n = readJson("mf-pdfsign-i18n") || {};
    this.placements = readJson("mf-pdfsign-placements") || [];
    this.pdfUrl = root.getAttribute("data-pdf-url");
    this.placeUrl = root.getAttribute("data-place-url");
    this.removeUrlTemplate = root.getAttribute("data-remove-url-template");
    this.pagesEl = root.querySelector("[data-pdfsign-pages]");
    this.loadingEl = root.querySelector("[data-pdfsign-loading]");
    this.statusEl = root.querySelector("[data-pdfsign-status]");
    this.listWrap = root.querySelector("[data-pdfsign-list-wrap]");
    this.listEl = root.querySelector("[data-pdfsign-list]");
    this.overlay = root.querySelector("[data-pdfsign-overlay]");
    this.dialogError = root.querySelector("[data-pdfsign-dialog-error]");
    this.sizeSelect = root.querySelector("[data-pdfsign-size]");
    this.pad = new SignaturePad(root.querySelector("[data-pdfsign-pad]"));
    this.pending = null; // { page, x, y }
    this.busy = false;
    this.renderToken = 0;
    this.canSign = root.getAttribute("data-can-sign") !== "0";
    // Studio: a stored signature is placed on right-click without drawing; a first drawing becomes that stored signature.
    this.savedSignatureId = root.getAttribute("data-saved-signature-id") || null;
    this.decisionAfterSign = root.getAttribute("data-decision-after-sign") === "1";
    this.decisionEl = root.querySelector("[data-pdfsign-decision]") || document.querySelector("[data-pdfsign-decision]");
    if (this.decisionEl && this.decisionEl.parentNode !== document.body) document.body.appendChild(this.decisionEl);

    if (typeof pdfjsLib !== "undefined") {
      pdfjsLib.GlobalWorkerOptions.workerSrc = root.getAttribute("data-worker-src");
    }
    // The card uses backdrop-filter, which would trap a position:fixed overlay inside it.
    document.body.appendChild(this.overlay);
    this.bindDialog();
    this.renderList();
    this.loadPdf();
  }

  DocumentSigner.prototype.setBusyOverlay = function (text) {
    var existing = this.pagesEl.querySelector(".mf-busy");
    if (!text) {
      if (existing) existing.remove();
      this.pagesEl.classList.remove("is-updating");
      return;
    }
    if (!existing) {
      existing = el("div", "mf-busy");
      existing.setAttribute("role", "status");
      existing.setAttribute("aria-live", "polite");
      existing.appendChild(el("span", "mf-spinner mf-spinner--large"));
      existing.appendChild(el("span", "mf-busy__text"));
      this.pagesEl.appendChild(existing);
    }
    existing.querySelector(".mf-busy__text").textContent = text;
    this.pagesEl.classList.add("is-updating");
  };

  DocumentSigner.prototype.setStatus = function (text, kind) {
    this.statusEl.textContent = text || "";
    this.statusEl.className = "mf-pdfsign__status" + (kind ? " mf-pdfsign__status--" + kind : "");
  };

  DocumentSigner.prototype.loadPdf = function (busyText) {
    var self = this;
    if (typeof pdfjsLib === "undefined") {
      this.showFallback();
      return;
    }
    var token = ++this.renderToken;
    if (busyText) {
      this.setBusyOverlay(busyText);
    } else {
      this.loadingEl.hidden = false;
    }
    var url = this.pdfUrl + (this.pdfUrl.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now();
    pdfjsLib
      .getDocument({ url: url, withCredentials: true })
      .promise.then(function (pdf) {
        if (token !== self.renderToken) return;
        return self.renderPages(pdf, token);
      })
      .then(function () {
        if (token !== self.renderToken) return;
        self.loadingEl.hidden = true;
        self.setBusyOverlay(null);
      })
      .catch(function () {
        if (token !== self.renderToken) return;
        self.loadingEl.hidden = true;
        self.setBusyOverlay(null);
        self.showFallback();
      });
  };

  DocumentSigner.prototype.showFallback = function () {
    this.pagesEl.innerHTML = "";
    var frame = document.createElement("iframe");
    frame.className = "mf-doc-viewer";
    frame.src = this.pdfUrl;
    frame.title = "PDF";
    this.pagesEl.appendChild(frame);
    this.setStatus(this.i18n.load_failed, "error");
  };

  DocumentSigner.prototype.renderPages = function (pdf, token) {
    var self = this;
    var container = this.pagesEl;
    var staging = document.createDocumentFragment();
    var targetWidth = Math.min(container.clientWidth || 800, 960);
    var ratio = Math.max(window.devicePixelRatio || 1, 1);
    var chain = Promise.resolve();
    for (var i = 1; i <= pdf.numPages; i++) {
      (function (pageNo) {
        chain = chain.then(function () {
          if (token !== self.renderToken) return;
          return pdf.getPage(pageNo).then(function (page) {
            var base = page.getViewport({ scale: 1 });
            var scale = targetWidth / base.width;
            var viewport = page.getViewport({ scale: scale * ratio });
            var wrap = el("div", "mf-pdfsign__page");
            wrap.setAttribute("data-page-index", String(pageNo - 1));
            var canvas = el("canvas", "mf-pdfsign__canvas");
            canvas.width = Math.floor(viewport.width);
            canvas.height = Math.floor(viewport.height);
            canvas.style.aspectRatio = base.width + " / " + base.height;
            wrap.appendChild(canvas);
            wrap.appendChild(el("span", "mf-pdfsign__page-label", fmt(self.i18n.page, { n: pageNo })));
            staging.appendChild(wrap);
            self.bindPage(wrap, canvas, pageNo - 1);
            return page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
          });
        });
      })(i);
    }
    return chain.then(function () {
      if (token !== self.renderToken) return;
      var busy = container.querySelector(".mf-busy");
      container.innerHTML = "";
      container.appendChild(staging);
      if (busy) container.appendChild(busy);
    });
  };

  DocumentSigner.prototype.bindPage = function (wrap, canvas, pageIndex) {
    var self = this;
    var pressTimer = null;
    if (!this.canSign) {
      canvas.classList.add("is-readonly");
      return;
    }

    function open(ev, clientX, clientY) {
      var rect = canvas.getBoundingClientRect();
      var x = (clientX - rect.left) / rect.width;
      var y = (clientY - rect.top) / rect.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      self.openDialog({ page: pageIndex, x: x, y: y });
    }

    canvas.addEventListener("contextmenu", function (ev) {
      ev.preventDefault();
      open(ev, ev.clientX, ev.clientY);
    });
    // Long-press for touch screens (no right-click there).
    canvas.addEventListener("touchstart", function (ev) {
      if (ev.touches.length !== 1) return;
      var t = ev.touches[0];
      var cx = t.clientX;
      var cy = t.clientY;
      pressTimer = setTimeout(function () {
        pressTimer = null;
        open(ev, cx, cy);
      }, 600);
    }, { passive: true });
    ["touchend", "touchmove", "touchcancel"].forEach(function (name) {
      canvas.addEventListener(name, function () {
        if (pressTimer) {
          clearTimeout(pressTimer);
          pressTimer = null;
        }
      }, { passive: true });
    });
  };


  DocumentSigner.prototype.renderList = function () {
    var self = this;
    this.listEl.innerHTML = "";
    this.listWrap.hidden = !this.placements.length;
    this.placements.forEach(function (p, i) {
      var li = el("li", null, fmt(self.i18n.placement_label, { n: i + 1, page: p.page + 1 }));
      if (p.locked) {
        // Sealed by a later approve/reject: shown, never removable.
        li.appendChild(el("span", "mf-pdfsign__sealed", self.i18n.sealed || "Sealed"));
      } else if (self.canSign) {
        var btn = el("button", null, self.i18n.remove || "Remove");
        btn.type = "button";
        btn.addEventListener("click", function () {
          self.removePlacement(p.id);
        });
        li.appendChild(btn);
      }
      self.listEl.appendChild(li);
    });
  };

  // ---------------------------------------------------------------- dialog

  DocumentSigner.prototype.bindDialog = function () {
    var self = this;
    this.overlay.querySelector("[data-pdfsign-clear]").addEventListener("click", function () {
      self.pad.clear();
      self.dialogError.hidden = true;
    });
    this.overlay.querySelector("[data-pdfsign-cancel]").addEventListener("click", function () {
      self.closeDialog();
    });
    var swatches = this.overlay.querySelectorAll("[data-pdfsign-colors] [data-color]");
    Array.prototype.forEach.call(swatches, function (btn) {
      btn.addEventListener("click", function () {
        Array.prototype.forEach.call(swatches, function (b) {
          b.classList.toggle("is-active", b === btn);
          b.setAttribute("aria-pressed", b === btn ? "true" : "false");
        });
        self.pad.setColor(btn.getAttribute("data-color"));
      });
    });
    this.overlay.querySelector("[data-pdfsign-place]").addEventListener("click", function () {
      if (self.updateMode) self.updateSignature();
      else self.placeSignature();
    });
    this.overlay.addEventListener("click", function (ev) {
      if (ev.target === self.overlay) self.closeDialog();
    });
    // "Update signature": redraw the stored signature. Adding to the document happens only by right-click.
    var updateBtn = this.root.querySelector("[data-pdfsign-update]");
    if (updateBtn) {
      updateBtn.addEventListener("click", function () {
        self.openUpdateDialog();
      });
    }
    document.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape") return;
      if (!self.overlay.hidden) self.closeDialog();
      if (self.decisionEl && !self.decisionEl.hidden) self.closeDecision();
    });
  };

  DocumentSigner.prototype.setDialogMode = function (update) {
    var title = this.overlay.querySelector(".mf-dialog__title");
    var help = this.overlay.querySelector(".mf-dialog__title + p");
    var placeBtn = this.overlay.querySelector("[data-pdfsign-place]");
    var size = this.overlay.querySelector(".mf-pdfsign__size");
    this.updateMode = !!update;
    if (title) title.textContent = update ? this.i18n.update_title || title.textContent : this.i18n.draw_title || title.textContent;
    if (help) help.textContent = update ? this.i18n.update_help || help.textContent : this.i18n.draw_help || help.textContent;
    if (placeBtn) {
      placeBtn.textContent = update ? this.i18n.update_button || placeBtn.textContent : this.i18n.place_button || placeBtn.textContent;
      placeBtn.setAttribute("data-mf-label", placeBtn.textContent);
    }
    if (size) size.hidden = !!update;
  };

  DocumentSigner.prototype.openUpdateDialog = function () {
    this.setDialogMode(true);
    this.pending = { update: true };
    this.dialogError.hidden = true;
    this.overlay.hidden = false;
    document.body.style.overflow = "hidden";
    this.pad.resize();
  };

  DocumentSigner.prototype.updateSignature = function () {
    if (this.busy) return;
    if (!this.pad.hasInk) {
      this.dialogError.textContent = this.i18n.empty;
      this.dialogError.hidden = false;
      return;
    }
    var self = this;
    var url = this.root.getAttribute("data-signature-update-url");
    this.busy = true;
    this.setDialogBusy(true, this.i18n.updating_signature);
    this.request(url, { image: this.pad.toDataURL() })
      .then(function (data) {
        if (!data.ok) {
          self.dialogError.textContent = data.error || self.i18n.network;
          self.dialogError.hidden = false;
          return;
        }
        self.savedSignatureId = String(data.id);
        var preview = self.root.querySelector(".mf-pdfsign__saved-preview");
        if (preview && data.url) preview.src = data.url + (data.url.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now();
        self.pad.clear();
        self.closeDialog();
        self.setStatus(self.i18n.updated, "ok");
      })
      .catch(function () {
        self.dialogError.textContent = self.i18n.network;
        self.dialogError.hidden = false;
      })
      .finally(function () {
        self.busy = false;
        self.setDialogBusy(false);
      });
  };

  DocumentSigner.prototype.openDialog = function (point) {
    if (this.savedSignatureId) {
      this.placeSaved(point);
      return;
    }
    this.setDialogMode(false);
    this.pending = point;
    this.dialogError.hidden = true;
    this.overlay.hidden = false;
    document.body.style.overflow = "hidden";
    this.pad.resize();
  };

  DocumentSigner.prototype.closeDialog = function () {
    this.overlay.hidden = true;
    document.body.style.overflow = "";
    this.pending = null;
  };

  DocumentSigner.prototype.request = function (url, body) {
    return window.MF.request(url, { method: "POST", body: body || {}, root: this.root }).then(function (res) {
      var data = res.data || {};
      data._status = res.status;
      if (res.error === window.MF.NETWORK_ERROR) throw new Error("network");
      return data;
    });
  };

  DocumentSigner.prototype.placeSignature = function () {
    if (this.busy || !this.pending) return;
    if (!this.pad.hasInk) {
      this.dialogError.textContent = this.i18n.empty;
      this.dialogError.hidden = false;
      return;
    }
    var self = this;
    var payload = {
      page: this.pending.page,
      x: this.pending.x,
      y: this.pending.y,
      width: parseFloat(this.sizeSelect.value) || 0.22,
      image: this.pad.toDataURL(),
    };
    this.busy = true;
    this.setDialogBusy(true);
    this.request(this.placeUrl, payload)
      .then(function (data) {
        if (!data.ok) {
          self.dialogError.textContent = data.error || self.i18n.network;
          self.dialogError.hidden = false;
          return;
        }
        self.placements = data.placements || [];
        self.pad.clear();
        self.closeDialog();
        self.renderList();
        if (data.remember_candidate) {
          // Kept as the user's signature only when they approve or reject (the forms carry the placement id).
          self.markRememberCandidate(data.remember_candidate);
          self.setStatus(self.i18n.saved_next_time || self.i18n.placed, "ok");
        } else {
          self.setStatus(self.i18n.placed, "ok");
        }
        self.loadPdf(self.i18n.updating);
        self.offerDecision();
      })
      .catch(function () {
        self.dialogError.textContent = self.i18n.network;
        self.dialogError.hidden = false;
      })
      .finally(function () {
        self.busy = false;
        self.setDialogBusy(false);
      });
  };

  DocumentSigner.prototype.placeSaved = function (point) {
    if (this.busy) return;
    var self = this;
    this.busy = true;
    this.setBusyOverlay(this.i18n.placing_saved || this.i18n.placing);
    this.request(this.placeUrl, {
      page: point.page,
      x: point.x,
      y: point.y,
      width: parseFloat(this.sizeSelect.value) || 0.22,
      saved_signature_id: this.savedSignatureId,
    })
      .then(function (data) {
        if (!data.ok) {
          self.setBusyOverlay(null);
          self.setStatus(data.error || self.i18n.network, "error");
          return;
        }
        self.placements = data.placements || [];
        self.renderList();
        self.setStatus(self.i18n.placed, "ok");
        self.loadPdf(self.i18n.updating);
        self.offerDecision();
      })
      .catch(function () {
        self.setBusyOverlay(null);
        self.setStatus(self.i18n.network, "error");
      })
      .finally(function () {
        self.busy = false;
      });
  };

  DocumentSigner.prototype.markRememberCandidate = function (placementId) {
    document.querySelectorAll("form.mf-workflow-decision").forEach(function (form) {
      var input = form.querySelector("input[name='remember_signature_placement']");
      if (!input) {
        input = document.createElement("input");
        input.type = "hidden";
        input.name = "remember_signature_placement";
        form.appendChild(input);
      }
      input.value = String(placementId);
    });
  };

  DocumentSigner.prototype.offerDecision = function () {
    if (!this.decisionAfterSign || !this.decisionEl) return;
    var self = this;
    this.decisionEl.hidden = false;
    document.body.style.overflow = "hidden";
    var cancel = this.decisionEl.querySelector("[data-pdfsign-decision-cancel]");
    if (cancel && !cancel._bound) {
      cancel._bound = true;
      cancel.addEventListener("click", function () {
        self.closeDecision();
      });
      this.decisionEl.addEventListener("click", function (ev) {
        if (ev.target === self.decisionEl) self.closeDecision();
      });
    }
    var area = this.decisionEl.querySelector("textarea");
    if (area) window.setTimeout(function () { area.focus(); }, 0);
  };

  DocumentSigner.prototype.closeDecision = function () {
    if (!this.decisionEl) return;
    this.decisionEl.hidden = true;
    document.body.style.overflow = "";
  };

  DocumentSigner.prototype.setDialogBusy = function (busy, label) {
    var placeBtn = this.overlay.querySelector("[data-pdfsign-place]");
    window.MF.setBusy(placeBtn, busy, label || this.i18n.placing);
    this.overlay.querySelectorAll("[data-pdfsign-cancel], [data-pdfsign-clear], [data-pdfsign-size], [data-color]").forEach(function (c) {
      c.disabled = busy;
    });
    this.overlay.classList.toggle("is-busy", busy);
  };

  DocumentSigner.prototype.removePlacement = function (id) {
    if (this.busy) return;
    if (!window.confirm(this.i18n.confirm_remove)) return;
    var self = this;
    // The template was built for placement id 0 (an opaque token); swap the last id segment.
    var url = this.removeUrlTemplate.replace(/\/[^\/]+\/remove\/$/, "/" + id + "/remove/");
    this.busy = true;
    this.setBusyOverlay(this.i18n.removing);
    this.request(url)
      .then(function (data) {
        if (!data.ok) {
          self.setBusyOverlay(null);
          self.setStatus(data.error || self.i18n.network, "error");
          return;
        }
        self.placements = data.placements || [];
        self.renderList();
        self.setStatus(self.i18n.removed, "ok");
        self.loadPdf(self.i18n.updating);
      })
      .catch(function () {
        self.setBusyOverlay(null);
        self.setStatus(self.i18n.network, "error");
      })
      .finally(function () {
        self.busy = false;
      });
  };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-pdfsign]").forEach(function (root) {
      new DocumentSigner(root);
    });
  });
})();
