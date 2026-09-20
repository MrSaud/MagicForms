/*
 * Visual workflow builder (studio → form → Workflow).
 *
 * Renders a vertical path: start → step … → end, with "+" insert points between nodes.
 * Selecting a node fills the side panel; every save/delete/move round-trips to the server,
 * which answers with the full state so the canvas is always re-rendered from truth.
 */
(function () {
  "use strict";

  var readJson = window.MF.readJson;
  var fmt = window.MF.fmt;
  var el = window.MF.el;

  var NEW_ID = "new";

  function Builder(root) {
    this.root = root;
    this.i18n = readJson("mf-wfb-i18n") || {};
    var initial = readJson("mf-wfb-state") || { steps: [] };
    this.state = initial;
    this.urls = {
      state: root.getAttribute("data-state-url"),
      save: root.getAttribute("data-save-url"),
      deleteTpl: root.getAttribute("data-delete-url-template"),
      reorder: root.getAttribute("data-reorder-url"),
    };
    this.canvas = root.querySelector("[data-wfb-canvas]");
    this.panel = root.querySelector("[data-wfb-panel]");
    this.panelBody = root.querySelector("[data-wfb-panel-body]");
    this.panelEmpty = root.querySelector("[data-wfb-empty]");
    this.checkBox = root.querySelector("[data-wfb-check]");
    this.checkList = root.querySelector("[data-wfb-check-list]");
    this.inputs = {
      label: root.querySelector("[data-wfb-label]"),
      description: root.querySelector("[data-wfb-description]"),
      assignees: root.querySelector("[data-wfb-assignees]"),
    };
    this.errors = {
      label: root.querySelector("[data-wfb-error-label]"),
      description: root.querySelector("[data-wfb-error-description]"),
      assignees: root.querySelector("[data-wfb-error-assignees]"),
      general: root.querySelector("[data-wfb-error]"),
    };
    this.hintAssignees = root.querySelector("[data-wfb-hint-assignees]");
    this.submissionsNote = root.querySelector("[data-wfb-submissions-note]");
    this.status = root.querySelector("[data-wfb-status]");
    this.saveBtn = root.querySelector("[data-wfb-save]");
    this.cancelBtn = root.querySelector("[data-wfb-cancel]");
    this.deleteBtn = root.querySelector("[data-wfb-delete]");
    this.secondary = root.querySelector("[data-wfb-secondary]");
    this.moveBtns = root.querySelectorAll("[data-wfb-move]");

    this.selectedId = null; // number | "new" | null
    this.draft = null; // { insertAfter: "start" | number | null } while composing a new step
    this.dirty = false;
    this.busy = false;

    this.initAssigneePicker();
    this.bind();
    this.render();
  }

  Builder.prototype.initAssigneePicker = function () {
    var select = this.inputs.assignees;
    var self = this;
    if (!select || typeof TomSelect === "undefined") return;
    var url = select.getAttribute("data-search-url");
    this.ts = new TomSelect(select, {
      plugins: ["remove_button"],
      persist: false,
      create: false,
      maxItems: null,
      valueField: "id",
      labelField: "text",
      searchField: ["text"],
      maxOptions: 50,
      loadThrottle: 250,
      preload: "focus",
      hideSelected: true,
      closeAfterSelect: false,
      dropdownParent: "body",
      load: function (query, callback) {
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        fetch(url + sep + "q=" + encodeURIComponent((query || "").trim()), {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        })
          .then(function (r) {
            return r.ok ? r.json() : { results: [] };
          })
          .then(function (data) {
            callback((data && data.results) || []);
          })
          .catch(function () {
            callback();
          });
      },
      onChange: function () {
        self.markDirty();
        self.updateAssigneeHint();
      },
    });
  };

  Builder.prototype.bind = function () {
    var self = this;
    this.panel.addEventListener("submit", function (ev) {
      ev.preventDefault();
      self.save();
    });
    this.cancelBtn.addEventListener("click", function () {
      self.deselect(true);
    });
    this.deleteBtn.addEventListener("click", function () {
      self.remove();
    });
    Array.prototype.forEach.call(this.moveBtns, function (btn) {
      btn.addEventListener("click", function () {
        self.move(btn.getAttribute("data-wfb-move"));
      });
    });
    ["label", "description"].forEach(function (k) {
      self.inputs[k].addEventListener("input", function () {
        self.markDirty();
        if (k === "label") self.syncDraftLabel();
      });
    });
    window.addEventListener("beforeunload", function (ev) {
      if (self.dirty) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    });
  };

  // ---------- state helpers ----------

  Builder.prototype.stepById = function (id) {
    for (var i = 0; i < this.state.steps.length; i++) {
      if (this.state.steps[i].id === id) return this.state.steps[i];
    }
    return null;
  };

  Builder.prototype.assigneeIds = function () {
    if (this.ts) {
      var v = this.ts.getValue();
      return (Array.isArray(v) ? v : v ? [v] : []).map(function (x) {
        return parseInt(x, 10);
      });
    }
    return Array.prototype.map.call(this.inputs.assignees.selectedOptions, function (o) {
      return parseInt(o.value, 10);
    });
  };

  Builder.prototype.markDirty = function () {
    this.dirty = true;
  };

  Builder.prototype.confirmDiscard = function () {
    if (!this.dirty) return true;
    return window.confirm(this.i18n.confirm_discard || "Discard unsaved changes?");
  };

  // ---------- rendering ----------

  Builder.prototype.render = function () {
    this.renderCanvas();
    this.renderCheck();
  };

  Builder.prototype.renderCanvas = function () {
    var self = this;
    var steps = this.state.steps;
    var frag = document.createDocumentFragment();

    // Build the visual sequence, inserting the unsaved draft card where it belongs.
    var sequence = [];
    var draftPlaced = false;
    if (this.draft && this.draft.insertAfter === "start") {
      sequence.push({ draft: true });
      draftPlaced = true;
    }
    steps.forEach(function (s) {
      sequence.push({ step: s });
      if (self.draft && self.draft.insertAfter === s.id) {
        sequence.push({ draft: true });
        draftPlaced = true;
      }
    });
    if (this.draft && !draftPlaced) sequence.push({ draft: true });

    frag.appendChild(this.terminalNode(this.i18n.start, "start"));
    frag.appendChild(this.insertPoint("start"));

    sequence.forEach(function (item) {
      if (item.draft) {
        frag.appendChild(self.draftCard());
      } else {
        frag.appendChild(self.stepCard(item.step));
        frag.appendChild(self.insertPoint(item.step.id));
      }
    });

    frag.appendChild(this.terminalNode(this.i18n.end, "end"));

    // Keep the <noscript> fallback out of the way once JS runs.
    this.canvas.querySelectorAll(":scope > :not(noscript)").forEach(function (n) {
      n.remove();
    });
    this.canvas.appendChild(frag);
  };

  Builder.prototype.terminalNode = function (text, kind) {
    var wrap = el("div", "mf-wfb__node mf-wfb__node--terminal mf-wfb__node--" + kind);
    wrap.appendChild(el("span", "mf-wfb__terminal", text));
    return wrap;
  };

  Builder.prototype.insertPoint = function (afterId) {
    var self = this;
    var wrap = el("div", "mf-wfb__connector");
    var btn = el("button", "mf-wfb__plus");
    btn.type = "button";
    btn.setAttribute("aria-label", this.i18n.insert_here || "Insert a step here");
    btn.title = this.i18n.insert_here || "";
    btn.appendChild(el("span", null, "+"));
    if (this.draft && this.draft.insertAfter === afterId) btn.classList.add("is-active");
    btn.addEventListener("click", function () {
      self.startDraft(afterId);
    });
    wrap.appendChild(btn);
    return wrap;
  };

  Builder.prototype.stepCard = function (step) {
    var self = this;
    var wrap = el("div", "mf-wfb__node");
    var card = el("button", "mf-wfb__card");
    card.type = "button";
    card.setAttribute("data-step-id", step.id);
    var missing = !step.assignees.length;
    if (missing) card.classList.add("mf-wfb__card--warn");
    if (this.selectedId === step.id) card.classList.add("is-selected");

    card.appendChild(el("span", "mf-wfb__card-title", step.label));
    if (missing) {
      var warn = el("span", "mf-wfb__card-sub mf-wfb__card-sub--warn");
      warn.appendChild(el("span", "mf-wfb__warn-icon", "⚠"));
      warn.appendChild(document.createTextNode(" " + (this.i18n.no_assignee || "")));
      card.appendChild(warn);
    } else {
      var names = step.assignees
        .map(function (a) {
          return a.text.split(" — ").pop();
        })
        .slice(0, 3)
        .join("، ");
      var more = step.assignees.length > 3 ? " +" + (step.assignees.length - 3) : "";
      card.appendChild(el("span", "mf-wfb__card-sub", names + more));
    }
    if (step.description) {
      card.appendChild(el("span", "mf-wfb__card-desc", step.description));
    }
    card.addEventListener("click", function () {
      self.select(step.id);
    });
    wrap.appendChild(card);
    return wrap;
  };

  Builder.prototype.draftCard = function () {
    var wrap = el("div", "mf-wfb__node");
    var card = el("div", "mf-wfb__card mf-wfb__card--warn is-selected mf-wfb__card--draft");
    card.setAttribute("data-step-id", NEW_ID);
    var label = (this.inputs.label.value || "").trim() || this.i18n.new_step;
    card.appendChild(el("span", "mf-wfb__card-title", label));
    var sub = el("span", "mf-wfb__card-sub mf-wfb__card-sub--warn");
    sub.appendChild(el("span", "mf-wfb__warn-icon", "⚠"));
    sub.appendChild(document.createTextNode(" " + (this.i18n.unsaved || "")));
    card.appendChild(sub);
    wrap.appendChild(card);
    return wrap;
  };

  Builder.prototype.syncDraftLabel = function () {
    if (this.selectedId !== NEW_ID) return;
    var card = this.canvas.querySelector('[data-step-id="' + NEW_ID + '"] .mf-wfb__card-title');
    if (card) card.textContent = (this.inputs.label.value || "").trim() || this.i18n.new_step;
  };

  Builder.prototype.renderCheck = function () {
    var self = this;
    var issues = [];
    var steps = this.state.steps;
    if (!steps.length) issues.push(this.i18n.check_no_steps);
    var seen = {};
    steps.forEach(function (s) {
      if (!s.assignees.length) issues.push(fmt(self.i18n.check_no_assignee, { label: s.label }));
      var key = s.label.trim().toLowerCase();
      if (seen[key] === 1) issues.push(fmt(self.i18n.check_duplicate, { label: s.label }));
      seen[key] = (seen[key] || 0) + 1;
    });
    if (this.draft) issues.push(this.i18n.check_unsaved);

    this.checkList.innerHTML = "";
    this.checkBox.classList.toggle("mf-wfb__check--ok", issues.length === 0);
    this.checkBox.classList.toggle("mf-wfb__check--warn", issues.length > 0);
    if (!issues.length) {
      var ok = el("li", "mf-wfb__check-item mf-wfb__check-item--ok");
      ok.appendChild(el("span", "mf-wfb__check-icon", "✓"));
      ok.appendChild(document.createTextNode(" " + this.i18n.check_ok));
      this.checkList.appendChild(ok);
      return;
    }
    issues.forEach(function (text) {
      var li = el("li", "mf-wfb__check-item");
      li.appendChild(el("span", "mf-wfb__check-icon", "⚠"));
      li.appendChild(document.createTextNode(" " + text));
      self.checkList.appendChild(li);
    });
  };

  // ---------- selection & panel ----------

  Builder.prototype.startDraft = function (afterId) {
    if (!this.confirmDiscard()) return;
    this.draft = { insertAfter: afterId };
    this.selectedId = NEW_ID;
    this.dirty = false;
    this.fillPanel({ id: null, label: "", description: "", assignees: [], submissions_count: 0 });
    this.render();
    this.inputs.label.focus();
  };

  Builder.prototype.select = function (id) {
    if (this.selectedId === id) return;
    if (!this.confirmDiscard()) return;
    var step = this.stepById(id);
    if (!step) return;
    this.draft = null;
    this.selectedId = id;
    this.dirty = false;
    this.fillPanel(step);
    this.render();
  };

  Builder.prototype.deselect = function (ask) {
    if (ask && !this.confirmDiscard()) return;
    this.draft = null;
    this.selectedId = null;
    this.dirty = false;
    this.panelBody.hidden = true;
    this.panelEmpty.hidden = false;
    this.render();
  };

  Builder.prototype.fillPanel = function (step) {
    this.clearErrors();
    this.setStatus("");
    this.panelEmpty.hidden = true;
    this.panelBody.hidden = false;
    this.inputs.label.value = step.label || "";
    this.inputs.description.value = step.description || "";
    if (this.ts) {
      this.ts.clear(true);
      this.ts.clearOptions();
      step.assignees.forEach(function (a) {
        this.ts.addOption({ id: String(a.id), text: a.text });
      }, this);
      this.ts.setValue(
        step.assignees.map(function (a) {
          return String(a.id);
        }),
        true
      );
    } else {
      this.inputs.assignees.innerHTML = "";
      step.assignees.forEach(function (a) {
        var o = document.createElement("option");
        o.value = a.id;
        o.textContent = a.text;
        o.selected = true;
        this.inputs.assignees.appendChild(o);
      }, this);
    }
    var isNew = !step.id;
    this.secondary.hidden = isNew;
    var idx = isNew ? -1 : this.state.steps.indexOf(this.stepById(step.id));
    Array.prototype.forEach.call(this.moveBtns, function (btn) {
      var dir = btn.getAttribute("data-wfb-move");
      btn.disabled = dir === "up" ? idx <= 0 : idx >= this.state.steps.length - 1;
    }, this);
    if (step.submissions_count > 0) {
      this.submissionsNote.hidden = false;
      this.submissionsNote.textContent = fmt(this.i18n.submissions_here, { count: step.submissions_count });
    } else {
      this.submissionsNote.hidden = true;
    }
    this.updateAssigneeHint();
  };

  Builder.prototype.updateAssigneeHint = function () {
    this.hintAssignees.hidden = this.assigneeIds().length > 0;
  };

  Builder.prototype.clearErrors = function () {
    Object.keys(this.errors).forEach(function (k) {
      this.errors[k].hidden = true;
      this.errors[k].textContent = "";
    }, this);
  };

  Builder.prototype.showError = function (field, message) {
    var target = this.errors[field] || this.errors.general;
    target.textContent = message;
    target.hidden = false;
  };

  Builder.prototype.setStatus = function (text) {
    this.status.textContent = text || "";
  };

  Builder.prototype.setBusy = function (busy) {
    this.busy = busy;
    this.saveBtn.disabled = busy;
    this.deleteBtn.disabled = busy;
    this.root.classList.toggle("is-busy", busy);
  };

  // ---------- server calls ----------

  Builder.prototype.request = function (url, method, body) {
    return window.MF.request(url, { method: method, body: body, root: this.root }).then(function (res) {
      var data = res.data || {};
      data._status = res.status;
      if (res.error === window.MF.NETWORK_ERROR) throw new Error("network");
      return data;
    });
  };

  Builder.prototype.applyState = function (state) {
    if (state) this.state = state;
  };

  Builder.prototype.save = function () {
    if (this.busy) return;
    this.clearErrors();
    var label = (this.inputs.label.value || "").trim();
    if (!label) {
      this.showError("label", this.i18n.err_label_required);
      this.inputs.label.focus();
      return;
    }
    var payload = {
      id: this.selectedId === NEW_ID ? null : this.selectedId,
      label: label,
      description: (this.inputs.description.value || "").trim(),
      assignee_ids: this.assigneeIds(),
      insert_after: this.draft ? this.draft.insertAfter : null,
    };
    var self = this;
    this.setBusy(true);
    this.request(this.urls.save, "POST", payload)
      .then(function (data) {
        if (!data.ok) {
          self.showError(data.field || "general", data.error || self.i18n.err_network);
          return;
        }
        self.applyState(data.state);
        self.draft = null;
        self.dirty = false;
        self.selectedId = data.step_id;
        var step = self.stepById(data.step_id);
        if (step) self.fillPanel(step);
        self.render();
        self.setStatus(self.i18n.saved);
      })
      .catch(function () {
        self.showError("general", self.i18n.err_network);
      })
      .finally(function () {
        self.setBusy(false);
      });
  };

  Builder.prototype.remove = function () {
    if (this.busy || this.selectedId === NEW_ID || this.selectedId == null) return;
    if (!window.confirm(this.i18n.confirm_delete)) return;
    var self = this;
    var step = this.stepById(this.selectedId);
    var url = step && step.delete_url;
    if (!url) return;
    this.clearErrors();
    this.setBusy(true);
    this.request(url, "POST")
      .then(function (data) {
        self.applyState(data.state);
        if (!data.ok) {
          self.showError("general", data.error || self.i18n.err_network);
          self.render();
          return;
        }
        self.dirty = false;
        self.deselect(false);
        self.setStatus(self.i18n.deleted);
      })
      .catch(function () {
        self.showError("general", self.i18n.err_network);
      })
      .finally(function () {
        self.setBusy(false);
      });
  };

  Builder.prototype.move = function (direction) {
    if (this.busy || this.selectedId === NEW_ID || this.selectedId == null) return;
    var ids = this.state.steps.map(function (s) {
      return s.id;
    });
    var idx = ids.indexOf(this.selectedId);
    var to = direction === "up" ? idx - 1 : idx + 1;
    if (idx < 0 || to < 0 || to >= ids.length) return;
    ids.splice(to, 0, ids.splice(idx, 1)[0]);
    var self = this;
    this.setBusy(true);
    this.request(this.urls.reorder, "POST", { order: ids })
      .then(function () {
        return self.request(self.urls.state, "GET");
      })
      .then(function (data) {
        self.applyState(data.state);
        var step = self.stepById(self.selectedId);
        var wasDirty = self.dirty;
        if (step && !wasDirty) self.fillPanel(step);
        else if (step) self.refreshMoveButtons();
        self.render();
      })
      .catch(function () {
        self.showError("general", self.i18n.err_network);
      })
      .finally(function () {
        self.setBusy(false);
      });
  };

  Builder.prototype.refreshMoveButtons = function () {
    var idx = this.state.steps.indexOf(this.stepById(this.selectedId));
    Array.prototype.forEach.call(this.moveBtns, function (btn) {
      var dir = btn.getAttribute("data-wfb-move");
      btn.disabled = dir === "up" ? idx <= 0 : idx >= this.state.steps.length - 1;
    }, this);
  };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-wfb]").forEach(function (root) {
      new Builder(root);
    });
  });
})();
