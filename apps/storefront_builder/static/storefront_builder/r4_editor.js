window.RastiSiR4 = {
  selected: null,
  revision: Number(document.querySelector('[data-r4-shell]')?.dataset.editRevision || 0),
  inspectorOpen: false,
  saveState: 'saved',
  conflict: false,
  queue: null,
  resourcePicker: null,
};

(function () {
  var R4 = window.RastiSiR4;
  var shell = document.querySelector('[data-r4-shell]');
  var inspector = document.getElementById('r4Inspector');
  var previewFrame = document.getElementById('r4PreviewFrame');
  var saveStateEl = document.getElementById('r4SaveState');
  var sidebarToggle = document.getElementById('r4SidebarToggle');
  var structurePanel = document.getElementById('r4Structure');
  var structureToggle = document.getElementById('r4StructureToggle');
  // R4 Task 10 — the shared Resource Picker overlay root is created here
  // (never added to editor.html's own markup, which Task 10 leaves
  // untouched) so it always exists as a direct child of the R4 shell.
  var pickerRoot = document.getElementById('r4ResourcePicker');
  if (!pickerRoot && shell) {
    pickerRoot = document.createElement('div');
    pickerRoot.id = 'r4ResourcePicker';
    pickerRoot.hidden = true;
    shell.appendChild(pickerRoot);
  }
  var pickerSearchTimer = null;
  // R4 Task 11 — Global Design + Undo/Redo + Publish topbar controls.
  var globalDesignToggle = document.getElementById('r4GlobalDesignToggle');
  var globalDesignPanel = document.getElementById('r4GlobalDesign');
  var undoButton = document.getElementById('r4UndoButton');
  var redoButton = document.getElementById('r4RedoButton');
  var publishButton = document.getElementById('r4PublishButton');
  var discardButton = document.getElementById('r4DiscardButton');

  // ---- Admin sidebar: R4-page-only, defaults to collapsed on every fresh
  // load (nothing persisted between page loads) — driven purely by a data
  // attribute on the R4 shell root that r4_editor.css's :has() selectors
  // key off of.
  if (sidebarToggle && shell) {
    sidebarToggle.addEventListener('click', function () {
      var r4SidebarExpanded = shell.dataset.r4SidebarExpanded === 'true';
      r4SidebarExpanded = !r4SidebarExpanded;
      shell.dataset.r4SidebarExpanded = r4SidebarExpanded ? 'true' : 'false';
      sidebarToggle.setAttribute('aria-expanded', r4SidebarExpanded ? 'true' : 'false');
    });
  }

  // ---- Structure panel: R4 Task 8, CLOSED by default on every fresh load
  // (nothing persisted), same toggle pattern as the admin sidebar above.
  if (structureToggle && shell) {
    structureToggle.addEventListener('click', function () {
      var open = shell.dataset.r4StructureOpen === 'true';
      open = !open;
      shell.dataset.r4StructureOpen = open ? 'true' : 'false';
      structureToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  var SAVE_STATE_LABELS = {
    saved: 'ذخیره شد',
    saving: 'در حال ذخیره...',
    error: 'خطا در ذخیره تغییرات',
    conflict: 'نسخه‌ی جدیدتری از این صفحه موجود است',
  };

  function setSaveState(state) {
    R4.saveState = state;
    if (saveStateEl) saveStateEl.textContent = SAVE_STATE_LABELS[state] || '';
  }

  function showConflictBanner() {
    if (!shell || document.getElementById('r4ConflictBanner')) return;
    var banner = document.createElement('div');
    banner.id = 'r4ConflictBanner';
    banner.setAttribute('role', 'alert');
    banner.textContent = SAVE_STATE_LABELS.conflict + ' — ';
    var reloadButton = document.createElement('button');
    reloadButton.type = 'button';
    reloadButton.textContent = 'بارگذاری دوباره';
    reloadButton.addEventListener('click', function () {
      window.location.reload();
    });
    banner.appendChild(reloadButton);
    shell.prepend(banner);
  }

  // ---- Task 5's single mutate endpoint: one serialized queue, one sender.
  R4.sendMutation = function (mutation) {
    if (R4.conflict) return Promise.resolve();
    setSaveState('saving');
    var url = new URL('mutate/', window.location.href);
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ base_revision: R4.revision, mutation: mutation }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { status: response.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status === 200 && result.body && result.body.ok) {
          R4.revision = result.body.new_revision;
          if (shell) shell.dataset.editRevision = String(R4.revision);
          setSaveState('saved');
          return result.body;
        }
        if (result.status === 409) {
          // Explicit conflict state — stop the automatic queue for good;
          // never silently replay the stale mutation, never auto-reload.
          R4.conflict = true;
          setSaveState('conflict');
          showConflictBanner();
          return result.body;
        }
        // Controlled non-409 rejection — surfaced, revision untouched,
        // never treated as success, never silently retried.
        setSaveState('error');
        return result.body;
      })
      .catch(function () {
        setSaveState('error');
      });
  };

  R4.enqueueMutation = function (mutation) {
    if (R4.conflict) return Promise.resolve();
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return R4.sendMutation(mutation);
    });
    return R4.queue;
  };

  // ---- R4 Task 8 — structural mutations (add/remove/duplicate/move) go
  // through the SAME single queue/endpoint as every other mutation; this
  // wrapper only adds the read-side refresh a successful structural change
  // needs (existing Preview iframe reload + Structure panel re-fetch), per
  // instruction Section 31. No new write endpoint, no fake client DOM
  // renderer, no second renderer.
  function refreshStructureAndPreview() {
    if (previewFrame && previewFrame.contentWindow) {
      previewFrame.contentWindow.location.reload();
    }
    if (!structurePanel) return Promise.resolve();
    return fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var freshDoc = new DOMParser().parseFromString(html, 'text/html');
        var freshStructure = freshDoc.getElementById('r4Structure');
        if (freshStructure) structurePanel.innerHTML = freshStructure.innerHTML;
      })
      .catch(function () {
        // The mutation itself already succeeded and the server-authoritative
        // revision already advanced — a failed read-side refresh just means
        // the merchant sees the stale list until their next action.
      });
  }

  R4.enqueueStructuralMutation = function (mutation) {
    return R4.enqueueMutation(mutation).then(function (result) {
      if (result && result.ok) {
        if (mutation.type === 'section.remove' && R4.selected === mutation.section_id) {
          closeInspector();
        }
        // Awaited: callers (and this session's own QA) must be able to
        // trust that once this promise resolves, the Structure panel/
        // Preview iframe reflect the just-applied mutation — not just that
        // the server accepted it.
        return refreshStructureAndPreview().then(function () {
          return result;
        });
      }
      return result;
    });
  };

  // ---- Inspector: schema-driven, two tabs, current-value hydration.
  function activateTab(name) {
    if (!inspector) return;
    inspector.querySelectorAll('[data-r4-tab]').forEach(function (tabButton) {
      var isActive = tabButton.getAttribute('data-r4-tab') === name;
      tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    inspector.querySelectorAll('[data-r4-tab-panel]').forEach(function (panel) {
      var isActive = panel.getAttribute('data-r4-tab-panel') === name;
      if (isActive) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
  }

  // ---- appearance_override: a compound field (one schema key, an object
  // value) — hydrated from BOTH the persisted/current value and the
  // inherited-global fallback (shown while disabled, per instruction
  // Section 14), never from a second ad-hoc allowlist.
  function hydrateAppearanceOverrideFields(values) {
    if (!inspector) return;
    var inheritedScript = document.getElementById('r4InspectorInheritedAppearance');
    var inherited = {};
    if (inheritedScript) {
      try {
        inherited = JSON.parse(inheritedScript.textContent) || {};
      } catch (err) {
        inherited = {};
      }
    }
    inspector.querySelectorAll('[data-r4-field-type="appearance_override"]').forEach(function (wrapper) {
      var key = wrapper.getAttribute('data-r4-field-key');
      var stored = Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null;
      var typography = (stored && stored.typography) || {};
      var enabled = Boolean(typography.enabled);
      var fallback = inherited[key] || {};
      var font = typography.font != null ? typography.font : fallback.font;
      var typeScale = typography.type_scale != null ? typography.type_scale : fallback.type_scale;

      var enabledInput = wrapper.querySelector('[data-r4-appearance-enabled]');
      var fontSelect = wrapper.querySelector('[data-r4-appearance-font]');
      var scaleSelect = wrapper.querySelector('[data-r4-appearance-type-scale]');
      if (enabledInput) enabledInput.checked = enabled;
      if (fontSelect) {
        if (font != null) fontSelect.value = font;
        fontSelect.disabled = !enabled;
      }
      if (scaleSelect) {
        if (typeScale != null) scaleSelect.value = typeScale;
        scaleSelect.disabled = !enabled;
      }
    });
  }

  function hydrateFieldValues() {
    if (!inspector) return;
    var script = document.getElementById('r4InspectorFieldValues');
    if (!script) return;
    var values;
    try {
      values = JSON.parse(script.textContent);
    } catch (err) {
      return;
    }
    inspector.querySelectorAll('[data-r4-field-key]').forEach(function (control) {
      var fieldType = control.getAttribute('data-r4-field-type');
      // Compound fields are hydrated separately below — this loop only
      // handles scalar controls. resource_source (R4 Task 9) is a
      // server-rendered READ-ONLY summary with no editable control at
      // all — nothing to hydrate client-side. repeater (R4 Task 6 Group D)
      // is entirely server-rendered from the current value too (see
      // section_inspector.html's current_field_value) — its wrapper carries
      // data-r4-field-key for the compound patch listener below, but has no
      // .value of its own to hydrate.
      if (fieldType === 'appearance_override' || fieldType === 'resource_source' || fieldType === 'repeater') return;
      var key = control.getAttribute('data-r4-field-key');
      if (!Object.prototype.hasOwnProperty.call(values, key)) return;
      var value = values[key];
      if (fieldType === 'boolean') {
        control.checked = Boolean(value);
      } else {
        control.value = value == null ? '' : value;
      }
    });
    hydrateAppearanceOverrideFields(values);
  }

  // R4 Task 6 (Group D) — repeater: reads every remaining row's declared
  // sub-fields straight from the DOM (never from a second in-memory copy —
  // the server-rendered rows plus whatever add/remove/reorder has done to
  // them ARE the source of truth) into a plain array of objects, matching
  // exactly the shape settings_schema._clean_repeater_value expects.
  function collectRepeaterRows(wrapper) {
    var rows = [];
    wrapper.querySelectorAll('[data-r4-repeater-rows] > [data-r4-repeater-row]').forEach(function (rowEl) {
      var row = {};
      rowEl.querySelectorAll('[data-r4-repeater-subfield]').forEach(function (subInput) {
        var subKey = subInput.getAttribute('data-r4-repeater-subfield');
        row[subKey] = subInput.type === 'checkbox' ? subInput.checked : subInput.value;
      });
      rows.push(row);
    });
    return rows;
  }

  function patchRepeaterField(wrapper) {
    if (R4.selected == null) return;
    var key = wrapper.getAttribute('data-r4-field-key');
    var patch = {};
    patch[key] = collectRepeaterRows(wrapper);
    R4.enqueueMutation({
      type: 'section.update_settings',
      section_id: R4.selected,
      patch: patch,
    });
  }

  function addRepeaterRow(wrapper) {
    var maxItems = Number(wrapper.getAttribute('data-r4-repeater-max-items') || '0');
    var rowsContainer = wrapper.querySelector('[data-r4-repeater-rows]');
    var rowTemplate = wrapper.querySelector('[data-r4-repeater-row-template]');
    if (!rowsContainer || !rowTemplate) return;
    if (maxItems > 0 && rowsContainer.querySelectorAll('[data-r4-repeater-row]').length >= maxItems) return;
    var clone = rowTemplate.content.cloneNode(true);
    rowsContainer.appendChild(clone);
    // Deliberately no patchRepeaterField() here, unlike remove/move: a
    // freshly added row is blank and has nothing meaningful to persist
    // yet — for families with a required sub-field (e.g. trust_features'
    // title), eagerly saving it would predictably fail on every single
    // "add" click, before the merchant has typed anything. The row is
    // saved naturally once its own change listener fires from an actual
    // edit; if the merchant never fills it in and navigates away, it is
    // simply never persisted, which is the correct outcome for a blank
    // template row.
  }

  R4.openSection = function (sectionId) {
    if (!inspector || !sectionId) return Promise.resolve();
    // Opening a Section Inspector always closes Global Design — the two
    // never show at once (Task 11 Section 22).
    closeGlobalDesign();
    var url = new URL('sections/' + sectionId + '/inspector/', window.location.href);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) {
        if (!response.ok) return null;
        return response.text();
      })
      .then(function (html) {
        if (html == null) return;
        inspector.innerHTML = html;
        inspector.hidden = false;
        if (shell) shell.dataset.r4InspectorOpen = 'true';
        R4.selected = sectionId;
        R4.inspectorOpen = true;
        activateTab('basic');
        // Hydrate the raw backing values (incl. the rich_text textarea)
        // BEFORE Alpine mounts CKEditor, so it initializes from the real
        // current body_html rather than an empty source element.
        hydrateFieldValues();
        // Alpine 3's own MutationObserver auto-initializes x-data elements
        // added anywhere in the document (verified against this build) —
        // it already mounts storefrontRichTextEditor()'s CKEditor here.
        // Do NOT also call Alpine.initTree(): doing so double-mounts.
      })
      .catch(function () {
        // Network/render failure opening the Inspector — no R3 fallback,
        // no popup; the shell simply stays as it already was.
      });
  };

  function closeInspector() {
    if (!inspector) return;
    inspector.hidden = true;
    inspector.innerHTML = '';
    if (shell) shell.dataset.r4InspectorOpen = 'false';
    R4.selected = null;
    R4.inspectorOpen = false;
  }

  if (inspector) {
    // One delegated field-change path — no per-section save handler.
    inspector.addEventListener('click', function (evt) {
      var tabButton = evt.target.closest('[data-r4-tab]');
      if (tabButton) {
        activateTab(tabButton.getAttribute('data-r4-tab'));
        return;
      }
      var closeButton = evt.target.closest('[data-r4-inspector-close]');
      if (closeButton) { closeInspector(); return; }
      // R4 Task 10 — the ONE generic open control on a resource_source
      // field row; identical for product_section and brand_carousel, no
      // Product/Brand-specific handler.
      var pickerOpenButton = evt.target.closest('[data-r4-resource-picker-open]');
      if (pickerOpenButton) {
        var pickerFieldWrapper = pickerOpenButton.closest('[data-r4-field-key]');
        R4.openResourcePicker(pickerFieldWrapper);
      }
      // R4 Task 6 (Group D) — repeater row add/remove/reorder: plain DOM
      // operations (clone the hidden <template> row, remove a row element,
      // swap two adjacent row elements), never Alpine reactive state — see
      // the comment in settings_field.html's repeater branch. Each action
      // immediately re-collects and patches (no native 'change' event fires
      // for a removed/reordered/cloned row on its own).
      var repeaterAddButton = evt.target.closest('[data-r4-repeater-add]');
      if (repeaterAddButton) {
        var addWrapper = repeaterAddButton.closest('[data-r4-field-type="repeater"]');
        if (addWrapper) addRepeaterRow(addWrapper);
        return;
      }
      var repeaterRemoveButton = evt.target.closest('[data-r4-repeater-remove]');
      if (repeaterRemoveButton) {
        var removeWrapper = repeaterRemoveButton.closest('[data-r4-field-type="repeater"]');
        var removeRow = repeaterRemoveButton.closest('[data-r4-repeater-row]');
        if (removeWrapper && removeRow) {
          removeRow.remove();
          patchRepeaterField(removeWrapper);
        }
        return;
      }
      var repeaterMoveUpButton = evt.target.closest('[data-r4-repeater-move-up]');
      if (repeaterMoveUpButton) {
        var moveUpWrapper = repeaterMoveUpButton.closest('[data-r4-field-type="repeater"]');
        var moveUpRow = repeaterMoveUpButton.closest('[data-r4-repeater-row]');
        var prevRow = moveUpRow && moveUpRow.previousElementSibling;
        if (moveUpWrapper && moveUpRow && prevRow) {
          moveUpRow.parentNode.insertBefore(moveUpRow, prevRow);
          patchRepeaterField(moveUpWrapper);
        }
        return;
      }
      var repeaterMoveDownButton = evt.target.closest('[data-r4-repeater-move-down]');
      if (repeaterMoveDownButton) {
        var moveDownWrapper = repeaterMoveDownButton.closest('[data-r4-field-type="repeater"]');
        var moveDownRow = repeaterMoveDownButton.closest('[data-r4-repeater-row]');
        var nextRow = moveDownRow && moveDownRow.nextElementSibling;
        if (moveDownWrapper && moveDownRow && nextRow) {
          moveDownRow.parentNode.insertBefore(nextRow, moveDownRow);
          patchRepeaterField(moveDownWrapper);
        }
        return;
      }
    });

    inspector.addEventListener('change', function (evt) {
      var control = evt.target.closest('[data-r4-field-key]');
      if (!control || R4.selected == null) return;
      var fieldType = control.getAttribute('data-r4-field-type');
      // repeater (R4 Task 6 Group D): a row's sub-input has no
      // data-r4-field-key of its own, but `.closest()` still reaches the
      // repeater wrapper div, which does carry one — without this
      // exclusion every row edit would ALSO fire here with a bogus
      // `undefined`-valued patch racing the real one from the dedicated
      // repeater listener below.
      // CKEditor mounts over the rich_text textarea (aria-hidden, no
      // direct user interaction) — its save path is the dedicated
      // focusout handler below, not this native 'change' listener.
      // appearance_override is a compound field with its own dedicated
      // listener below too.
      if (fieldType === 'rich_text' || fieldType === 'appearance_override' || fieldType === 'repeater') return;
      var key = control.getAttribute('data-r4-field-key');
      var value = fieldType === 'boolean' ? control.checked : control.value;
      var patch = {};
      patch[key] = value;
      var sectionId = R4.selected;
      var isVariantChange = key === 'display_mode';
      var promise = R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: sectionId,
        patch: patch,
      });
      // Phase 3 (V02) — re-open the Inspector after a successful variant
      // change so server-authoritative control visibility (e.g. brand_carousel
      // "مشاهده همه", offered only for grid/carousel) reflects the new state;
      // dormant stored values stay untouched (read-side refresh only).
      if (isVariantChange) {
        promise.then(function (result) {
          if (result && result.ok) R4.openSection(sectionId);
        });
      }
    });

    // appearance_override: one compound patch per change, built from the
    // widget's three nested controls — never a raw JSON/CSS input, never a
    // new endpoint.
    inspector.addEventListener('change', function (evt) {
      var wrapper = evt.target.closest('[data-r4-field-type="appearance_override"]');
      if (!wrapper || R4.selected == null) return;
      if (!evt.target.closest('[data-r4-appearance-enabled],[data-r4-appearance-font],[data-r4-appearance-type-scale]')) return;
      var key = wrapper.getAttribute('data-r4-field-key');
      var enabledInput = wrapper.querySelector('[data-r4-appearance-enabled]');
      var fontSelect = wrapper.querySelector('[data-r4-appearance-font]');
      var scaleSelect = wrapper.querySelector('[data-r4-appearance-type-scale]');
      var enabled = Boolean(enabledInput && enabledInput.checked);
      if (fontSelect) fontSelect.disabled = !enabled;
      if (scaleSelect) scaleSelect.disabled = !enabled;

      var typography = { enabled: enabled };
      if (enabled) {
        if (fontSelect) typography.font = fontSelect.value;
        if (scaleSelect) typography.type_scale = scaleSelect.value;
      }
      var patch = {};
      patch[key] = { typography: typography };
      R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: R4.selected,
        patch: patch,
      });
    });

    // R4 Task 6 (Group D) — repeater: any edit inside an existing row
    // (typing into a text input, toggling a checkbox, picking a choice)
    // re-collects every row and sends ONE compound patch, exactly like
    // appearance_override's own dedicated listener above.
    inspector.addEventListener('change', function (evt) {
      var wrapper = evt.target.closest('[data-r4-field-type="repeater"]');
      if (!wrapper || R4.selected == null) return;
      if (!evt.target.closest('[data-r4-repeater-subfield]')) return;
      patchRepeaterField(wrapper);
    });

    // Rich text: enqueue one patch only when focus genuinely LEAVES the
    // whole CKEditor wrapper (not on every keystroke, not when focus just
    // moves between the toolbar and the editable area within it).
    inspector.addEventListener('focusout', function (evt) {
      var richEditorWrapper = evt.target.closest('.sfb-rich-editor');
      if (!richEditorWrapper || R4.selected == null) return;
      if (evt.relatedTarget && richEditorWrapper.contains(evt.relatedTarget)) return;
      var textarea = richEditorWrapper.querySelector('[data-r4-field-key]');
      if (!textarea) return;
      var key = textarea.getAttribute('data-r4-field-key');
      var patch = {};
      patch[key] = textarea.value;
      R4.enqueueMutation({
        type: 'section.update_settings',
        section_id: R4.selected,
        patch: patch,
      });
    });
  }

  // ---- R4 Task 8 — Structure panel: one delegated click handler for
  // select/move/duplicate/remove/add, bound to the stable container so it
  // keeps working after refreshStructureAndPreview() replaces the panel's
  // innerHTML (delegation, never re-bound per row).
  if (structurePanel) {
    structurePanel.addEventListener('click', function (evt) {
      var moveBtn = evt.target.closest('[data-r4-structure-move]');
      if (moveBtn) {
        if (moveBtn.disabled) return;
        var moveRow = moveBtn.closest('[data-r4-structure-row]');
        if (!moveRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.move',
          section_id: Number(moveRow.getAttribute('data-r4-structure-section-id')),
          direction: moveBtn.getAttribute('data-r4-structure-move'),
        });
        return;
      }
      var duplicateBtn = evt.target.closest('[data-r4-structure-duplicate]');
      if (duplicateBtn) {
        var duplicateRow = duplicateBtn.closest('[data-r4-structure-row]');
        if (!duplicateRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.duplicate',
          section_id: Number(duplicateRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var removeBtn = evt.target.closest('[data-r4-structure-remove]');
      if (removeBtn) {
        if (removeBtn.disabled) return;
        var removeRow = removeBtn.closest('[data-r4-structure-row]');
        if (!removeRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.remove',
          section_id: Number(removeRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var toggleActiveBtn = evt.target.closest('[data-r4-structure-toggle-active]');
      if (toggleActiveBtn) {
        var toggleActiveRow = toggleActiveBtn.closest('[data-r4-structure-row]');
        if (!toggleActiveRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.toggle_active',
          section_id: Number(toggleActiveRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var toggleLockedBtn = evt.target.closest('[data-r4-structure-toggle-locked]');
      if (toggleLockedBtn) {
        var toggleLockedRow = toggleLockedBtn.closest('[data-r4-structure-row]');
        if (!toggleLockedRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.toggle_locked',
          section_id: Number(toggleLockedRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var resetToBaselineBtn = evt.target.closest('[data-r4-structure-reset-to-baseline]');
      if (resetToBaselineBtn) {
        if (resetToBaselineBtn.disabled) return;
        var resetRow = resetToBaselineBtn.closest('[data-r4-structure-row]');
        if (!resetRow) return;
        R4.enqueueStructuralMutation({
          type: 'section.reset_to_baseline',
          section_id: Number(resetRow.getAttribute('data-r4-structure-section-id')),
        });
        return;
      }
      var resetPageBtn = evt.target.closest('#r4ResetPageButton');
      if (resetPageBtn) {
        if (!window.confirm('این صفحه به ترکیبِ اولیه‌یِ قالب بازنشانی می‌شود — بخش‌هایِ دستیِ همین صفحه هم از بین می‌روند. ادامه می‌دهید؟')) return;
        R4.queue = (R4.queue || Promise.resolve()).then(function () {
          return sendReplaceDraftAction('reset-page/', { page_type: shell ? shell.dataset.r4PageType : 'home' });
        });
        R4.queue.then(function (result) {
          if (result && result.ok) window.location.reload();
        });
        return;
      }
      var addBtn = evt.target.closest('#r4StructureAddButton');
      if (addBtn) {
        var addSelect = structurePanel.querySelector('#r4StructureAddSelect');
        var sectionKey = addSelect ? addSelect.value : '';
        if (!sectionKey) return;
        // Phase 4 (Task 3B) — every section.add mutation must name its
        // target page explicitly; read from the shell's own data attribute
        // (server-rendered from the SAME validated page_type the current
        // editor load resolved — never re-derived/guessed client-side).
        R4.enqueueStructuralMutation({
          type: 'section.add',
          section_key: sectionKey,
          page_type: shell ? shell.dataset.r4PageType : 'home',
        });
        if (addSelect) addSelect.value = '';
        return;
      }
      // R4 Task 7 (final-review fix, IMPORTANT-2) — one "add section" row
      // per EMPTY Cell (see editor.html), so a Cell created by
      // container.change_layout's grow branch is never a permanent dead
      // end. Same delegated-click shape as #r4StructureAddButton above.
      var emptyCellAddBtn = evt.target.closest('[data-r4-structure-empty-cell-add]');
      if (emptyCellAddBtn) {
        var emptyCellRow = emptyCellAddBtn.closest('[data-r4-structure-empty-cell]');
        if (!emptyCellRow) return;
        var emptyCellSelect = emptyCellRow.querySelector('[data-r4-structure-empty-cell-select]');
        var emptyCellSectionKey = emptyCellSelect ? emptyCellSelect.value : '';
        if (!emptyCellSectionKey) return;
        R4.enqueueStructuralMutation({
          type: 'cell.add_section',
          section_key: emptyCellSectionKey,
          cell_id: Number(emptyCellRow.getAttribute('data-r4-structure-cell-id')),
        });
        if (emptyCellSelect) emptyCellSelect.value = '';
        return;
      }
      // Pre-Task-10 remediation (composition parity closure) — move an
      // EXISTING section into any empty Cell (not just an adjacent swap),
      // same delegated-click shape as the empty-cell "add" button above.
      var moveToCellBtn = evt.target.closest('[data-r4-structure-move-to-cell]');
      if (moveToCellBtn) {
        var moveRow = moveToCellBtn.closest('[data-r4-structure-row]');
        if (!moveRow) return;
        var moveSelect = moveRow.querySelector('[data-r4-structure-move-to-cell-select]');
        var targetCellId = moveSelect ? moveSelect.value : '';
        if (!targetCellId) return;
        R4.enqueueStructuralMutation({
          type: 'section.move_to_cell',
          section_id: Number(moveRow.getAttribute('data-r4-structure-section-id')),
          cell_id: Number(targetCellId),
        });
        if (moveSelect) moveSelect.value = '';
        return;
      }
      var label = evt.target.closest('.r4-structure-label');
      if (label) {
        var labelRow = label.closest('[data-r4-structure-row]');
        if (!labelRow) return;
        R4.openSection(Number(labelRow.getAttribute('data-r4-structure-section-id')));
      }
    });

    // R4 Task 7 (Batch 1) — multi-column composition: one <select> per
    // Container (rendered once per distinct container_id — see editor.html)
    // choosing among the SAME LAYOUT_PRESETS keys the legacy layout-preset
    // picker already offers. Delegated the same way as every other
    // Structure panel control, so it keeps working after
    // refreshStructureAndPreview() replaces the panel's innerHTML.
    structurePanel.addEventListener('change', function (evt) {
      var layoutSelect = evt.target.closest('[data-r4-structure-layout-select]');
      if (layoutSelect) {
        var containerRow = layoutSelect.closest('[data-r4-structure-container-row]');
        if (!containerRow) return;
        R4.enqueueStructuralMutation({
          type: 'container.change_layout',
          container_id: Number(containerRow.getAttribute('data-r4-structure-container-id')),
          layout_key: layoutSelect.value,
        });
        return;
      }
      // Pre-Task-10 remediation (composition parity closure) — one Container
      // settings field change posts ONE key, same shape as the Global
      // Design panel's per-field change handler above.
      var settingsField = evt.target.closest('[data-r4-container-settings-field]');
      if (settingsField) {
        var settingsRow = settingsField.closest('[data-r4-structure-container-row]');
        if (!settingsRow) return;
        var settingsKey = settingsField.getAttribute('data-r4-container-settings-field');
        var settingsPatch = {};
        settingsPatch[settingsKey] = settingsField.value;
        R4.enqueueStructuralMutation({
          type: 'container.update_settings',
          container_id: Number(settingsRow.getAttribute('data-r4-structure-container-id')),
          patch: settingsPatch,
        });
      }
    });
  }

  // ---- R4 Task 10 — the ONE shared Resource Picker lifecycle for both
  // Product and Brand. One state object (R4.resourcePicker), one fetch
  // endpoint (resources/picker/), one apply path (the existing Task 5
  // R4.enqueueMutation queue) — never a per-kind picker/component/endpoint.
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function pickerFetchUrl(kind, query, selectedIds) {
    var url = new URL('resources/picker/', window.location.href);
    url.searchParams.set('kind', kind);
    if (query) url.searchParams.set('q', query);
    selectedIds.forEach(function (id) { url.searchParams.append('selected', String(id)); });
    return url;
  }

  function pickerAllowedAutoRules() {
    var rules = [];
    if (!pickerRoot) return rules;
    pickerRoot.querySelectorAll('[data-r4-picker-auto-rule]').forEach(function (button) {
      rules.push(button.getAttribute('data-r4-picker-auto-rule'));
    });
    return rules;
  }

  function pickerHasValidSelection() {
    var state = R4.resourcePicker;
    if (!state) return false;
    if (state.mode === 'manual') return state.selectedIds.length > 0;
    if (state.mode === 'auto') return pickerAllowedAutoRules().indexOf(state.autoRule) !== -1;
    return false;
  }

  function updatePickerApplyEnabled() {
    if (!pickerRoot) return;
    var applyButton = pickerRoot.querySelector('[data-r4-picker-apply]');
    if (applyButton) applyButton.disabled = !pickerHasValidSelection();
  }

  function buildPickerSelectedRowHTML(item) {
    return (
      '<div class="r4-picker-row r4-picker-row--selected" data-r4-picker-selected-item '
      + 'data-r4-picker-item-id="' + item.id + '" '
      + 'data-r4-picker-item-label="' + escapeHtml(item.label) + '" '
      + 'data-r4-picker-item-sublabel="' + escapeHtml(item.sublabel || '') + '">'
      + '<span class="r4-picker-row-label">' + escapeHtml(item.label) + '</span>'
      + '<span class="r4-picker-row-sublabel">' + escapeHtml(item.sublabel || '') + '</span>'
      + '<span class="r4-picker-row-actions">'
      + '<button type="button" data-r4-picker-move="up" aria-label="جابه‌جایی به بالا">↑</button>'
      + '<button type="button" data-r4-picker-move="down" aria-label="جابه‌جایی به پایین">↓</button>'
      + '<button type="button" data-r4-picker-remove aria-label="حذف">✕</button>'
      + '</span></div>'
    );
  }

  function renderPickerSelectedList() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return;
    var listEl = pickerRoot.querySelector('#r4PickerSelectedList');
    if (!listEl) return;
    if (state.selectedIds.length === 0) {
      listEl.innerHTML = '<p class="r4-picker-empty" data-r4-picker-selected-empty-hint>هنوز چیزی انتخاب نشده است.</p>';
    } else {
      listEl.innerHTML = state.selectedIds.map(function (id) {
        var item = state.itemCache[id] || { id: id, label: String(id), sublabel: '' };
        return buildPickerSelectedRowHTML(item);
      }).join('');
    }
    var countEl = pickerRoot.querySelector('[data-r4-picker-selected-count]');
    if (countEl) countEl.textContent = String(state.selectedIds.length);
    updatePickerApplyEnabled();
  }

  function syncPickerModeUI() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return;
    var activeTabName = state.mode === 'manual' ? 'manual' : (state.mode === 'auto' ? 'auto' : null);
    pickerRoot.querySelectorAll('[data-r4-picker-mode]').forEach(function (tabButton) {
      var isActive = tabButton.getAttribute('data-r4-picker-mode') === activeTabName;
      tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    pickerRoot.querySelectorAll('[data-r4-picker-panel]').forEach(function (panel) {
      var name = panel.getAttribute('data-r4-picker-panel');
      var show = state.mode === 'manual' ? name === 'manual' : name === 'auto';
      if (show) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
    });
    var allowedRules = pickerAllowedAutoRules();
    pickerRoot.querySelectorAll('[data-r4-picker-auto-rule]').forEach(function (ruleButton) {
      var isActive = ruleButton.getAttribute('data-r4-picker-auto-rule') === state.autoRule;
      ruleButton.classList.toggle('r4-picker-auto-rule--active', isActive);
      ruleButton.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    // Task 9's typed Product auto rules (by_category/by_brand/by_collection)
    // are preserved but not directly editable here (Section 17) — surfaced
    // as read-only info, never silently replaced by opening/closing.
    var currentNote = pickerRoot.querySelector('[data-r4-picker-auto-current]');
    if (currentNote) {
      if (state.mode === 'auto' && state.autoRule && allowedRules.indexOf(state.autoRule) === -1) {
        currentNote.hidden = false;
        currentNote.textContent = 'این بخش هم‌اکنون از یک قانون خودکار دیگر استفاده می‌کند که در این پنجره قابل تغییر مستقیم نیست. برای تغییر، حالت دستی یا یکی از گزینه‌های بالا را انتخاب کنید.';
      } else {
        currentNote.hidden = true;
      }
    }
    updatePickerApplyEnabled();
  }

  function closeResourcePicker() {
    if (!pickerRoot) return;
    pickerRoot.hidden = true;
    pickerRoot.innerHTML = '';
    R4.resourcePicker = null;
  }

  function refreshPickerResults() {
    var state = R4.resourcePicker;
    if (!state || !pickerRoot) return Promise.resolve();
    var url = pickerFetchUrl(state.kind, state.query, state.selectedIds);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var freshDoc = new DOMParser().parseFromString(html, 'text/html');
        var freshResults = freshDoc.getElementById('r4PickerResults');
        var currentResults = pickerRoot.querySelector('#r4PickerResults');
        if (freshResults && currentResults) {
          currentResults.innerHTML = freshResults.innerHTML;
          currentResults.querySelectorAll('[data-r4-picker-item-id]').forEach(function (el) {
            var id = Number(el.getAttribute('data-r4-picker-item-id'));
            state.itemCache[id] = {
              id: id,
              label: el.getAttribute('data-r4-picker-item-label'),
              sublabel: el.getAttribute('data-r4-picker-item-sublabel'),
            };
          });
        }
      })
      .catch(function () {
        // A failed search refresh leaves the previous results visible —
        // never treated as "nothing found", never retried automatically.
      });
  }

  function buildResourceSourcePayload() {
    var state = R4.resourcePicker;
    if (!state) return null;
    if (state.mode === 'manual') {
      if (!state.selectedIds.length) return null;
      return {
        kind: state.kind, mode: 'manual', auto_rule: null, auto_parameters: {},
        manual_ids: state.selectedIds.slice(),
      };
    }
    if (state.mode === 'auto' && pickerAllowedAutoRules().indexOf(state.autoRule) !== -1) {
      return { kind: state.kind, mode: 'auto', auto_rule: state.autoRule, auto_parameters: {}, manual_ids: [] };
    }
    return null;
  }

  function applyResourcePicker() {
    var state = R4.resourcePicker;
    var payload = buildResourceSourcePayload();
    if (!state || !payload) return Promise.resolve();
    var sectionId = R4.selected;
    var patch = {};
    patch[state.fieldKey] = payload;
    // The ONE Section write remains the existing Task 5 mutation queue —
    // the Picker has no save endpoint/form of its own.
    return R4.enqueueMutation({
      type: 'section.update_settings',
      section_id: sectionId,
      patch: patch,
    }).then(function (result) {
      if (result && result.ok) {
        closeResourcePicker();
        if (previewFrame && previewFrame.contentWindow) {
          previewFrame.contentWindow.location.reload();
        }
        // Re-open the Inspector so its summary comes back from the
        // server-authoritative legacy -> ResourceSource projection —
        // never reconstructed client-side.
        return R4.openSection(sectionId);
      }
      // Controlled 400/409/network failure — overlay stays open, nothing
      // is pretended to be saved; the existing save-state/conflict
      // handling in R4.sendMutation already governs what happens next.
      return result;
    });
  }

  R4.openResourcePicker = function (fieldWrapper) {
    if (!fieldWrapper || !pickerRoot || R4.selected == null) return Promise.resolve();
    var fieldKey = fieldWrapper.getAttribute('data-r4-field-key');
    var script = document.getElementById('r4InspectorFieldValues');
    var values = {};
    if (script) {
      try { values = JSON.parse(script.textContent) || {}; } catch (err) { values = {}; }
    }
    // The CURRENT typed ResourceSource, already projected server-side
    // (Task 9) from the real legacy Section.settings — never reconstructed
    // from visible Persian summary text.
    var current = values[fieldKey] || {};
    if (!current.kind) return Promise.resolve();

    R4.resourcePicker = {
      fieldKey: fieldKey,
      kind: current.kind,
      mode: current.mode === 'manual' ? 'manual' : 'auto',
      autoRule: current.auto_rule || null,
      autoParameters: current.auto_parameters || {},
      selectedIds: (current.manual_ids || []).slice(),
      itemCache: {},
      maxItems: 0,
      query: '',
    };

    var url = pickerFetchUrl(current.kind, '', R4.resourcePicker.selectedIds);
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.ok ? response.text() : null; })
      .then(function (html) {
        if (html == null || !R4.resourcePicker) return;
        pickerRoot.innerHTML = html;
        pickerRoot.hidden = false;
        var maxItemsEl = pickerRoot.querySelector('[data-r4-picker-max-items]');
        R4.resourcePicker.maxItems = maxItemsEl ? Number(maxItemsEl.textContent) || 0 : 0;
        pickerRoot.querySelectorAll('[data-r4-picker-item-id]').forEach(function (el) {
          var id = Number(el.getAttribute('data-r4-picker-item-id'));
          R4.resourcePicker.itemCache[id] = {
            id: id,
            label: el.getAttribute('data-r4-picker-item-label'),
            sublabel: el.getAttribute('data-r4-picker-item-sublabel'),
          };
        });
        syncPickerModeUI();
        var searchInput = pickerRoot.querySelector('[data-r4-picker-search]');
        if (searchInput) searchInput.focus();
      })
      .catch(function () {
        closeResourcePicker();
      });
  };

  if (pickerRoot) {
    pickerRoot.addEventListener('input', function (evt) {
      var searchInput = evt.target.closest('[data-r4-picker-search]');
      if (!searchInput || !R4.resourcePicker) return;
      R4.resourcePicker.query = searchInput.value;
      if (pickerSearchTimer) clearTimeout(pickerSearchTimer);
      pickerSearchTimer = setTimeout(refreshPickerResults, 300);
    });

    pickerRoot.addEventListener('click', function (evt) {
      if (evt.target.closest('[data-r4-picker-close]') || evt.target.closest('[data-r4-picker-cancel]')) {
        closeResourcePicker();
        return;
      }
      var modeTab = evt.target.closest('[data-r4-picker-mode]');
      if (modeTab && R4.resourcePicker) {
        R4.resourcePicker.mode = modeTab.getAttribute('data-r4-picker-mode');
        syncPickerModeUI();
        return;
      }
      var ruleButton = evt.target.closest('[data-r4-picker-auto-rule]');
      if (ruleButton && R4.resourcePicker) {
        R4.resourcePicker.mode = 'auto';
        R4.resourcePicker.autoRule = ruleButton.getAttribute('data-r4-picker-auto-rule');
        syncPickerModeUI();
        return;
      }
      var addButton = evt.target.closest('[data-r4-picker-add]');
      if (addButton && R4.resourcePicker) {
        var state = R4.resourcePicker;
        if (state.selectedIds.length >= state.maxItems) return;
        var addId = Number(addButton.getAttribute('data-r4-picker-item-id'));
        if (state.selectedIds.indexOf(addId) !== -1) return;
        state.itemCache[addId] = {
          id: addId,
          label: addButton.getAttribute('data-r4-picker-item-label'),
          sublabel: addButton.getAttribute('data-r4-picker-item-sublabel'),
        };
        state.selectedIds.push(addId);
        state.mode = 'manual';
        renderPickerSelectedList();
        syncPickerModeUI();
        return;
      }
      var removeButton = evt.target.closest('[data-r4-picker-remove]');
      if (removeButton && R4.resourcePicker) {
        var removeRow = removeButton.closest('[data-r4-picker-selected-item]');
        if (!removeRow) return;
        var removeId = Number(removeRow.getAttribute('data-r4-picker-item-id'));
        R4.resourcePicker.selectedIds = R4.resourcePicker.selectedIds.filter(function (v) { return v !== removeId; });
        renderPickerSelectedList();
        return;
      }
      var moveButton = evt.target.closest('[data-r4-picker-move]');
      if (moveButton && R4.resourcePicker) {
        var moveRow = moveButton.closest('[data-r4-picker-selected-item]');
        if (!moveRow) return;
        var moveId = Number(moveRow.getAttribute('data-r4-picker-item-id'));
        var ids = R4.resourcePicker.selectedIds;
        var idx = ids.indexOf(moveId);
        var swapWith = moveButton.getAttribute('data-r4-picker-move') === 'up' ? idx - 1 : idx + 1;
        if (idx === -1 || swapWith < 0 || swapWith >= ids.length) return;
        var tmp = ids[idx];
        ids[idx] = ids[swapWith];
        ids[swapWith] = tmp;
        renderPickerSelectedList();
        return;
      }
      if (evt.target.closest('[data-r4-picker-apply]')) {
        applyResourcePicker();
      }
    });
  }

  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Escape' && pickerRoot && !pickerRoot.hidden) {
      closeResourcePicker();
    }
  });

  // ---- Preview selection compatibility bridge (see Task 6 finding):
  // a normal click on a Preview section currently only ever reaches
  // sfb:openSectionSettings (interceptBuilderEditClick's capture-phase
  // stopImmediatePropagation prevents sfb:selectSection for that same
  // click) — both are accepted and routed to the same openSection().
  //
  // R4 Task 8 mapped the shared Preview toolbar's existing
  // sfb:sectionCommand/sfb:blockCommand messages for duplicate/remove/up/
  // down. R4 Task 7 (Batch 1) extends this to the two commands Task 8 left
  // deliberately unhandled — toggle (enable/disable) and lock — now that
  // real mutation types (section.toggle_active/section.toggle_locked) exist
  // for them; cellCommand/containerCommand remain out of scope (multi-block
  // Cell CRUD is not part of this batch's placement model).
  window.addEventListener('message', function (evt) {
    if (evt.origin !== window.location.origin) return;
    if (!previewFrame || evt.source !== previewFrame.contentWindow) return;
    if (!evt.data) return;
    var type = evt.data.type;
    if (type === 'sfb:selectSection' || type === 'sfb:openSectionSettings') {
      var sectionId = evt.data.sectionId;
      if (!sectionId) return;
      R4.openSection(Number(sectionId));
      return;
    }
    if (type === 'sfb:sectionCommand') {
      var sectionCommandId = evt.data.sectionId;
      if (!sectionCommandId) return;
      if (evt.data.command === 'duplicate') {
        R4.enqueueStructuralMutation({ type: 'section.duplicate', section_id: Number(sectionCommandId) });
      } else if (evt.data.command === 'remove') {
        R4.enqueueStructuralMutation({ type: 'section.remove', section_id: Number(sectionCommandId) });
      } else if (evt.data.command === 'toggle') {
        R4.enqueueStructuralMutation({ type: 'section.toggle_active', section_id: Number(sectionCommandId) });
      } else if (evt.data.command === 'lock') {
        R4.enqueueStructuralMutation({ type: 'section.toggle_locked', section_id: Number(sectionCommandId) });
      }
      return;
    }
    if (type === 'sfb:blockCommand') {
      var blockCommandId = evt.data.sectionId;
      if (!blockCommandId) return;
      if (evt.data.command === 'up' || evt.data.command === 'down') {
        R4.enqueueStructuralMutation({
          type: 'section.move', section_id: Number(blockCommandId), direction: evt.data.command,
        });
      } else if (evt.data.command === 'remove') {
        R4.enqueueStructuralMutation({ type: 'section.remove', section_id: Number(blockCommandId) });
      }
    }
  });

  // ---- R4 Task 11 — Global Design (appearance/header/footer selection),
  // Undo/Redo, and Publish. Global Design edits go through the EXISTING
  // R4.enqueueMutation queue (same as every Section edit); Undo/Redo/
  // Publish are not shaped like a mutation, but still serialize behind
  // the SAME R4.queue — never a second/independent queue of their own.
  function closeGlobalDesign() {
    if (!globalDesignPanel) return;
    globalDesignPanel.hidden = true;
    if (globalDesignToggle) globalDesignToggle.setAttribute('aria-expanded', 'false');
    if (shell) shell.dataset.r4GlobalDesignOpen = 'false';
  }

  function openGlobalDesign() {
    if (!globalDesignPanel) return;
    closeInspector();
    globalDesignPanel.hidden = false;
    if (globalDesignToggle) globalDesignToggle.setAttribute('aria-expanded', 'true');
    if (shell) shell.dataset.r4GlobalDesignOpen = 'true';
  }

  if (globalDesignToggle) {
    globalDesignToggle.addEventListener('click', function () {
      if (globalDesignPanel && globalDesignPanel.hidden) openGlobalDesign();
      else closeGlobalDesign();
    });
  }

  if (globalDesignPanel) {
    globalDesignPanel.addEventListener('click', function (evt) {
      if (evt.target.closest('[data-r4-global-design-close]')) closeGlobalDesign();

      // R4 Task 7 (Batch 2) — one reset icon per appearance field, keyed
      // off the SAME ``data-r4-global-reset-field`` attribute value as the
      // field's own patch key (``appearance.reset_setting_to_baseline``'s
      // ``key`` param) — never a second per-field mapping to maintain.
      var resetFieldBtn = evt.target.closest('[data-r4-global-reset-field]');
      if (resetFieldBtn) {
        R4.enqueueMutation({
          type: 'appearance.reset_setting_to_baseline',
          key: resetFieldBtn.getAttribute('data-r4-global-reset-field'),
        }).then(function (result) {
          if (result && result.ok) refreshGlobalDesignAndPreview();
        });
        return;
      }
      if (evt.target.closest('#r4ResetHeaderButton')) {
        R4.enqueueMutation({ type: 'header.reset_to_baseline' }).then(function (result) {
          if (result && result.ok) refreshGlobalDesignAndPreview();
        });
        return;
      }
      if (evt.target.closest('#r4ResetFooterButton')) {
        R4.enqueueMutation({ type: 'footer.reset_to_baseline' }).then(function (result) {
          if (result && result.ok) refreshGlobalDesignAndPreview();
        });
        return;
      }
      // R4 Task 7 (final-review fix, IMPORTANT-1) — MUST be delegated
      // (evt.target.closest, not a direct listener bound once at load):
      // #r4ResetStorefrontButton lives inside #r4GlobalDesign, whose
      // innerHTML refreshGlobalDesignAndPreview() replaces on every OTHER
      // successful Global Design edit above — a directly-bound listener
      // on the original node would silently stop firing after the very
      // first such edit. Reset-storefront REPLACES the Draft's identity
      // (like Discard/Publish), so it still needs its own confirm +
      // sendReplaceDraftAction + reload, unlike the in-place resets above.
      if (evt.target.closest('#r4ResetStorefrontButton')) {
        if (!window.confirm('کل ظاهر فروشگاه (همه‌یِ صفحاتِ پوشش‌داده‌شده، هدر، فوتر، ظاهر) به قالب بازنشانی می‌شود. ادامه می‌دهید؟')) return;
        R4.queue = (R4.queue || Promise.resolve()).then(function () {
          return sendReplaceDraftAction('reset-storefront/');
        });
        R4.queue.then(function (result) {
          if (result && result.ok) window.location.reload();
        });
        return;
      }
      // R4 Task 8 (Batch 1) — same delegation requirement as
      // #r4ResetStorefrontButton just above: #r4SwitchTemplateButton
      // lives inside #r4GlobalDesign too. Content-preserving Template
      // Switch REPLACES the Draft's identity (a fresh checkpoint clone —
      // see preset_service.switch_template_preserving_content), so it
      // needs the same confirm + sendReplaceDraftAction + reload shape,
      // never an in-place R4.enqueueMutation.
      if (evt.target.closest('#r4SwitchTemplateButton')) {
        var templateSelect = document.getElementById('r4TemplateSwitchSelect');
        if (!templateSelect || !templateSelect.value) return;
        var selectedOption = templateSelect.options[templateSelect.selectedIndex];
        var templateVersion = selectedOption ? selectedOption.getAttribute('data-r4-template-version') : null;
        if (!templateVersion) return;
        if (!window.confirm('ظاهرِ این قالب (پالت، هدر، فوتر، طراحیِ کلی) اعمال می‌شود — محتوایِ بخش‌های موجود دست‌نخورده می‌ماند. ادامه می‌دهید؟')) return;
        R4.queue = (R4.queue || Promise.resolve()).then(function () {
          return sendReplaceDraftAction('switch-template/', {
            template_key: templateSelect.value,
            template_version: templateVersion,
          });
        });
        R4.queue.then(function (result) {
          if (result && result.ok) window.location.reload();
        });
      }
    });

    // One delegated change handler — the mutation `type` and patch `key`
    // both come from data attributes already rendered by the server
    // (section_registry/appearance_registry/global_region_registry), so
    // Product/appearance/header/footer never need their own JS branch.
    globalDesignPanel.addEventListener('change', function (evt) {
      var field = evt.target.closest('[data-r4-global-field]');
      if (!field) return;
      var group = field.closest('[data-r4-global-mutation]');
      if (!group) return;
      var key = field.getAttribute('data-r4-global-field');
      // Pre-Task-10 remediation — a checkbox's own ``.value`` is always the
      // string "on" regardless of checked state; every new boolean toggle
      // field (header/footer show_*, sticky, announcement_enabled/
      // show_phone, card_image_crossfade/zoom) needs the real ``.checked``
      // state instead, exactly like the section Inspector's own generic
      // boolean field handling.
      var value = field.type === 'checkbox' ? field.checked : field.value;
      if (key === 'palette_slug' && value === '') value = null;
      var patch = {};
      // Pre-Task-10 remediation — color_overrides/theme_overrides are
      // compound (dict-shaped) appearance_config keys: one color/theme
      // input still fires exactly one change event, but must post a
      // ONE-KEY PARTIAL patch of the dict (never the whole 8-key set),
      // matching ``_apply_appearance_update``'s merge-onto-current
      // semantics server-side.
      if (key === 'color_overrides' || key === 'theme_overrides') {
        var subKeyAttr = key === 'color_overrides' ? 'data-r4-global-color-key' : 'data-r4-global-theme-key';
        var subKey = field.getAttribute(subKeyAttr);
        if (!subKey) return;
        var nested = {};
        nested[subKey] = value;
        patch[key] = nested;
      } else {
        patch[key] = value;
      }
      R4.enqueueMutation({
        type: group.getAttribute('data-r4-global-mutation'),
        patch: patch,
      }).then(function (result) {
        if (result && result.ok) refreshGlobalDesignAndPreview();
      });
    });
  }

  // Same "GET the R4 editor + DOMParser + swap one element's innerHTML"
  // technique Task 8's refreshStructureAndPreview() already established —
  // reused here for the Global Design panel's own server-authoritative
  // read projection (e.g. a Template switch resetting font/type_scale).
  function refreshGlobalDesignAndPreview() {
    if (previewFrame && previewFrame.contentWindow) {
      previewFrame.contentWindow.location.reload();
    }
    if (!globalDesignPanel) return Promise.resolve();
    return fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var freshDoc = new DOMParser().parseFromString(html, 'text/html');
        var freshPanel = freshDoc.getElementById('r4GlobalDesign');
        if (freshPanel) globalDesignPanel.innerHTML = freshPanel.innerHTML;
      })
      .catch(function () {
        // The mutation itself already succeeded — a failed read-side
        // refresh just leaves the panel showing its pre-change values
        // until the merchant's next action.
      });
  }

  // ---- Undo/Redo: a dedicated command sender (not a `mutation` payload)
  // that still updates R4.revision/save-state/conflict exactly like
  // R4.sendMutation, and is still serialized behind the SAME R4.queue.
  function sendHistoryCommand(command) {
    if (R4.conflict) return Promise.resolve();
    setSaveState('saving');
    var url = new URL('history/', window.location.href);
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({ base_revision: R4.revision, command: command }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { status: response.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status === 200 && result.body && result.body.ok) {
          R4.revision = result.body.new_revision;
          if (shell) shell.dataset.editRevision = String(R4.revision);
          setSaveState('saved');
          return result.body;
        }
        if (result.status === 409) {
          R4.conflict = true;
          setSaveState('conflict');
          showConflictBanner();
          return result.body;
        }
        setSaveState('error');
        return result.body;
      })
      .catch(function () {
        setSaveState('error');
      });
  }

  if (undoButton) {
    undoButton.addEventListener('click', function () {
      R4.queue = (R4.queue || Promise.resolve()).then(function () {
        return sendHistoryCommand('undo');
      });
      R4.queue.then(function (result) {
        // A restored Draft may change sections/containers/appearance/
        // header/footer all at once — a full reload is the deliberate,
        // non-fragile choice (Task 11 Section 21), never a partial
        // fake re-render of a whole restored Draft.
        if (result && result.ok && result.changed) window.location.reload();
      });
    });
  }

  if (redoButton) {
    redoButton.addEventListener('click', function () {
      R4.queue = (R4.queue || Promise.resolve()).then(function () {
        return sendHistoryCommand('redo');
      });
      R4.queue.then(function (result) {
        if (result && result.ok && result.changed) window.location.reload();
      });
    });
  }

  // ---- Publish/Discard/Reset-page/Reset-storefront: all four REPLACE the
  // Draft's identity (a new/deleted version, never an in-place edit), so
  // none of them go through R4.enqueueStructuralMutation's "refresh in
  // place" contract — each shares this ONE fetch shape (same queue, same
  // current R4.revision, same conflict/error handling), and the caller
  // reloads the whole page on success, exactly like Undo/Redo already do
  // for the same reason (Section 21).
  function sendReplaceDraftAction(pathSegment, extraBody) {
    if (R4.conflict) return Promise.resolve();
    setSaveState('saving');
    var url = new URL(pathSegment, window.location.href);
    var body = Object.assign({ base_revision: R4.revision }, extraBody || {});
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        return response.json().then(function (responseBody) {
          return { status: response.status, body: responseBody };
        });
      })
      .then(function (result) {
        if (result.status === 200 && result.body && result.body.ok) {
          setSaveState('saved');
          return result.body;
        }
        if (result.status === 409) {
          R4.conflict = true;
          setSaveState('conflict');
          showConflictBanner();
          return result.body;
        }
        setSaveState('error');
        return result.body;
      })
      .catch(function () {
        setSaveState('error');
      });
  }

  function sendPublish() {
    return sendReplaceDraftAction('publish/');
  }

  if (publishButton) {
    publishButton.addEventListener('click', function () {
      R4.queue = (R4.queue || Promise.resolve()).then(function () {
        return sendPublish();
      });
      R4.queue.then(function (result) {
        // A successful Publish must not continue editing the now-Published
        // Draft — reload so the normal R4 GET resolves/creates the NEXT
        // Draft through the existing layout_service.get_or_create_draft
        // lifecycle (never manually cloned/created here).
        if (result && result.ok) window.location.reload();
      });
    });
  }

  if (discardButton) {
    discardButton.addEventListener('click', function () {
      if (!window.confirm('پیش‌نویسِ فعلی رد می‌شود و همه‌ی تغییراتِ منتشرنشده از بین می‌رود. ادامه می‌دهید؟')) return;
      R4.queue = (R4.queue || Promise.resolve()).then(function () {
        return sendReplaceDraftAction('discard/');
      });
      R4.queue.then(function (result) {
        if (result && result.ok) window.location.reload();
      });
    });
  }

  // Pre-Task-10 remediation (R4 live cutover) — the dashboard nav's
  // ``?panel=appearance``/``?panel=header``/``?panel=footer`` deep links
  // (base_admin.html, unchanged by the cutover) now point at R4 instead of
  // the legacy editor; open the Global Design panel automatically so that
  // link still lands the merchant on the right screen instead of the bare
  // Preview.
  if (globalDesignPanel) {
    var deepLinkPanel = new URLSearchParams(window.location.search).get('panel');
    if (deepLinkPanel === 'appearance' || deepLinkPanel === 'header' || deepLinkPanel === 'footer') {
      openGlobalDesign();
    }
  }

})();
