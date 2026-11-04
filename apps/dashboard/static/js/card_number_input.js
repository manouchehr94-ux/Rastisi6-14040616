/* Card-number input mask for the Finance settings (card transfer). PRESENTATION ONLY — the server is the authority and applies the same rules
   (apps/orders/gateways/card_to_card.py::strip_display_formatting): it normalizes Persian / Arabic-Indic / fullwidth digits, ignores every separator,
   invisible RTL mark (ZWNJ, ZWSP, LRM, RLM, bidi isolates) and dash, then judges the DIGITS (count + checksum), never the grouped characters.
   Here the field simply shows 4 groups of 4, whatever the merchant typed or pasted; the grouping is never what gets validated.
   One delegated listener => it also works for cards swapped in by HTMX. */
(function () {
  'use strict';
  var RANGES = [[0x30, 0x39], [0x6F0, 0x6F9], [0x660, 0x669], [0xFF10, 0xFF19]];   // ASCII · Persian · Arabic-Indic · fullwidth

  function digitsOf(text) {
    var out = '';
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      for (var r = 0; r < RANGES.length; r++) {
        if (code >= RANGES[r][0] && code <= RANGES[r][1]) { out += String(code - RANGES[r][0]); break; }
      }
    }
    return out;                                   // separators, marks and any other character are simply not digits
  }
  function group(digits) { return digits.replace(/(\d{4})(?=\d)/g, '$1 '); }
  window.RastiSiCardMask = { digitsOf: digitsOf, group: function (text) { return group(digitsOf(text).slice(0, 16)); } };

  document.addEventListener('input', function (event) {
    var el = event.target;
    if (!el || !el.matches || !el.matches('input[data-card-input]') || event.isComposing) return;
    var caret = el.selectionStart == null ? el.value.length : el.selectionStart;
    var before = digitsOf(el.value.slice(0, caret)).length;          // digits to the left of the caret
    var digits = digitsOf(el.value).slice(0, 16);
    var shown = group(digits);
    if (shown === el.value) return;
    el.value = shown;
    var pos = 0, seen = 0;                                           // put the caret after the same number of digits
    while (pos < shown.length && seen < Math.min(before, digits.length)) { if (/\d/.test(shown[pos])) seen++; pos++; }
    try { el.setSelectionRange(pos, pos); } catch (e) { /* not selectable: ignore */ }
  });
}());
