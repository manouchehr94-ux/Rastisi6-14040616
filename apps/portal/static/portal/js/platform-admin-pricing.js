/* Platform Admin › plan form › simple pricing preview.
   DISPLAY ONLY — the server recalculates and stores the real amounts (apps.subscriptions.services.period_pricing); nothing
   calculated here is ever submitted. Same policy: final = round_half_up(monthly × months × (100 − discount) / 100) in whole
   toman, exact integer (BigInt) arithmetic, discount in basis points (no floating point money). */
(function () {
  "use strict";
  var root = document.querySelector("[data-pricing]");
  if (!root) return;
  var cfg = {};
  try { cfg = JSON.parse(root.getAttribute("data-config") || "{}"); } catch (e) { cfg = {}; }
  var nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
  var pf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });

  function latin(text) {
    return String(text || "")
      .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06f0); })
      .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
      .replace(/[,٬\s]/g, "").replace(/٫/g, ".");
  }
  function parseMonthly(text) {
    var t = latin(text);
    if (!/^\d{1,12}$/.test(t)) return null;
    var v = BigInt(t);
    return v > 0n && v <= BigInt(cfg.max_monthly || 100000000000) ? v : null;
  }
  function parseBasisPoints(text) {           // "12.5" -> 1250 ; empty -> 0 ; invalid -> null
    var t = latin(text);
    if (t === "") return 0n;
    var m = /^(\d{1,3})(?:\.(\d{1,2}))?$/.exec(t);
    if (!m) return null;
    var bp = BigInt(m[1]) * 100n + BigInt((m[2] || "").padEnd(2, "0") || "0");
    return bp < 10000n ? bp : null;            // 100 % is not a discount (free plans are a separate plan type)
  }
  function compute(monthly, months, bp) {
    var base = monthly * BigInt(months);
    var fin = (base * (10000n - bp) + 5000n) / 10000n;          // half-up to the whole toman (values are positive)
    var effective = (fin * 2n + BigInt(months)) / (2n * BigInt(months));
    return { base: base, discount: base - fin, final: fin, effective: effective };
  }
  function fmt(v) { return nf.format(Number(v)) + " تومان"; }

  var monthlyInput = root.querySelector("[data-pr-monthly]");
  var periods = Array.prototype.slice.call(root.querySelectorAll("[data-period]"));
  var kinds = root.querySelectorAll("[data-pr-kind]");

  function set(card, key, text) { var el = card.querySelector('[data-out="' + key + '"]'); if (el) el.textContent = text; }
  function clear(card) { ["base", "discount", "final", "effective"].forEach(function (k) { set(card, k, "—"); }); }

  function render() {
    var monthly = parseMonthly(monthlyInput && monthlyInput.value);
    periods.forEach(function (card) {
      var months = parseInt(card.getAttribute("data-months"), 10);
      var input = card.querySelector("[data-pr-discount]");
      var err = card.querySelector('[data-out="error"]');
      var offer = card.querySelector("[data-pr-offer]");
      var keep = card.querySelector("[data-pr-keep]");
      var legacyKept = keep && keep.checked;
      var off = (offer && !offer.checked) || legacyKept;
      card.classList.toggle("is-off", !!off);
      if (input) { input.disabled = !!off; }
      var ack = card.querySelector("[data-pr-ack]");
      if (ack) { ack.disabled = !!legacyKept; }
      if (err) { err.hidden = true; err.textContent = ""; }
      if (monthly === null) { clear(card); return; }
      var bp = input ? parseBasisPoints(input.value) : 0n;
      if (bp === null) {
        clear(card);
        if (err) { err.hidden = false; err.textContent = "درصدِ تخفیف باید بینِ ۰ و کمتر از ۱۰۰ (حداکثر دو رقمِ اعشار) باشد."; }
        return;
      }
      var r = compute(monthly, months, bp);
      if (r.final < 1n) { clear(card); if (err) { err.hidden = false; err.textContent = "قیمتِ نهایی باید حداقل یک تومان باشد."; } return; }
      set(card, "base", fmt(r.base));
      set(card, "discount", fmt(r.discount) + (bp > 0n && input ? " (" + pf.format(Number(bp) / 100) + "٪)" : ""));
      set(card, "final", off && legacyKept ? "قیمتِ قدیمی حفظ می‌شود" : fmt(r.final));
      set(card, "effective", fmt(r.effective) + " / ماه");
    });
  }

  function toggleKind() {
    var free = false;
    kinds.forEach(function (k) { if (k.checked && k.value === "free") free = true; });
    var paid = root.querySelector("[data-pr-paid]"), note = root.querySelector("[data-pr-free]");
    if (paid) paid.hidden = free;
    if (note) note.hidden = !free;
  }

  root.addEventListener("input", render);
  root.addEventListener("change", function () { toggleKind(); render(); });
  toggleKind();
  render();
  root.setAttribute("data-pr-ready", "1");
})();
