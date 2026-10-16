/* Финсовет → «Финансы»: «План выплат» и «Ожидаемые средства» — таблицы «как в Excel».
 *
 * Ячейка (.xl-cell) — поле ввода, но ведёт себя как ячейка Excel:
 *   - режим «выбор» (по умолчанию): текст выделен целиком, стрелки ходят по ячейкам,
 *     Shift+стрелки / Shift+клик выделяют диапазон, ⌘/Ctrl+C копирует диапазон,
 *     ⌘/Ctrl+V вставляет таблицу (в т.ч. из Excel), Delete очищает диапазон;
 *   - режим «правка» (начали печатать, двойной клик или F2): ←/→ двигают курсор в тексте.
 * Enter — вниз, Shift+Enter — вверх, Tab — вправо, Esc — отменить правку.
 * Ячейка сохраняется сама при уходе из неё; строка «Итого» пересчитывается на лету.
 */
(function () {
  "use strict";

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(data || {}).toString(),
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok && d.ok !== false, d: d }; });
    });
  }

  // «1 845 000» ⇄ 1845000 (копейки — только если они есть)
  function parseMoney(text) {
    const n = parseFloat(String(text || "").replace(/[\s ]/g, "").replace("−", "-").replace(",", "."));
    return isNaN(n) ? 0 : n;
  }
  function formatMoney(n) {
    const neg = n < 0;
    const parts = Math.abs(n).toFixed(2).split(".");
    return (neg ? "−" : "") + parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ") + (parts[1] !== "00" ? "," + parts[1] : "");
  }

  // ------------------------------------------------------------------ //
  //  Одна таблица
  // ------------------------------------------------------------------ //
  function initTable(table) {
    const box = table.closest(".fin-box");
    const addBtn = table.querySelector("[data-fin-add]");
    const body = table.tBodies[0];
    let anchor = null;   // {r, c} — активная ячейка (где фокус)
    let cursor = null;   // {r, c} — второй угол выделенного диапазона
    let mode = "nav";    // "nav" | "edit"

    // Сетка — по видимым колонкам (td.xl-c), включая вычисляемый «Остаток»:
    // так вставка из Excel ложится в те же колонки, что и на экране.
    function rows() { return Array.from(body.rows); }
    function colsOf(row) { return Array.from(row.querySelectorAll("td.xl-c")); }
    function ncols() { const r = body.rows[0]; return r ? colsOf(r).length : 0; }
    function tdAt(r, c) { const row = body.rows[r]; return row ? colsOf(row)[c] || null : null; }
    function inputAt(r, c) { const td = tdAt(r, c); return td ? td.querySelector(".xl-cell") : null; }
    function posOf(input) {
      const row = input.closest("tr");
      return { r: rows().indexOf(row), c: colsOf(row).indexOf(input.closest("td")) };
    }

    function renumber() {
      rows().forEach(function (row, i) { row.querySelector(".xl-num").textContent = i + 1; });
      const cnt = box.querySelector(".fin-box-h small");
      if (cnt) cnt.textContent = body.rows.length + " строк";
    }

    function recalcTotals() {
      table.querySelectorAll("[data-sum]").forEach(function (cell) {
        const key = cell.dataset.sum;
        let sum = 0;
        body.querySelectorAll('[data-out="' + key + '"]').forEach(function (el) {
          sum += parseMoney(el.tagName === "INPUT" ? (el.dataset.saved !== undefined ? el.dataset.saved : el.value) : el.textContent);
        });
        cell.textContent = formatMoney(sum);
      });
    }

    function applyState(row, d) {
      ["total", "paid", "remaining", "amount"].forEach(function (k) {
        if (d[k] === undefined) return;
        const el = row.querySelector('[data-out="' + k + '"]');
        if (!el) return;
        if (el.tagName === "INPUT") {
          el.dataset.saved = d[k];
          if (document.activeElement !== el || mode === "nav") el.value = d[k];
        } else {
          el.textContent = d[k];
        }
      });
      if (d.done !== undefined) row.classList.toggle("is-done", d.done);
      recalcTotals();
    }

    function saveCell(input) {
      if (input.dataset.saved === undefined) input.dataset.saved = input.defaultValue;
      if (input.value === input.dataset.saved) return Promise.resolve();
      const row = input.closest("tr");
      input.classList.add("saving");
      return post(row.dataset.updateUrl, { field: input.dataset.field, value: input.value })
        .then(function (res) {
          input.classList.remove("saving");
          if (!res.ok) {
            input.classList.add("xl-err");
            input.title = res.d.error || "Не удалось сохранить";
            return;
          }
          input.classList.remove("xl-err");
          input.dataset.saved = input.value;
          applyState(row, res.d);
          input.classList.add("saved");
          setTimeout(function () { input.classList.remove("saved"); }, 700);
        })
        .catch(function () { input.classList.remove("saving"); input.classList.add("xl-err"); });
    }

    // по очереди, чтобы ответы с итогами строки не перемешались
    function saveAll(cells) {
      return cells.reduce(function (chain, cell) {
        return chain.then(function () { return saveCell(cell); });
      }, Promise.resolve());
    }

    // ---- выделение диапазона ----
    function clearSel() {
      table.querySelectorAll(".xl-sel").forEach(function (td) { td.classList.remove("xl-sel"); });
    }
    function rect() {
      if (!anchor) return null;
      const b = cursor || anchor;
      return {
        r1: Math.min(anchor.r, b.r), r2: Math.max(anchor.r, b.r),
        c1: Math.min(anchor.c, b.c), c2: Math.max(anchor.c, b.c),
      };
    }
    function paintSel() {
      clearSel();
      const q = rect();
      if (!q || (q.r1 === q.r2 && q.c1 === q.c2)) return;
      for (let r = q.r1; r <= q.r2; r++) {
        for (let c = q.c1; c <= q.c2; c++) {
          const td = tdAt(r, c);
          if (td) td.classList.add("xl-sel");
        }
      }
    }
    function isRange() { const q = rect(); return q && (q.r1 !== q.r2 || q.c1 !== q.c2); }

    // ---- перемещение ----
    function focusCell(r, c, dc) {
      // вычисляемые колонки («Остаток») пропускаем по направлению движения
      const n = ncols();
      while (c >= 0 && c < n && !inputAt(r, c)) c += dc || 1;
      const input = inputAt(r, c);
      if (!input) return false;
      input.focus();
      return true;
    }
    function move(dr, dc) {
      if (!anchor) return;
      const r = Math.max(0, Math.min(body.rows.length - 1, anchor.r + dr));
      const c = Math.max(0, Math.min(ncols() - 1, anchor.c + dc));
      focusCell(r, c, dc);
    }
    function extend(dr, dc) {
      if (!anchor) return;
      const b = cursor || anchor;
      cursor = {
        r: Math.max(0, Math.min(body.rows.length - 1, b.r + dr)),
        c: Math.max(0, Math.min(ncols() - 1, b.c + dc)),
      };
      paintSel();
      const td = tdAt(cursor.r, cursor.c);
      if (td) td.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    // ---- события ----
    table.addEventListener("focusin", function (e) {
      const input = e.target;
      if (!input.classList.contains("xl-cell")) return;
      if (input.dataset.saved === undefined) input.dataset.saved = input.value;
      anchor = posOf(input);
      cursor = null;
      mode = "nav";
      clearSel();
      input.select();
    });

    table.addEventListener("focusout", function (e) {
      if (e.target.classList.contains("xl-cell")) saveCell(e.target);
    });

    table.addEventListener("input", function (e) {
      if (e.target.classList.contains("xl-cell")) {
        mode = "edit";
        if (isRange()) { cursor = null; clearSel(); }
      }
    });

    table.addEventListener("dblclick", function (e) {
      if (e.target.classList.contains("xl-cell")) mode = "edit";
    });

    // клик внутри уже активной ячейки — оставить курсор там, куда кликнули (правка)
    table.addEventListener("mouseup", function (e) {
      const input = e.target;
      if (!input.classList || !input.classList.contains("xl-cell")) return;
      if (input.dataset.justFocused) { delete input.dataset.justFocused; input.select(); }
    });

    table.addEventListener("mousedown", function (e) {
      const input = e.target.closest(".xl-cell");
      const td = e.target.closest("td.xl-c");
      if (!td || !body.contains(td)) return;
      if (e.shiftKey && anchor) {
        // Shift+клик — выделить диапазон от активной ячейки до этой
        e.preventDefault();
        cursor = { r: rows().indexOf(td.closest("tr")), c: colsOf(td.closest("tr")).indexOf(td) };
        paintSel();
        return;
      }
      if (!input) return;
      if (document.activeElement !== input) input.dataset.justFocused = "1";
      else mode = "edit"; // второй клик по активной ячейке — правка текста с курсором
    });

    table.addEventListener("keydown", function (e) {
      const input = e.target;
      if (!input.classList.contains("xl-cell")) return;
      const mod = e.metaKey || e.ctrlKey;

      if (e.key === "Escape") {
        input.value = input.dataset.saved !== undefined ? input.dataset.saved : input.defaultValue;
        mode = "nav"; cursor = null; clearSel(); input.select();
        e.preventDefault();
        return;
      }
      if (e.key === "F2") { mode = "edit"; const l = input.value.length; input.setSelectionRange(l, l); e.preventDefault(); return; }

      const arrows = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
      if (arrows[e.key]) {
        const d = arrows[e.key];
        if (e.shiftKey && !mod) {
          // в режиме правки Shift+←/→ — выделение текста внутри ячейки, как в Excel
          if (mode === "edit" && d[1] !== 0) return;
          e.preventDefault();
          extend(d[0], d[1]);
          return;
        }
        if (mode === "edit" && d[1] !== 0) return; // ←/→ двигают курсор в тексте
        e.preventDefault();
        move(d[0], d[1]);
        return;
      }

      if (e.key === "Enter") { e.preventDefault(); move(e.shiftKey ? -1 : 1, 0); return; }
      if (e.key === "Tab") {
        // Tab — вправо по ячейкам, в конце строки — на начало следующей
        e.preventDefault();
        const n = ncols();
        let r = anchor.r, c = anchor.c + (e.shiftKey ? -1 : 1);
        while (true) {
          if (c >= n) { r += 1; c = 0; } else if (c < 0) { r -= 1; c = n - 1; }
          if (r < 0 || r >= body.rows.length) return;
          if (inputAt(r, c)) { inputAt(r, c).focus(); return; }
          c += e.shiftKey ? -1 : 1;
        }
      }

      if ((e.key === "Delete" || e.key === "Backspace") && mode === "nav" && isRange()) {
        e.preventDefault();
        const q = rect();
        const cells = [];
        for (let r = q.r1; r <= q.r2; r++) {
          for (let c = q.c1; c <= q.c2; c++) {
            const cell = inputAt(r, c);
            if (cell) { cell.value = ""; cells.push(cell); }
          }
        }
        saveAll(cells);
        return;
      }

      if (mod && e.code === "KeyC" && mode === "nav") {
        // ⌘/Ctrl+C — диапазон в буфер как таблица (табы/переводы строк), вставляется в Excel
        const q = rect();
        if (!q || !navigator.clipboard) return;
        e.preventDefault();
        const lines = [];
        for (let r = q.r1; r <= q.r2; r++) {
          const vals = [];
          for (let c = q.c1; c <= q.c2; c++) {
            const td = tdAt(r, c);
            const cell = td && td.querySelector(".xl-cell");
            vals.push(cell ? cell.value : (td ? td.textContent.trim() : ""));
          }
          lines.push(vals.join("\t"));
        }
        navigator.clipboard.writeText(lines.join("\n"));
        const q2 = rect();
        for (let r = q2.r1; r <= q2.r2; r++) for (let c = q2.c1; c <= q2.c2; c++) {
          const td = tdAt(r, c); if (td) { td.classList.add("xl-copied"); setTimeout(function () { td.classList.remove("xl-copied"); }, 600); }
        }
      }
    });

    // ⌘/Ctrl+V — таблица из буфера (Excel/Google Sheets) раскладывается по ячейкам
    // начиная с активной; не хватает строк — добавляются новые в конец.
    table.addEventListener("paste", function (e) {
      const input = e.target;
      if (!input.classList.contains("xl-cell")) return;
      const text = (e.clipboardData || window.clipboardData).getData("text");
      if (!text || (text.indexOf("\t") === -1 && text.indexOf("\n") === -1)) return; // одно значение — обычная вставка
      e.preventDefault();
      const grid = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map(function (l) { return l.split("\t"); });
      const start = posOf(input);
      const need = start.r + grid.length - body.rows.length;
      let chain = Promise.resolve();
      for (let i = 0; i < need; i++) chain = chain.then(function () { return addRow("end"); });
      chain.then(function () {
        const cells = [];
        grid.forEach(function (vals, i) {
          vals.forEach(function (v, j) {
            const cell = inputAt(start.r + i, start.c + j);
            if (cell) { cell.value = v.trim(); cells.push(cell); }
          });
        });
        saveAll(cells);
        anchor = start;
        cursor = { r: start.r + grid.length - 1, c: Math.min(ncols() - 1, start.c + grid[0].length - 1) };
        paintSel();
      });
    });

    // ---- строки ----
    function addRow(position) {
      return post(addBtn.dataset.finAdd, { position: position || "start" }).then(function (res) {
        if (!res.ok) return null;
        const tmp = document.createElement("tbody");
        tmp.innerHTML = res.d.html.trim();
        const row = tmp.querySelector("tr");
        if (position === "end") body.appendChild(row); else body.insertBefore(row, body.firstChild);
        renumber();
        return row;
      });
    }
    addBtn.addEventListener("click", function () {
      addBtn.disabled = true;
      addRow("start").then(function (row) {
        addBtn.disabled = false;
        if (!row) return;
        const first = row.querySelector('.xl-cell[data-field="name"], .xl-cell[data-field="source"]');
        if (first) first.focus();
      }).catch(function () { addBtn.disabled = false; });
    });

    table.addEventListener("click", function (e) {
      const del = e.target.closest("[data-fin-delete]");
      if (del) {
        const row = del.closest("tr");
        const label = (row.querySelector('[data-field="name"],[data-field="source"]') || {}).value || "строку";
        if (!confirm("Удалить «" + label + "»?")) return;
        post(row.dataset.deleteUrl).then(function (res) {
          if (!res.ok) return;
          row.remove();
          anchor = cursor = null;
          clearSel();
          renumber();
          recalcTotals();
        });
        return;
      }
      const hist = e.target.closest("[data-fin-history]");
      if (hist) History.open(hist.closest("tr"), applyState);
    });

    // клик вне таблицы — снять выделение диапазона
    document.addEventListener("mousedown", function (e) {
      if (!table.contains(e.target)) { cursor = null; clearSel(); }
    });

    renumber();
  }

  // ------------------------------------------------------------------ //
  //  История выплат одной строки: список с датами, «добавить» / «удалить выплату»
  // ------------------------------------------------------------------ //
  const History = (function () {
    const modal = document.getElementById("finHistoryModal");
    if (!modal) return { open: function () {} };
    const form = document.getElementById("finRecordForm");
    const list = modal.querySelector("[data-fh-list]");
    const err = modal.querySelector("[data-fh-error]");
    let row = null;
    let onState = null;

    function esc(t) { const d = document.createElement("div"); d.textContent = t == null ? "" : t; return d.innerHTML; }
    function render(d) {
      modal.querySelector("[data-fh-name]").textContent = d.name;
      modal.querySelector("[data-fh-total]").textContent = d.total;
      modal.querySelector("[data-fh-paid]").textContent = d.paid;
      modal.querySelector("[data-fh-remaining]").textContent = d.remaining;
      if (!d.records.length) { list.innerHTML = '<div class="muted">Выплат пока не было</div>'; return; }
      list.innerHTML = d.records.map(function (r) {
        return '<div class="fh-item"><span class="fh-date">' + esc(r.date) + "</span>" +
          '<span class="fh-amount">' + esc(r.amount) + "</span>" +
          '<span class="fh-note">' + esc(r.note) + ' <small class="muted">' + esc(r.author) + "</small></span>" +
          '<button type="button" class="xl-btn xl-del" data-fh-del="' + esc(r.delete_url) +
          '" title="Удалить выплату" aria-label="Удалить выплату">✕</button></div>';
      }).join("");
    }
    function load() {
      return fetch(row.dataset.historyUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (d) { render(d); if (onState) onState(row, d); });
    }
    function open(tr, applyState) {
      row = tr;
      onState = applyState;
      form.reset();
      form.date.value = new Date().toISOString().slice(0, 10);
      err.hidden = true;
      list.innerHTML = '<div class="muted">Загрузка…</div>';
      modal.hidden = false;
      load();
      setTimeout(function () { form.amount.focus(); }, 30);
    }
    function close() { modal.hidden = true; row = null; }

    modal.querySelectorAll("[data-fh-close]").forEach(function (b) { b.addEventListener("click", close); });
    modal.addEventListener("click", function (e) {
      if (e.target === modal) { close(); return; }
      const del = e.target.closest("[data-fh-del]");
      if (!del || !confirm("Удалить эту выплату?")) return;
      post(del.dataset.fhDel).then(function (res) { if (res.ok) load(); });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) close(); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      err.hidden = true;
      post(row.dataset.recordUrl, { amount: form.amount.value, date: form.date.value, note: form.note.value })
        .then(function (res) {
          if (!res.ok) { err.textContent = res.d.error || "Не удалось сохранить"; err.hidden = false; return; }
          form.amount.value = "";
          form.note.value = "";
          load();
        });
    });
    return { open: open };
  })();

  document.querySelectorAll("[data-fin-root] [data-fin-table]").forEach(initTable);
})();
