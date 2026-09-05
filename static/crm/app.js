// ===== Webordo SRM — клиентский JS =====
(function () {
  "use strict";

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  // ---- мобильное меню ----
  document.addEventListener("click", function (e) {
    if (e.target.closest(".burger")) document.body.classList.toggle("nav-open");
    else if (e.target.classList.contains("scrim")) document.body.classList.remove("nav-open");
  });

  // ---- авто-скрытие флеш-сообщений ----
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity .4s"; el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 4500);
  });

  // ---- список клиентов: открытие строки + режим выбора + массовые действия ----
  const anyClientBox = document.querySelector("[name=client_ids]");
  const selectToggle = document.getElementById("selectToggle");
  if (anyClientBox || selectToggle) {
    const boxes = () => document.querySelectorAll("[name=client_ids]");
    const bar = document.querySelector("[data-bulkbar]");
    const counter = document.querySelector("[data-bulk-count]");

    function markRow(box) {
      const row = box.closest("[data-select-row]");
      if (row) row.classList.toggle("row-selected", box.checked);
    }
    function refresh() {
      const n = document.querySelectorAll("[name=client_ids]:checked").length;
      const selecting = document.body.classList.contains("selecting");
      if (bar) {
        bar.hidden = !selecting;
        bar.classList.toggle("bulkbar-empty", n === 0);
      }
      if (counter) counter.textContent = n;
    }
    document.addEventListener("change", function (e) {
      if (e.target.name === "client_ids") { markRow(e.target); refresh(); }
    });

    if (selectToggle) {
      selectToggle.addEventListener("click", function () {
        const on = document.body.classList.toggle("selecting");
        selectToggle.textContent = on ? "Готово" : "Выбрать";
        selectToggle.classList.toggle("btn", true);
        if (!on) {
          boxes().forEach((b) => { b.checked = false; markRow(b); });
        }
        refresh();
      });
    }
    const selectAllBtn = document.querySelector("[data-select-all-btn]");
    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", function () {
        const allChecked = Array.from(boxes()).every((b) => b.checked);
        boxes().forEach((b) => { b.checked = !allChecked; markRow(b); });
        refresh();
      });
    }
    // «Выбрать всё» одной кнопкой — сразу включает режим и отмечает всё видимое
    const selectAllNow = document.querySelector("[data-select-all-now]");
    if (selectAllNow) {
      selectAllNow.addEventListener("click", function () {
        document.body.classList.add("selecting");
        if (selectToggle) selectToggle.textContent = "Готово";
        boxes().forEach((b) => { b.checked = true; markRow(b); });
        refresh();
      });
    }

    // Клик по строке: в обычном режиме — открыть карточку; в режиме выбора — отметить.
    document.querySelectorAll("[data-select-row]").forEach(function (row) {
      row.addEventListener("click", function (e) {
        if (e.target.closest("a,button,select,textarea,label,input")) return;
        if (document.body.classList.contains("selecting")) {
          const box = row.querySelector("[name=client_ids]");
          if (box) { box.checked = !box.checked; markRow(box); refresh(); }
        } else if (row.dataset.href) {
          window.location = row.dataset.href;
        }
      });
    });

    boxes().forEach(markRow);
    refresh();
  }

  // ---- закрывать выпадающее меню "⋯" по клику вне ----
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  // ---- копирование телефона одним кликом (как ячейка Excel) ----
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // HTTP без TLS — Clipboard API недоступен, откат на execCommand
    return new Promise(function (resolve, reject) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand("copy") ? resolve() : reject();
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      const original = btn.textContent;
      const feedback = btn.classList.contains("kcopy") ? "✓" : "Скопировано";
      copyText(btn.dataset.copy).then(function () {
        btn.classList.add("copied");
        btn.textContent = feedback;
        setTimeout(function () {
          btn.classList.remove("copied");
          btn.textContent = original;
        }, 1000);
      });
    });
  });

  // ---- клик по строке-ссылке (таблица задач) ----
  document.querySelectorAll("[data-row-link]").forEach(function (row) {
    row.addEventListener("click", function (e) {
      if (e.target.closest("a,button,form,input,select,textarea,label,[contenteditable]")) return;
      window.location = row.dataset.rowLink;
    });
  });

  // ---- Канбан drag & drop ----
  const board = document.querySelector("[data-kanban]");
  if (board) {
    let dragged = null;
    board.addEventListener("dragstart", function (e) {
      const card = e.target.closest(".kcard");
      if (!card) return;
      if (document.body.classList.contains("selecting")) { e.preventDefault(); return; }
      if (e.target.closest("[contenteditable],input,button,a,select,textarea")) { e.preventDefault(); return; }
      dragged = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    board.addEventListener("dragend", function () {
      if (dragged) dragged.classList.remove("dragging");
      document.querySelectorAll(".kcol-b").forEach((c) => c.classList.remove("drop-hint"));
      dragged = null;
    });
    board.querySelectorAll(".kcol-b").forEach(function (zone) {
      zone.addEventListener("dragover", function (e) {
        e.preventDefault();
        zone.classList.add("drop-hint");
      });
      zone.addEventListener("dragleave", () => zone.classList.remove("drop-hint"));
      zone.addEventListener("drop", function (e) {
        e.preventDefault();
        zone.classList.remove("drop-hint");
        if (!dragged) return;
        const card = dragged;
        const clientId = card.dataset.clientId;
        const stageId = zone.dataset.stageId;
        if (card.parentElement === zone) return;

        function commit(reason) {
          zone.appendChild(card);
          updateCounts();
          fetch(board.dataset.moveUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
            body: JSON.stringify({ client_id: clientId, stage_id: stageId, lost_reason: reason || "" }),
          })
            .then((r) => r.json())
            .then((d) => { if (!d.ok) location.reload(); })
            .catch(() => location.reload());
        }
        if (zone.dataset.lost === "1" && window.askLostReason) {
          window.askLostReason(function (reason) {
            if (reason !== null) commit(reason); // отмена — карточку никуда не переносим
          });
        } else {
          commit("");
        }
      });
    });
    function updateCounts() {
      board.querySelectorAll(".kcol").forEach(function (col) {
        const c = col.querySelector(".count");
        if (c) c.textContent = col.querySelectorAll(".kcard").length;
      });
    }

    // ---- быстрое добавление заявки/сделки прямо в колонке ----
    document.querySelectorAll("[data-kadd]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const col = btn.closest(".kcol");
        const form = col.querySelector("[data-kquick]");
        form.hidden = !form.hidden;
        if (!form.hidden) form.querySelector('[name="full_name"]').focus();
      });
    });
    document.querySelectorAll("[data-kquick-cancel]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        btn.closest("[data-kquick]").hidden = true;
      });
    });
    document.querySelectorAll("[data-kquick]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const fd = new FormData(form);
        fd.set("stage", form.dataset.stageId);
        fetch(board.dataset.quickUrl, {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
          body: fd,
        })
          .then((r) => r.json())
          .then((d) => {
            if (d.ok) location.reload();
          });
      });
    });

    // ---- редактирование прямо на карточке: клик → курсор → ввод (как в Excel) ----
    board.querySelectorAll(".kf").forEach(function (el) {
      let before = el.textContent;
      el.addEventListener("focus", function () { before = el.textContent; });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); el.blur(); }
        if (e.key === "Escape") { el.textContent = before; el.blur(); }
      });
      el.addEventListener("blur", function () {
        const val = el.textContent.trim();
        if (val === before.trim()) return;
        el.classList.add("saving");
        fetch(board.dataset.inlineUrl.replace("0", el.dataset.clientId), {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
          body: "field=" + encodeURIComponent(el.dataset.field) + "&value=" + encodeURIComponent(val),
        })
          .then((r) => r.json())
          .then((d) => {
            el.classList.remove("saving");
            if (!d.ok) { el.textContent = before; alert(d.error || "Не удалось сохранить"); }
            else before = val;
          })
          .catch(() => { el.classList.remove("saving"); el.textContent = before; });
      });
    });
  }

  // ---- быстрая смена статуса (AJAX) ----
  document.querySelectorAll("[data-ajax-form]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
        body: new FormData(form),
      })
        .then((r) => r.json())
        .then(() => {
          const row = form.closest("[data-row]");
          if (row) row.classList.add("done-row");
          location.reload();
        });
    });
  });

  // ---- быстрая смена стадии прямо в списке/канбане/карточке ----
  function submitStageChange(sel, opt, reason) {
    const body = new URLSearchParams({ stage: sel.value });
    if (reason) body.set("lost_reason", reason);
    sel.classList.add("saving");
    sel.classList.remove("saved");
    fetch(sel.dataset.url, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => {
        sel.classList.remove("saving");
        sel.classList.add("saved");
        if (d.color) sel.style.background = d.color;
        else if (opt && opt.dataset.color) sel.style.background = opt.dataset.color;
        sel.dataset.prev = sel.value;
        setTimeout(() => sel.classList.remove("saved"), 1200);
      })
      .catch(() => {
        sel.classList.remove("saving");
        sel.value = sel.dataset.prev; // откат
        alert("Не удалось сменить стадию");
      });
  }

  // модалка причины проигрыша — общая для Списка/Канбана/карточки клиента.
  // window.askLostReason(cb) вызывает cb(reasonString) при сохранении/пропуске,
  // либо cb(null), если отменили — вызывающий код сам решает, что делать с отменой.
  const lostModal = document.getElementById("lostModal");
  window.askLostReason = function (cb) {
    if (!lostModal) { cb(""); return; }
    const textEl = document.getElementById("lostReasonText");
    textEl.value = "";
    lostModal.querySelectorAll("[data-reason]").forEach((c) => c.classList.remove("active"));
    lostModal.hidden = false;
    setTimeout(() => textEl.focus(), 30);

    function done(reason) {
      lostModal.hidden = true;
      cleanup();
      cb(reason);
    }
    function onChip(e) {
      textEl.value = e.currentTarget.dataset.reason;
      lostModal.querySelectorAll("[data-reason]").forEach((c) => c.classList.remove("active"));
      e.currentTarget.classList.add("active");
    }
    function onConfirm() { done(textEl.value.trim()); }
    function onSkip() { done(""); }
    function onCancel() { done(null); }
    function onBackdrop(e) { if (e.target === lostModal) onCancel(); }
    function onKey(e) { if (e.key === "Escape") onCancel(); }
    const chips = Array.from(lostModal.querySelectorAll("[data-reason]"));
    const cancelBtns = Array.from(lostModal.querySelectorAll("[data-lost-cancel]"));
    const confirmBtn = document.getElementById("lostConfirm");
    const skipBtn = document.getElementById("lostSkip");
    function cleanup() {
      chips.forEach((c) => c.removeEventListener("click", onChip));
      cancelBtns.forEach((b) => b.removeEventListener("click", onCancel));
      confirmBtn.removeEventListener("click", onConfirm);
      skipBtn.removeEventListener("click", onSkip);
      lostModal.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKey);
    }
    chips.forEach((c) => c.addEventListener("click", onChip));
    cancelBtns.forEach((b) => b.addEventListener("click", onCancel));
    confirmBtn.addEventListener("click", onConfirm);
    skipBtn.addEventListener("click", onSkip);
    lostModal.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKey);
  };

  document.querySelectorAll("[data-stage-select]").forEach(function (sel) {
    sel.dataset.prev = sel.value;
    sel.addEventListener("click", function (e) {
      e.stopPropagation(); // не выделять строку
    });
    sel.addEventListener("change", function () {
      const opt = sel.selectedOptions[0];
      if (opt && opt.dataset.lost === "1") {
        window.askLostReason(function (reason) {
          if (reason === null) { sel.value = sel.dataset.prev; return; }
          submitStageChange(sel, opt, reason);
        });
        return;
      }
      submitStageChange(sel, opt, "");
    });
  });

  // ---- поповер со всеми активными задачами клиента (hover) ----
  (function () {
    let hideTimer = null;
    let openPop = null;

    function place(pop, anchor) {
      const r = anchor.getBoundingClientRect();
      pop.classList.add("show");
      const pr = pop.getBoundingClientRect();
      let top = r.bottom + 6;
      if (top + pr.height > window.innerHeight - 8) top = Math.max(8, r.top - pr.height - 6);
      let left = r.left;
      if (left + pr.width > window.innerWidth - 8) left = window.innerWidth - pr.width - 8;
      pop.style.top = top + "px";
      pop.style.left = Math.max(8, left) + "px";
    }
    function show(wrap) {
      clearTimeout(hideTimer);
      const pop = wrap.querySelector("[data-task-pop]");
      if (!pop || pop === openPop) return;
      if (openPop) openPop.classList.remove("show");
      openPop = pop;
      place(pop, wrap);
    }
    function scheduleHide() {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(function () {
        if (openPop) openPop.classList.remove("show");
        openPop = null;
      }, 160);
    }

    document.querySelectorAll("[data-task-hover]").forEach(function (wrap) {
      const pop = wrap.querySelector("[data-task-pop]");
      if (!pop) return;
      wrap.addEventListener("mouseenter", () => show(wrap));
      wrap.addEventListener("mouseleave", scheduleHide);
      pop.addEventListener("mouseenter", () => clearTimeout(hideTimer));
      pop.addEventListener("mouseleave", scheduleHide);
    });
    window.addEventListener("scroll", function () {
      if (openPop) { openPop.classList.remove("show"); openPop = null; }
    }, true);
  })();

  // ---- модалка "добавить задачу" из списка клиентов ----
  const taskModal = document.getElementById("taskModal");
  if (taskModal) {
    const form = document.getElementById("taskModalForm");
    const errBox = taskModal.querySelector("[data-modal-error]");
    const clientLabel = taskModal.querySelector("[data-modal-client]");
    const titleEl = taskModal.querySelector("#taskModalTitle");
    let targetCell = null;
    let bulkIds = null; // массив id при добавлении задачи нескольким

    function prepModal(url, label, title) {
      form.action = url;
      clientLabel.textContent = label;
      if (titleEl && title) titleEl.textContent = title;
      form.reset();
      errBox.hidden = true;
      taskModal.hidden = false;
      const d = form.querySelector("#tm_date");
      if (d && !d.value) d.value = new Date().toISOString().slice(0, 10);
      setTimeout(() => form.querySelector("#tm_title").focus(), 30);
    }
    function openModal(btn) {
      bulkIds = null;
      targetCell = btn.closest("[data-task-cell]");
      prepModal(btn.dataset.url, "Клиент: " + btn.dataset.client, "Новая задача");
    }
    function openBulkModal(btn) {
      const ids = Array.from(
        document.querySelectorAll("[name=client_ids]:checked")
      ).map((b) => b.value);
      if (!ids.length) {
        alert("Сначала выберите клиентов в списке");
        return;
      }
      bulkIds = ids;
      targetCell = null;
      prepModal(
        btn.dataset.url,
        "Задача будет добавлена " + ids.length + " клиент(ам)",
        "Задача для " + ids.length + " клиентов"
      );
    }
    function closeModal() {
      taskModal.hidden = true;
      targetCell = null;
      bulkIds = null;
    }

    document.querySelectorAll("[data-add-task]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        openModal(btn);
      });
    });
    document.querySelectorAll("[data-bulk-task]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openBulkModal(btn);
      });
    });
    taskModal.querySelectorAll("[data-modal-close]").forEach((b) =>
      b.addEventListener("click", closeModal)
    );
    taskModal.addEventListener("click", (e) => {
      if (e.target === taskModal) closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !taskModal.hidden) closeModal();
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      errBox.hidden = true;
      const fd = new FormData(form);
      if (bulkIds) bulkIds.forEach((id) => fd.append("client_ids", id));
      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
        body: fd,
      })
        .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
          btn.disabled = false;
          if (!ok || !d.ok) {
            errBox.textContent = "Проверьте поля: заполните название задачи.";
            errBox.hidden = false;
            return;
          }
          closeModal();
          // перечитываем страницу — обновится чип и список задач в поповере
          location.reload();
        })
        .catch(() => {
          btn.disabled = false;
          errBox.textContent = "Не удалось создать задачу. Попробуйте ещё раз.";
          errBox.hidden = false;
        });
    });
  }

  // ---- компактный список задач (Apple Notes: галочка, правка текста и даты на месте) ----
  const tlist = document.querySelector(".tlist");
  if (tlist) {
    const inlineUrlTpl = tlist.dataset.inlineUrl; // /tasks/0/inline/

    // галочка "выполнено" — без перезагрузки страницы
    tlist.querySelectorAll("[data-tcheck-form]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const item = form.closest(".titem");
        const btn = form.querySelector(".tcheck2");
        const willBeDone = !btn.classList.contains("done");
        fetch(form.action, {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
          body: new FormData(form),
        })
          .then((r) => r.json())
          .then((d) => {
            if (!d.ok) return;
            btn.classList.toggle("done", willBeDone);
            item.classList.toggle("is-done", willBeDone);
            form.querySelector('[name="status"]').value = willBeDone ? "new" : "done";
          });
      });
    });

    // текст задачи — клик → курсор → правка
    tlist.querySelectorAll(".ttext").forEach(function (el) {
      let before = el.textContent;
      el.addEventListener("focus", function () { before = el.textContent; });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); el.blur(); }
        if (e.key === "Escape") { el.textContent = before; el.blur(); }
      });
      el.addEventListener("blur", function () {
        const val = el.textContent.trim();
        if (!val) { el.textContent = before; return; }
        if (val === before.trim()) return;
        fetch(inlineUrlTpl.replace("0", el.dataset.taskId), {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
          body: "field=title&value=" + encodeURIComponent(val),
        })
          .then((r) => r.json())
          .then((d) => { if (d.ok) before = val; else el.textContent = before; })
          .catch(() => { el.textContent = before; });
      });
    });

    // дата задачи — нативный календарь, сохраняется сразу при выборе
    tlist.querySelectorAll(".tdate").forEach(function (el) {
      el.addEventListener("change", function () {
        const item = el.closest(".titem");
        fetch(inlineUrlTpl.replace("0", el.dataset.taskId), {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
          body: "field=due_date&value=" + encodeURIComponent(el.value),
        })
          .then((r) => r.json())
          .then((d) => {
            if (!d.ok) return;
            item.classList.remove("tone-red", "tone-amber", "tone-green");
            item.classList.add("tone-" + d.due_tone);
          });
      });
    });
  }

  // ---- живой предпросмотр текста сообщения ----
  const tplSel = document.querySelector("[data-template-source]");
  const textArea = document.querySelector("[data-message-text]");
  if (tplSel && textArea) {
    tplSel.addEventListener("change", function () {
      const opt = tplSel.selectedOptions[0];
      if (opt && opt.dataset.rendered) textArea.value = opt.dataset.rendered;
    });
  }
})();
