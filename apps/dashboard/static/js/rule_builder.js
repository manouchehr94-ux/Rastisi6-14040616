/* سازنده‌ی بصریِ قواعدِ کمپین — درختِ AND/OR تودرتو → JSON در فیلدِ مخفی.
   فقط یک ویرایشگرِ UI است؛ اعتبارسنجیِ نهایی همیشه سمتِ سرور انجام می‌شود. */
(function () {
  "use strict";
  var el = document.getElementById("rule-builder");
  if (!el) return;
  var schema = JSON.parse(document.getElementById("rule-schema").textContent);
  var input = document.getElementById("id_rules_json");
  var leafByKey = {};
  schema.leaves.forEach(function (l) { leafByKey[l.key] = l; });
  var root;
  try { root = JSON.parse(input.value || "{}"); } catch (e) { root = {}; }
  if (!root || !root.type) root = { type: "group", op: "and", negate: false, children: [] };
  if (root.type !== "group") root = { type: "group", op: "and", negate: false, children: [root] };

  function h(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "class") n.className = attrs[k];
      else if (k === "text") n.textContent = attrs[k];
      else if (k.indexOf("on") === 0) n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  // مدیریتِ فوکوس: رندرِ دوباره DOM را می‌سازد؛ بدونِ بازگرداندنِ فوکوس، کاربرِ صفحه‌کلید/صفحه‌خوان به <body> پرت می‌شود.
  var ids = new WeakMap(), seq = 0, nextFocus = null;
  function idOf(n) { if (!ids.has(n)) ids.set(n, ++seq); return ids.get(n); }
  function request(key) { nextFocus = key; }
  function sync() { input.value = JSON.stringify(root.children.length ? root : {}); }
  function splitList(s) { return String(s || "").split(/[,،\n]/).map(function (x) { return x.trim(); }).filter(Boolean); }
  function visible(field, node) {
    if (!field.show_if) return true;
    return Object.keys(field.show_if).every(function (k) {
      var want = field.show_if[k]; var have = node[k];
      return Array.isArray(want) ? want.indexOf(have) >= 0 : have === want;
    });
  }

  function fieldControl(field, node, rerender) {
    var name = field.name, t = field.type, ctl;
    var fk = idOf(node) + ":f:" + name;
    function set(v) { if (v === "" || v === null || (Array.isArray(v) && !v.length)) delete node[name]; else node[name] = v; sync(); }
    if (node[name] === undefined && field.default !== undefined) { node[name] = field.default; }
    if (t === "select") {
      ctl = h("select", { class: "inp", "aria-label": field.label, onchange: function (e) { set(e.target.value); rerender(); } },
        field.options.map(function (o) { return h("option", { value: o[0], text: o[1] }); }));
      ctl.value = node[name] === undefined ? "" : node[name];
      if (node[name] === undefined && field.options.length) { node[name] = field.options[0][0]; ctl.value = node[name]; }
    } else if (t === "number" || t === "int") {
      ctl = h("input", { class: "inp", type: "text", inputmode: "numeric", dir: "ltr", "aria-label": field.label, style: "width:140px",
        onchange: function (e) { var v = e.target.value.replace(/[٬,\s]/g, "").replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }); set(v === "" ? "" : (t === "int" ? parseInt(v, 10) : v)); } });
      ctl.value = node[name] === undefined ? "" : node[name];
    } else if (t === "date") {
      ctl = h("input", { class: "inp", type: "text", dir: "ltr", placeholder: "۱۴۰۵/۰۷/۰۱", "aria-label": field.label, style: "width:140px", onchange: function (e) { set(e.target.value.trim()); } });
      ctl.value = node[name] || "";
    } else if (t === "bool") {
      ctl = h("input", { type: "checkbox", "aria-label": field.label, onchange: function (e) { node[name] = e.target.checked; sync(); } });
      ctl.checked = node[name] !== false && node[name] !== undefined ? !!node[name] : node[name] === undefined ? true : false;
    } else if (t === "text_list") {
      ctl = h("input", { class: "inp", type: "text", "aria-label": field.label, style: "min-width:220px", onchange: function (e) { set(splitList(e.target.value)); } });
      ctl.value = (node[name] || []).join("، ");
    } else if (t === "int_list") {
      ctl = h("input", { class: "inp", type: "text", dir: "ltr", "aria-label": field.label, style: "min-width:180px", onchange: function (e) { set(splitList(e.target.value).map(Number).filter(function (n) { return n > 0; })); } });
      ctl.value = (node[name] || []).join(", ");
    } else if (t === "ids" || t === "multi" || t === "int_multi") {
      var options = t === "ids" ? (schema.sources[field.source] || []) : field.options;
      ctl = h("select", { class: "inp", multiple: "multiple", size: Math.min(6, Math.max(3, options.length)), "aria-label": field.label, style: "min-width:200px",
        onchange: function (e) {
          var vals = Array.prototype.filter.call(e.target.options, function (o) { return o.selected; }).map(function (o) { return t === "multi" ? o.value : Number(o.value); });
          set(vals);
        } }, options.map(function (o) { return h("option", { value: o[0], text: o[1] }); }));
      var have = (node[name] || []).map(String);
      Array.prototype.forEach.call(ctl.options, function (o) { o.selected = have.indexOf(o.value) >= 0; });
    } else { ctl = h("span", { text: "؟" }); }
    ctl.setAttribute("data-fk", fk);
    return h("label", { class: "rb-field", style: "display:inline-flex;flex-direction:column;gap:2px;font-size:12px" }, [field.label, ctl]);
  }

  function renderLeaf(node, parent, rerender) {
    var spec = leafByKey[node.type] || { label: node.type, fields: [] };
    var pos = parent.children.indexOf(node) + 1;
    var leafName = "شرط «" + spec.label + "» (شماره " + pos + ")";
    var box = h("div", { class: "rb-leaf", role: "group", "aria-label": leafName, style: "border:1px solid var(--line,#d9dce3);border-radius:10px;padding:10px;margin:6px 0;background:var(--card,#fff)" });
    var head = h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:6px" }, [
      h("b", { text: spec.label }),
      h("button", { type: "button", class: "btn btn-sm btn-danger", "aria-label": "حذف " + leafName, "data-fk": idOf(node) + ":del", text: "حذف", onclick: function () { parent.children.splice(parent.children.indexOf(node), 1); sync(); request(idOf(parent) + ":picker"); rerender(); } }),
    ]);
    box.appendChild(head);
    if (spec.help) box.appendChild(h("small", { text: spec.help, style: "color:var(--muted,#6b7280);display:block;margin-bottom:6px" }));
    var row = h("div", { style: "display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end" });
    (spec.fields || []).forEach(function (f) { if (visible(f, node)) row.appendChild(fieldControl(f, node, rerender)); });
    var firstCtl = row.querySelector("[data-fk]");
    if (firstCtl) firstCtl.setAttribute("data-first", idOf(node));
    else head.querySelector("button").setAttribute("data-first", idOf(node));
    box.appendChild(row);
    return box;
  }

  function renderGroup(node, parent, rerender, depth) {
    var gid = idOf(node);
    var gname = depth === 1 ? "گروهِ اصلیِ شرط‌ها" : "گروهِ تودرتو (سطح " + depth + ")";
    var box = h("div", { class: "rb-group", role: "group", "aria-label": gname, style: "border:2px solid " + (node.op === "or" ? "#f59e0b" : "#6366f1") + ";border-radius:12px;padding:10px;margin:8px 0;background:rgba(99,102,241,.04)" });
    var opSel = h("select", { class: "inp", style: "width:auto", "aria-label": "عملگر " + gname, "data-fk": gid + ":op", onchange: function (e) { node.op = e.target.value; sync(); rerender(); } }, [
      h("option", { value: "and", text: "همه‌ی شرط‌ها (و — AND)" }), h("option", { value: "or", text: "یکی از شرط‌ها (یا — OR)" })]);
    opSel.value = node.op;
    var neg = h("label", { style: "font-size:12px" }, [h("input", { type: "checkbox", "aria-label": "برعکس (NOT) — " + gname, "data-fk": gid + ":neg", onchange: function (e) { node.negate = e.target.checked; sync(); } }), " برعکس (NOT)"]);
    neg.firstChild.checked = !!node.negate;
    var head = h("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" }, [opSel, neg]);
    if (parent) head.appendChild(h("button", { type: "button", class: "btn btn-sm btn-danger", text: "حذف گروه", "aria-label": "حذف " + gname, onclick: function () { parent.children.splice(parent.children.indexOf(node), 1); sync(); request(idOf(parent) + ":picker"); rerender(); } }));
    box.appendChild(head);
    node.children.forEach(function (child) {
      box.appendChild(child.type === "group" ? renderGroup(child, node, rerender, depth + 1) : renderLeaf(child, node, rerender));
    });
    var picker = h("select", { class: "inp", style: "width:auto;max-width:260px", "aria-label": "افزودن شرط به " + gname, "data-fk": gid + ":picker" }, [h("option", { value: "", text: "＋ افزودن شرط…" })]);
    var cats = {};
    schema.leaves.forEach(function (l) { (cats[l.category || "سایر"] = cats[l.category || "سایر"] || []).push(l); });
    Object.keys(cats).forEach(function (c) {
      var g = h("optgroup", { label: c });
      cats[c].forEach(function (l) { g.appendChild(h("option", { value: l.key, text: l.label })); });
      picker.appendChild(g);
    });
    picker.addEventListener("change", function () {
      if (!picker.value) return;
      var child = { type: picker.value };
      node.children.push(child); sync(); request("first:" + idOf(child)); rerender();
    });
    var actions = h("div", { style: "display:flex;gap:8px;margin-top:8px;flex-wrap:wrap" }, [picker]);
    if (depth < 5) actions.appendChild(h("button", { type: "button", class: "btn btn-sm", text: "＋ گروهِ تودرتو", "aria-label": "افزودن گروهِ تودرتو به " + gname, "data-fk": gid + ":nested", onclick: function () { var g = { type: "group", op: "or", negate: false, children: [] }; node.children.push(g); sync(); request(idOf(g) + ":op"); rerender(); } }));
    box.appendChild(actions);
    return box;
  }

  function rerender() {
    var active = document.activeElement;
    var key = nextFocus || (active && el.contains(active) && active.getAttribute ? active.getAttribute("data-fk") : null);
    nextFocus = null;
    el.innerHTML = "";
    el.appendChild(renderGroup(root, null, rerender, 1));
    sync();
    if (key) {
      var target = key.indexOf("first:") === 0 ? el.querySelector('[data-first="' + key.slice(6) + '"]') : el.querySelector('[data-fk="' + key + '"]');
      if (target) target.focus();
    }
  }
  el.setAttribute("role", "region");
  el.setAttribute("aria-label", "سازنده‌ی قواعد کمپین");
  rerender();
})();
