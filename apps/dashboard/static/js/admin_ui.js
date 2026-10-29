/* RastiSi admin — shared design layer behaviour (see admin_ui.css).
 *
 *   data-au-open="#id"      open the <dialog id> (modal)
 *   data-au-close           close the enclosing <dialog>
 *   data-au-confirm="text"  ask before an irreversible action: the click/submit goes ahead only after the person confirms in a modal
 *                           (works on <button>, <a> and <form>); no text means the generic Persian prompt below.
 *   .au-switch [data-au-autosubmit]  submits the enclosing form when the switch flips.
 * Backdrop click and Esc close a modal; focus returns to the opener.
 */
(function () {
  'use strict';
  var GENERIC = 'این عمل قابل بازگشت نیست. ادامه می‌دهید؟';
  var lastOpener = null;

  function openDialog(dlg, opener) {
    if (!dlg) return;
    lastOpener = opener || document.activeElement;
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  }
  function closeDialog(dlg) {
    if (!dlg) return;
    if (typeof dlg.close === 'function') dlg.close(); else dlg.removeAttribute('open');
    if (lastOpener && lastOpener.focus) { try { lastOpener.focus(); } catch (e) { /* detached */ } }
  }

  function confirmDialog() {
    var dlg = document.getElementById('au-confirm-dialog');
    if (dlg) return dlg;
    dlg = document.createElement('dialog');
    dlg.id = 'au-confirm-dialog';
    dlg.className = 'au-modal';
    dlg.innerHTML = '<div class="au-modal__head"><h3>تأیید عملیات</h3><button type="button" class="au-x" data-au-close aria-label="بستن">×</button></div>' +
      '<div class="au-modal__body"><p id="au-confirm-text" style="margin:0"></p></div>' +
      '<div class="au-modal__foot"><button type="button" class="au-btn au-btn--primary" id="au-confirm-yes">تأیید و ادامه</button>' +
      '<button type="button" class="au-btn au-btn--ghost" data-au-close>انصراف</button></div>';
    document.body.appendChild(dlg);
    return dlg;
  }

  function askConfirm(text, proceed, opener) {
    var dlg = confirmDialog();
    dlg.querySelector('#au-confirm-text').textContent = text || GENERIC;
    var yes = dlg.querySelector('#au-confirm-yes');
    var fresh = yes.cloneNode(true);
    yes.parentNode.replaceChild(fresh, yes);
    fresh.addEventListener('click', function () { closeDialog(dlg); proceed(); });
    openDialog(dlg, opener);
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    var opener = t.closest && t.closest('[data-au-open]');
    if (opener) { e.preventDefault(); openDialog(document.querySelector(opener.getAttribute('data-au-open')), opener); return; }
    var closer = t.closest && t.closest('[data-au-close]');
    if (closer) { e.preventDefault(); closeDialog(closer.closest('dialog')); return; }
    if (t.tagName === 'DIALOG' && t.classList.contains('au-modal')) {  // backdrop
      var r = t.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeDialog(t);
      return;
    }
    var guarded = t.closest && t.closest('button[data-au-confirm], a[data-au-confirm], input[data-au-confirm]');
    if (guarded && guarded.dataset.auConfirmed !== '1') {
      e.preventDefault();
      askConfirm(guarded.getAttribute('data-au-confirm'), function () {
        guarded.dataset.auConfirmed = '1';
        guarded.click();
        delete guarded.dataset.auConfirmed;
      }, guarded);
    }
  }, true);

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form && form.matches && form.matches('form[data-au-confirm]') && form.dataset.auConfirmed !== '1') {
      e.preventDefault();
      askConfirm(form.getAttribute('data-au-confirm'), function () {
        form.dataset.auConfirmed = '1';
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      }, document.activeElement);
    }
  }, true);

  document.addEventListener('change', function (e) {
    var sw = e.target;
    if (sw && sw.matches && sw.matches('.au-switch input[data-au-autosubmit]') && sw.form) {
      if (sw.form.requestSubmit) sw.form.requestSubmit(); else sw.form.submit();
    }
  });
})();
