/* Browser test (Chromium via Playwright) for apps/dashboard/static/js/card_number_input.js — the presentation-only card mask of Finance → Card Transfer.
   Hermetic: a static page with a synthetic input; no network, no payment, no real card. Run:  node apps/dashboard/tests/browser/card_number_input_qa.js */
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '../../../..');
const maskJs = fs.readFileSync(path.join(root, 'apps/dashboard/static/js/card_number_input.js'), 'utf8');
const results = []; const ok = (n, c, x = '') => { results.push(c); console.log((c ? 'PASS ' : 'FAIL ') + n + (x ? '  ' + x : '')); };
const HTML = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>t</title></head><body>
<form><input id="card" name="c" data-card-input inputmode="numeric" maxlength="40"><input id="other" name="o" value=""></form><div id="slot"></div>
<script src="/card_number_input.js"></script></body></html>`;
const DIGITS = '6104123412341234', GROUPED = '6104 1234 1234 1234';

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ locale: 'fa-IR' })).newPage();
  await page.route('**/*', route => {
    const u = new URL(route.request().url());
    if (u.pathname === '/card_number_input.js') return route.fulfill({ contentType: 'text/javascript', body: maskJs });
    if (u.hostname === 'card.test') return route.fulfill({ contentType: 'text/html', body: HTML });
    return route.abort();                                               // nothing else may leave the page
  });
  await page.goto('http://card.test/');
  const val = sel => page.$eval(sel, e => e.value);
  const setVal = async (text, sel = '#card') => { await page.$eval(sel, e => { e.value = ''; }); await page.focus(sel); await page.keyboard.insertText(text); return val(sel); };

  ok('typing 16 ASCII digits shows four groups of four', (await setVal(DIGITS)) === GROUPED);
  ok('typing digit by digit (real key events) groups on the fly', await (async () => { await page.$eval('#card', e => { e.value = ''; }); await page.focus('#card'); await page.keyboard.type(DIGITS); return (await val('#card')) === GROUPED; })());
  ok('Persian digits are converted', (await setVal('۶۱۰۴۱۲۳۴۱۲۳۴۱۲۳۴')) === GROUPED);
  ok('Arabic-Indic digits are converted', (await setVal('٦١٠٤١٢٣٤١٢٣٤١٢٣٤')) === GROUPED);
  ok('fullwidth digits are converted', (await setVal('６１０４１２３４１２３４１２３４')) === GROUPED);
  ok('mixed digit scripts', (await setVal('6104 ۱۲۳۴ ١٢٣٤ 1234')) === GROUPED);
  ok('paste with ZWNJ / ZWSP / LRM / RLM / bidi isolates / NBSP / dashes / Arabic comma', (await setVal('⁦6104‌1234​1234 1234⁩‎‏-،')) === GROUPED);
  ok('an already grouped value re-pasted does not double-space', (await setVal(GROUPED)) === GROUPED);
  ok('overlong paste is capped at 16 digits', (await setVal('61041234123412349999')) === GROUPED);
  ok('letters and symbols are dropped from the field', (await setVal('6104 abcd 1234#1234 1234')) === GROUPED);
  ok('a partial number shows a partial group, without a trailing space', (await setVal('61041')) === '6104 1' && (await setVal('6104')) === '6104');
  ok('the shown value is 19 characters yet exactly 16 digits (display is independent of the digit count)', await (async () => { await setVal(DIGITS); const v = await val('#card'); return v.length === 19 && window_digits(v) === 16; })());
  function window_digits(v) { return (v.match(/\d/g) || []).length; }
  ok('window.RastiSiCardMask.digitsOf is the digit-only view', await page.evaluate(() => window.RastiSiCardMask.digitsOf('۶۱۰۴ 1234‌٦٧') === '610412346 7'.replace(' ', '')));
  ok('backspace deletes a digit and the mask re-groups', await (async () => { await setVal(DIGITS); await page.keyboard.press('Backspace'); return (await val('#card')) === '6104 1234 1234 123'; })());
  ok('typing in the middle keeps the caret after the typed digit', await (async () => {
    await setVal('6104 1234'); await page.$eval('#card', e => e.setSelectionRange(2, 2)); await page.keyboard.type('9');
    const [v, pos] = await page.$eval('#card', e => [e.value, e.selectionStart]); return v === '6190 4123 4' && pos === 3;
  })());
  ok('other inputs are untouched', (await setVal('abc ۱۲۳', '#other')) === 'abc ۱۲۳');
  ok('an input injected later (HTMX swap) is masked by the same delegated listener', await (async () => {
    await page.evaluate(() => { document.getElementById('slot').innerHTML = '<input id="late" data-card-input>'; });
    return (await setVal('۶۱۰۴۱۲۳۴۱۲۳۴۱۲۳۴', '#late')) === GROUPED;
  })());
  ok('the submitted form value is the grouped text the server then normalizes (never truncated by maxlength 40)', await (async () => { await setVal(DIGITS); return (await page.evaluate(() => new FormData(document.forms[0]).get('c'))) === GROUPED; })());
  await browser.close();
  const failed = results.filter(r => !r).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
})();
