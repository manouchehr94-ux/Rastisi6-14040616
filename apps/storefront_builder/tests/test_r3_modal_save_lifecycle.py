"""Phase 1 repair — R3 modal shared save lifecycle.

ROOT CAUSE (proven live in a real browser, see the Phase 1 report): the R3
full-screen editor reuses the same settings-form partials as the legacy R2
sidebar inspector, but the JS orchestration layer that turns a form submit
into a background AJAX save (``queueInspectorAutosave`` /
``autosaveInspectorForm``) was wired only to ``#sfbInspectorBody`` — the R2
panel, permanently ``display:none`` inside ``.sfb-r3-shell``. ``#sfbR3ModalBody``
never received the equivalent wiring, so:

  * the inner "ذخیره تنظیمات" submit button fell through to a *native*
    browser form submission (confirmed via Playwright: two
    ``framenavigated`` events, R3 modal closed afterwards) instead of
    keeping the modal open;
  * the footer "انجام شد" button was a plain ``@click="closeR3Modal();
    reloadPreview()"`` with no persistence call at all — clicking it
    discarded any unsaved change in the active form.

Both buttons are therefore fixed at their shared root: one
``saveActiveR3Settings({closeOnSuccess})`` operation, invoked by a single
submit listener delegated on ``document.body`` (filtered to
``#sfbR3ModalBody`` forms — see the docstring on the test below for why it
is not attached to ``#sfbR3ModalBody`` directly) and by the footer Done
button, built on the same ``postFormAjax`` helper R2's autosave now also
uses — not a second, independent persistence path.
"""
