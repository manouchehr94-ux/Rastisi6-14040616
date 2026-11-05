/* Platform Owner Admin — رفتارِ مشترکِ رابط (vanilla، بدونِ وابستگی؛ فقط در قالب‌هایِ platform_admin بارگذاری می‌شود).
   ۱ منویِ موبایل · ۲ توست‌ها · ۳ تأییدِ عملِ مخرب (data-confirm) · ۴ حالتِ loading و جلوگیری از ارسالِ دوباره ·
   ۵ هشدارِ تغییراتِ ذخیره‌نشده (data-pa-dirty) · ۶ اعتبارسنجیِ خطِ‌به‌خط · ۷ فیلدهایِ عددی (بدونِ تغییر با چرخِ ماوس) · ۸ ستاره‌یِ الزامی */
(function () {
  "use strict";
  var doc = document;
  function qs(s, r) { return (r || doc).querySelector(s); }
  function qsa(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function el(tag, cls, text) { var e = doc.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }

  /* ---- ۱. منویِ موبایل ---- */
  var sidebar = qs("[data-pa-sidebar]"), backdrop = qs("[data-pa-backdrop]"), opener = qs("[data-pa-nav-open]"), lastFocus = null;
  function setNav(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    if (opener) opener.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { lastFocus = doc.activeElement; var a = qs(".pa-nav-link.active, .pa-nav-link", sidebar); if (a) a.focus(); }
    else if (lastFocus && lastFocus.focus) { lastFocus.focus(); lastFocus = null; }
  }
  if (opener) opener.addEventListener("click", function () { setNav(true); });
  qsa("[data-pa-nav-close]").forEach(function (b) { b.addEventListener("click", function () { setNav(false); }); });
  if (backdrop) backdrop.addEventListener("click", function () { setNav(false); });
  if (sidebar) sidebar.addEventListener("click", function (e) { if (e.target.closest("a.pa-nav-link") && sidebar.classList.contains("open")) setNav(false); });
  doc.addEventListener("keydown", function (e) { if (e.key === "Escape" && sidebar && sidebar.classList.contains("open")) setNav(false); });

  /* ---- ۲. توست‌ها: پیامِ موفقیت/اطلاع به توستِ خودبسته؛ خطا همان‌جا (درون صفحه) می‌ماند ---- */
  var toasts = null;
  function toast(text, kind) {
    if (!toasts) { toasts = el("div", "pa-toasts"); toasts.setAttribute("aria-live", "polite"); doc.body.appendChild(toasts); }
    var t = el("div", "pa-toast " + (kind === "error" ? "pa-alert-error" : "pa-alert-success")); t.setAttribute("role", kind === "error" ? "alert" : "status");
    t.appendChild(el("p", "", text));
    var x = el("button", "", "×"); x.type = "button"; x.setAttribute("aria-label", "بستن"); x.addEventListener("click", function () { t.remove(); });
    t.appendChild(x); toasts.appendChild(t);
    if (kind !== "error") setTimeout(function () { t.remove(); }, 6000);
  }
  window.PA = window.PA || {}; window.PA.toast = toast;
  qsa("[data-pa-message='success']").forEach(function (m) { toast(m.textContent.trim(), "success"); m.remove(); });

  /* ---- ۳. تأییدِ عملِ مخرب ---- */
  var pending = null;
  function confirmDialog(message, onOk, okLabel) {
    var overlay = el("div", "pa-modal"); overlay.setAttribute("role", "presentation");
    var box = el("div", "pa-modalbox"); box.setAttribute("role", "alertdialog"); box.setAttribute("aria-modal", "true"); box.setAttribute("aria-label", "تأیید");
    var body = el("div", "pa-modalbody"); body.appendChild(el("p", "", message));
    var foot = el("div", "pa-modalfoot");
    var ok = el("button", "pa-btn pa-primary pa-danger", okLabel || "تأیید"); ok.type = "button";
    var no = el("button", "pa-btn", "انصراف"); no.type = "button";
    foot.appendChild(ok); foot.appendChild(no); box.appendChild(body); box.appendChild(foot); overlay.appendChild(box); doc.body.appendChild(overlay);
    var prev = doc.activeElement; no.focus();
    function close() { overlay.remove(); if (prev && prev.focus) prev.focus(); doc.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); if (e.key === "Tab") { var f = [ok, no]; var i = f.indexOf(doc.activeElement); e.preventDefault(); f[(i + (e.shiftKey ? -1 : 1) + 2) % 2].focus(); } }
    doc.addEventListener("keydown", onKey);
    no.addEventListener("click", close); overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    ok.addEventListener("click", function () { close(); onOk(); });
  }
  doc.addEventListener("submit", function (e) {
    var form = e.target, sub = e.submitter, msg = (sub && sub.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (msg && !form.__paConfirmed) {
      e.preventDefault(); e.stopImmediatePropagation();
      confirmDialog(msg, function () { form.__paConfirmed = true; if (form.requestSubmit) form.requestSubmit(sub || undefined); else form.submit(); });
    }
  }, true);

  /* ---- مودالِ بومی: [data-pa-open="id"] باز می‌کند، [data-pa-close] یا کلیک روی پس‌زمینه می‌بندد ---- */
  doc.addEventListener("click", function (e) {
    var o = e.target.closest("[data-pa-open]");
    if (o) { var d = doc.getElementById(o.getAttribute("data-pa-open")); if (d && d.showModal) d.showModal(); return; }
    if (e.target.closest("[data-pa-close]")) { var dd = e.target.closest("dialog"); if (dd) dd.close(); return; }
    if (e.target.tagName === "DIALOG" && e.target.classList.contains("pa-dialog")) e.target.close();
  });

  /* ---- [data-pa-set="id=value"]: مقدارِ یک فیلدِ مخفی را پیش از ارسالِ دکمه تنظیم می‌کند (بدونِ onclick درون‌خطی) ---- */
  doc.addEventListener("click", function (e) {
    var b = e.target.closest("[data-pa-set]"); if (!b) return;
    var kv = b.getAttribute("data-pa-set").split("="), t = doc.getElementById(kv[0]); if (t) t.value = kv[1] || "";
  });

  /* ---- ۴. loading + جلوگیری از ارسالِ دوباره ---- */
  doc.addEventListener("submit", function (e) {
    var form = e.target; if (e.defaultPrevented || form.hasAttribute("data-no-loading") || (form.method || "").toLowerCase() !== "post") return;
    if (form.__paSubmitting) { e.preventDefault(); return; }
    form.__paSubmitting = true; form.__paConfirmed = false;
    var b = e.submitter || qs("button[type=submit].pa-primary, button[type=submit]", form);
    if (b) b.classList.add("is-loading");
    setTimeout(function () { if (b) b.setAttribute("aria-busy", "true"); }, 0);
  });
  window.addEventListener("pageshow", function () { qsa("form").forEach(function (f) { f.__paSubmitting = false; }); qsa(".is-loading").forEach(function (b) { b.classList.remove("is-loading"); b.removeAttribute("aria-busy"); }); });

  /* ---- ۵. هشدارِ تغییراتِ ذخیره‌نشده ---- */
  var dirty = false;
  qsa("form[data-pa-dirty]").forEach(function (f) {
    var bar = qs(".pa-formbar", f), note = null;
    function mark() { dirty = true; if (bar && !note) { note = el("span", "pa-dirty-note", "تغییراتِ ذخیره‌نشده"); note.setAttribute("role", "status"); bar.appendChild(note); } }
    f.addEventListener("input", mark); f.addEventListener("change", mark);
    f.addEventListener("submit", function () { dirty = false; });
  });
  window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  /* ---- ۶. اعتبارسنجیِ خطِ‌به‌خط (Constraint Validation) ---- */
  doc.addEventListener("invalid", function (e) {
    var f = e.target; if (!f.closest || !f.closest(".pa")) return; e.preventDefault();
    var field = f.closest(".pa-field"); if (!field) return;
    field.classList.add("has-error"); var err = qs(".pa-error[data-auto]", field);
    if (!err) { err = el("div", "pa-error"); err.setAttribute("data-auto", ""); err.id = "err-" + Math.random().toString(36).slice(2, 8); field.appendChild(err); }
    err.textContent = f.validationMessage || "مقدارِ واردشده معتبر نیست."; f.setAttribute("aria-invalid", "true"); f.setAttribute("aria-describedby", err.id);
    if (!qs(".has-error [aria-invalid]:focus") && qsa(".pa-field.has-error").length === 1) f.focus();
  }, true);
  doc.addEventListener("input", function (e) {
    var f = e.target, field = f.closest && f.closest(".pa-field"); if (!field || !field.classList.contains("has-error")) return;
    if (f.checkValidity()) { field.classList.remove("has-error"); f.removeAttribute("aria-invalid"); var a = qs(".pa-error[data-auto]", field); if (a) a.remove(); }
  });

  /* ---- تصویرِ ناموجود (مثلاً پیش‌فرضِ ثبت‌نشده): جایگزینِ خنثی به‌جایِ تصویرِ شکسته ---- */
  doc.addEventListener("error", function (e) {
    var img = e.target; if (!img || img.tagName !== "IMG" || !img.hasAttribute("data-pa-fallback")) return;
    var box = el("div", "pa-photo pa-photo-missing", "تصویرِ پیش‌فرض در این محیط موجود نیست");
    img.replaceWith(box);
  }, true);

  /* ---- ۷. عددی: چرخِ ماوس مقدار را عوض نکند ---- */
  doc.addEventListener("wheel", function (e) { var t = e.target; if (t && t.type === "number" && doc.activeElement === t) t.blur(); }, { passive: true });

  /* ---- صفحه‌هایِ Inbox (قالبِ مشترکِ notifications) h1 ندارند: عنوانِ h2 به‌عنوانِ h1 معرفی می‌شود (بدونِ دست‌زدن به قالبِ مشترک) ---- */
  if (!qs("h1")) { var ih = qs(".nt-head h2"); if (ih) { ih.setAttribute("role", "heading"); ih.setAttribute("aria-level", "1"); } }

  /* ---- لینکِ مستقیم به یک کارتِ جمع‌شونده (#gw-code) آن را باز می‌کند ---- */
  if (location.hash) { var tgt = qs(location.hash.replace(/[^#\w-]/g, "")); var dd = tgt && qs("details[data-gw-details]", tgt); if (dd) dd.open = true; }

  /* ---- ۸. ارتباطِ label↔کنترل (اگر for/id نبود) و ستاره‌یِ فیلدِ الزامی ---- */
  var uid = 0;
  qsa(".pa-field").forEach(function (field) {
    var l = qs(":scope > label", field), c = qs("input:not([type=hidden]), select, textarea", field);
    if (l && c && !l.htmlFor && !c.id) { c.id = "pa-f-" + (++uid); l.htmlFor = c.id; }
  });
  qsa(".pa-field").forEach(function (field) {
    var c = qs("input[required], select[required], textarea[required]", field), l = qs(":scope > label", field);
    if (c && l && !qs(".req", l)) { var s = el("span", "req", "*"); s.setAttribute("aria-hidden", "true"); l.appendChild(s); }
  });
})();
