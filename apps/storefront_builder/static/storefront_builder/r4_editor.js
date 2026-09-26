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
  // Phase 5 Task 4C — device preview switcher + the canvas the SAME
  // #r4PreviewFrame iframe is scaled within. UI-only state, never persisted.
  var deviceSwitcher = document.querySelector('[data-r4-device-switcher]');
  var previewCanvas = document.querySelector('.r4-preview-canvas');
  var undoButton = document.getElementById('r4UndoButton');
  var redoButton = document.getElementById('r4RedoButton');
  var publishButton = document.getElementById('r4PublishButton');

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
    saved: 'پیش‌نویس ذخیره شد',
    saving: 'در حال ذخیره…',
    error: 'ذخیره ناموفق',
    conflict: 'تعارض نسخه',
  };

  // Design Studio — R4 announces its own state changes as DOM events on the
  // shell so the UI-only presentation layer (r4_studio.js) can follow them
  // without ever owning or duplicating business state.
  R4.emit = function (name, detail) {
    if (!shell) return;
    shell.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  };

  // Lifecycle confirmations (reset page/storefront, discard) go through ONE
  // hook the presentation layer may replace with the workspace dialog; the
  // default stays the browser confirm so R4 works without the Studio layer.
  R4.confirm = function (message) {
    return Promise.resolve(window.confirm(message));
  };

  function setSaveState(state) {
    R4.saveState = state;
    if (saveStateEl) saveStateEl.textContent = SAVE_STATE_LABELS[state] || '';
    R4.emit('r4:savestate', { state: state });
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
        R4.emit('r4:structure-refreshed');
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

  // One section-level structural command entry point (Studio inspector
  // actions + the preview toolbar bridge). Each command maps to exactly one
  // existing canonical mutation type through the SAME structural queue.
  var SECTION_COMMAND_TYPES = {
    up: 'section.move',
    down: 'section.move',
    duplicate: 'section.duplicate',
    remove: 'section.remove',
    toggle_active: 'section.toggle_active',
    toggle_locked: 'section.toggle_locked',
    reset_to_baseline: 'section.reset_to_baseline',
    move_to_cell: 'section.move_to_cell',
  };
  R4.sectionCommand = function (sectionId, command, extra) {
    var type = SECTION_COMMAND_TYPES[command];
    if (!type || !sectionId) return Promise.resolve();
    var mutation = { type: type, section_id: Number(sectionId) };
    if (command === 'up' || command === 'down') mutation.direction = command;
    if (command === 'move_to_cell') mutation.cell_id = Number(extra && extra.cellId);
    return R4.enqueueStructuralMutation(mutation);
  };
  R4.addSection = function (sectionKey, cellId) {
    if (!sectionKey) return Promise.resolve();
    if (cellId) {
      return R4.enqueueStructuralMutation({ type: 'cell.add_section', section_key: sectionKey, cell_id: Number(cellId) });
    }
    return R4.enqueueStructuralMutation({
      type: 'section.add',
      section_key: sectionKey,
      page_type: shell ? shell.dataset.r4PageType : 'home',
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
      // Phase 5 Task 4B — background is a compound widget too, entirely
      // server-rendered from the current value (its nested controls carry
      // their own selected/value already), so it is excluded from this
      // scalar loop exactly like the other compound field types.
      if (fieldType === 'appearance_override' || fieldType === 'resource_source' || fieldType === 'repeater' || fieldType === 'background') return;
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

  // Pre-Task-10 final remediation (Gap 1) — the Global Design panel's own
  // repeater patch sender: same collectRepeaterRows()/addRepeaterRow() the
  // Section Inspector's repeater field type already uses above (R4 Task 6
  // Group D) — only the mutation destination differs (header.update/
  // footer.update instead of section.update_settings, and no section_id),
  // so header announcement_links/extra_blocks and footer extra_blocks are
  // the SAME compound repeater concept, never a second implementation.
  function patchGlobalRepeaterField(wrapper) {
    var group = wrapper.closest('[data-r4-global-mutation]');
    if (!group) return;
    var key = wrapper.getAttribute('data-r4-global-repeater-field');
    var patch = {};
    patch[key] = collectRepeaterRows(wrapper);
    R4.enqueueMutation({
      type: group.getAttribute('data-r4-global-mutation'),
      patch: patch,
    }).then(function (result) {
      if (result && result.ok) refreshGlobalDesignAndPreview();
    });
  }

  // Phase 5 Task 4D — post the current R4 selection into the EXISTING
  // preview iframe so the same Section highlights there. Never a second
  // selection authority (reads R4.selected only) and never a reimplementation
  // of the highlight — the preview template already owns applying it. The
  // message shape/type mirror the legacy editor's own outbound selection
  // sync exactly; origin-targeted, never "*".
  function syncPreviewSelection() {
    // A null selection clears the preview highlight (Inspector closed).
    if (!previewFrame || !previewFrame.contentWindow) return;
    previewFrame.contentWindow.postMessage({
      type: 'sfb:setSelection',
      sectionId: R4.selected,
    }, window.location.origin);
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
        // Phase 5 Task 4 (remediation R1a) — the Inspector body can embed the
        // canonical media manager, whose add/edit/toggle/delete/reorder
        // controls are htmx-driven. htmx does NOT auto-bind content injected
        // via innerHTML, so process the injected subtree once here to activate
        // those existing endpoints inline (reuses the htmx already loaded by
        // base_admin.html — never a second binding mechanism). Guarded so a
        // build without htmx simply no-ops.
        if (window.htmx && typeof window.htmx.process === 'function') {
          window.htmx.process(inspector);
        }
        if (shell) shell.dataset.r4InspectorOpen = 'true';
        R4.selected = sectionId;
        R4.inspectorOpen = true;
        // Phase 5 Task 4D — sidebar/structure -> preview selection sync.
        // openSection is the single selection entry point (a sidebar row
        // click, and the preview-originated sfb:selectSection/
        // sfb:openSectionSettings, all route through here), so posting the
        // canonical selection into the EXISTING preview iframe once here
        // covers every path without a second selected-section state. The
        // preview template already applies this as its highlight — R4 never
        // reimplements that logic. Uses the existing section identity;
        // targeted to this window's origin.
        syncPreviewSelection();
        activateTab('basic');
        R4.emit('r4:inspector-opened', { sectionId: sectionId });
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
    syncPreviewSelection();
    R4.emit('r4:inspector-closed');
  }
  R4.closeInspector = closeInspector;

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
      // 'background' (Task 4B) is compound too — handled by its own listener.
      if (fieldType === 'rich_text' || fieldType === 'appearance_override' || fieldType === 'repeater' || fieldType === 'background') return;
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

    // Phase 5 Task 4B — background: a compound widget like
    // appearance_override above. Any change to any of its nested controls
    // (mode/color/palette-role/pattern/media) re-reads ALL of them and sends
    // ONE compound {background:{...}} patch through the SAME enqueueMutation
    // queue and the SAME section.update_settings mutation every other section
    // edit uses — never a second save path and never a new endpoint. The
    // media options come from the shared Store-scoped Media Library; ownership
    // of a chosen media_asset_id stays enforced at render time
    // (content.services.resolve_background_media_url), so the client only ever
    // sends an id, never a raw URL.
    inspector.addEventListener('change', function (evt) {
      var wrapper = evt.target.closest('[data-r4-field-type="background"]');
      if (!wrapper || R4.selected == null) return;
      if (!evt.target.closest('[data-r4-background-mode],[data-r4-background-color],[data-r4-background-palette-role],[data-r4-background-pattern],[data-r4-background-media]')) return;
      var key = wrapper.getAttribute('data-r4-field-key');
      var modeSelect = wrapper.querySelector('[data-r4-background-mode]');
      var colorInput = wrapper.querySelector('[data-r4-background-color]');
      var paletteSelect = wrapper.querySelector('[data-r4-background-palette-role]');
      var patternSelect = wrapper.querySelector('[data-r4-background-pattern]');
      var mediaSelect = wrapper.querySelector('[data-r4-background-media]');

      var background = { mode: modeSelect ? modeSelect.value : 'theme' };
      if (colorInput) background.color = colorInput.value;
      if (paletteSelect) background.palette_role = paletteSelect.value;
      if (patternSelect) background.pattern_slug = patternSelect.value;
      var mediaValue = mediaSelect ? mediaSelect.value : '';
      background.media_asset_id = mediaValue ? Number(mediaValue) : null;

      var patch = {};
      patch[key] = background;
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
        R4.confirm('این صفحه به ترکیبِ اولیه‌یِ قالب بازنشانی می‌شود — بخش‌هایِ دستیِ همین صفحه هم از بین می‌روند. ادامه می‌دهید؟').then(function (confirmed) {
          if (!confirmed) return;
          R4.queue = (R4.queue || Promise.resolve()).then(function () {
            return sendReplaceDraftAction('reset-page/', { page_type: shell ? shell.dataset.r4PageType : 'home' });
          });
          R4.queue.then(function (result) {
            if (result && result.ok) window.location.reload();
          });
        });
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
        return;
      }
      // Pre-Task-10 final remediation (independent review finding) —
      // Container background: mode + color are sent TOGETHER on any change
      // to either (not the single-key patch the generic handler above
      // sends), because the server partial-merges a patch onto the CURRENT
      // saved settings and effective_container_settings() rejects
      // mode="color" with no color yet set (or a color with mode still
      // "transparent") by silently reverting to "transparent" — see the
      // comment in r4/editor.html's own background markup. background_pattern
      // is always sent as the same single fixed value the legacy form's own
      // hidden field uses (never a merchant-facing pattern choice, never a
      // new pattern registry UI); harmless when mode isn't "pattern" since
      // the server only reads it in that case.
      var backgroundField = evt.target.closest('[data-r4-container-background-field]');
      if (backgroundField) {
        var backgroundWrapper = backgroundField.closest('[data-r4-container-background]');
        var backgroundRow = backgroundField.closest('[data-r4-structure-container-row]');
        if (!backgroundWrapper || !backgroundRow) return;
        var modeField = backgroundWrapper.querySelector('[data-r4-container-background-field="background_mode"]');
        var colorField = backgroundWrapper.querySelector('[data-r4-container-background-field="background_color"]');
        R4.enqueueStructuralMutation({
          type: 'container.update_settings',
          container_id: Number(backgroundRow.getAttribute('data-r4-structure-container-id')),
          patch: {
            background_mode: modeField ? modeField.value : 'transparent',
            background_color: colorField ? colorField.value : '',
            background_pattern: 'commerce-doodle',
          },
        });
      }
    });
  }

  // ---- Add section. The chooser (full page-legal library + the Phase 5
  // Task 6 Showcase facade) is rendered by the server into the Structure
  // panel and presented by the Studio as a workspace dialog, so this ONE
  // delegated listener is bound on the shell (it survives both the dialog
  // and refreshStructureAndPreview() replacing the panel's innerHTML).
  if (shell) {
    shell.addEventListener('click', function (evt) {
      var addBtn = evt.target.closest('#r4StructureAddButton');
      if (addBtn) {
        var addScope = addBtn.closest('[data-r4-add-section]') || structurePanel;
        var addSelect = addScope ? addScope.querySelector('#r4StructureAddSelect') : null;
        var sectionKey = addSelect ? addSelect.value : '';
        if (!sectionKey) return;
        // Phase 4 (Task 3B) — every section.add mutation must name its
        // target page explicitly; read from the shell's own data attribute
        // (server-rendered from the SAME validated page_type the current
        // editor load resolved — never re-derived/guessed client-side).
        R4.enqueueStructuralMutation({
          type: 'section.add',
          section_key: sectionKey,
          page_type: shell.dataset.r4PageType || 'home',
        });
        if (addSelect) addSelect.value = '';
        return;
      }
      // Phase 5 Task 6 — Storefront Showcase creation FACADE. A Showcase choice
      // carries ONLY a canonical section_key (data-section-key); it reuses the
      // exact same section.add path as #r4StructureAddButton above — no new
      // mutation type, no direct fetch, no pseudo Showcase section key.
      var showcaseChoice = evt.target.closest('[data-r4-showcase-choice]');
      if (showcaseChoice) {
        var showcaseKey = showcaseChoice.getAttribute('data-section-key');
        if (!showcaseKey) return;
        R4.enqueueStructuralMutation({
          type: 'section.add',
          section_key: showcaseKey,
          page_type: shell.dataset.r4PageType || 'home',
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
    // While the SAME iframe shows a transient surface (a Design Lab candidate
    // or a Ready Template live preview) its sections are not the Draft's
    // editable targets, so edit commands from it are ignored.
    if (R4.previewInteractive === false) return;
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
    var wasOpen = !globalDesignPanel.hidden;
    globalDesignPanel.hidden = true;
    if (globalDesignToggle) globalDesignToggle.setAttribute('aria-expanded', 'false');
    if (shell) shell.dataset.r4GlobalDesignOpen = 'false';
    if (wasOpen) R4.emit('r4:global-closed');
  }

  function openGlobalDesign() {
    if (!globalDesignPanel) return;
    closeInspector();
    globalDesignPanel.hidden = false;
    if (globalDesignToggle) globalDesignToggle.setAttribute('aria-expanded', 'true');
    if (shell) shell.dataset.r4GlobalDesignOpen = 'true';
    R4.emit('r4:global-opened');
  }

  // The Studio top navigation («طراحی سراسری», #r4GlobalDesignToggle) is a
  // workspace-mode switch owned by the presentation layer; it calls these
  // two entry points, so ONE click reaches ONE open/close operation.
  R4.openGlobalDesign = openGlobalDesign;
  R4.closeGlobalDesign = closeGlobalDesign;
  R4.isGlobalDesignOpen = function () {
    return Boolean(globalDesignPanel && !globalDesignPanel.hidden);
  };

  var THEME_NONE_KEY = 'theme.none.v1';

  function applyTheme(componentKey) {
    var themeDraftId = Number(shell && shell.dataset.r4DraftId);
    if (!componentKey || !themeDraftId) return Promise.resolve();
    // No Theme -> canonical Clear (never a no-op selection with a
    // meaningless intensity; the server also normalizes, this keeps the wire
    // payload honest).
    var mutation;
    if (componentKey === THEME_NONE_KEY) {
      mutation = { type: 'theme.clear', draft_id: themeDraftId };
    } else {
      var intensitySelect = globalDesignPanel && globalDesignPanel.querySelector('[data-r4-theme-intensity]');
      mutation = {
        type: 'theme.apply',
        draft_id: themeDraftId,
        component_key: componentKey,
        intensity: intensitySelect ? intensitySelect.value : 'balanced',
      };
    }
    return R4.enqueueMutation(mutation).then(function (result) {
      if (result && result.ok) return refreshGlobalDesignAndPreview().then(function () { return result; });
      return result;
    });
  }

  if (globalDesignPanel) {
    globalDesignPanel.addEventListener('click', function (evt) {
      if (evt.target.closest('[data-r4-global-design-close]')) closeGlobalDesign();

      // P5-W2 — reversible occasion Theme. A Theme change carries a component
      // selection AND a bounded intensity, plus an explicit Clear, so it needs
      // its own branch (the generic single-scalar data-r4-global-field handler
      // cannot express it). Every route goes through the ONE mutation boundary
      // (R4.enqueueMutation -> apply_mutation) exactly like every other edit.
      var themeApplyButton = evt.target.closest('[data-r4-theme-apply]');
      if (themeApplyButton) {
        applyTheme(themeApplyButton.getAttribute('data-r4-theme-apply'));
        return;
      }
      if (evt.target.closest('[data-r4-theme-clear]')) {
        applyTheme(THEME_NONE_KEY);
        return;
      }

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
        R4.confirm('کل ظاهر فروشگاه (همه‌یِ صفحاتِ پوشش‌داده‌شده، هدر، فوتر، ظاهر) به قالب بازنشانی می‌شود. ادامه می‌دهید؟').then(function (confirmed) {
          if (!confirmed) return;
          R4.queue = (R4.queue || Promise.resolve()).then(function () {
            return sendReplaceDraftAction('reset-storefront/');
          });
          R4.queue.then(function (result) {
            if (result && result.ok) window.location.reload();
          });
        });
      }
    });

    // Changing the intensity of the active occasion re-applies that SAME
    // occasion with the new intensity (one theme.apply mutation).
    globalDesignPanel.addEventListener('change', function (evt) {
      if (!evt.target.closest('[data-r4-theme-intensity]')) return;
      var activeTheme = globalDesignPanel.querySelector('[data-r4-theme-apply][aria-pressed="true"]');
      if (activeTheme) applyTheme(activeTheme.getAttribute('data-r4-theme-apply'));
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

    // Pre-Task-10 final remediation (Gap 1) — header announcement_links/
    // extra_blocks and footer extra_blocks repeaters: distinct
    // ``data-r4-global-repeater-field`` (not ``data-r4-global-field``) so a
    // row's own subfield inputs never get misread by the generic single-
    // scalar-field listener above, exactly like the Inspector's own
    // exclusion of fieldType 'repeater' from its generic listener.
    globalDesignPanel.addEventListener('click', function (evt) {
      var addButton = evt.target.closest('[data-r4-repeater-add]');
      if (addButton) {
        var addWrapper = addButton.closest('[data-r4-global-repeater-field]');
        if (addWrapper) addRepeaterRow(addWrapper);
        return;
      }
      var removeButton = evt.target.closest('[data-r4-repeater-remove]');
      if (removeButton) {
        var removeWrapper = removeButton.closest('[data-r4-global-repeater-field]');
        var removeRow = removeButton.closest('[data-r4-repeater-row]');
        if (removeWrapper && removeRow) {
          removeRow.remove();
          patchGlobalRepeaterField(removeWrapper);
        }
        return;
      }
      var moveUpButton = evt.target.closest('[data-r4-repeater-move-up]');
      if (moveUpButton) {
        var moveUpWrapper = moveUpButton.closest('[data-r4-global-repeater-field]');
        var moveUpRow = moveUpButton.closest('[data-r4-repeater-row]');
        var prevRow = moveUpRow && moveUpRow.previousElementSibling;
        if (moveUpWrapper && moveUpRow && prevRow) {
          moveUpRow.parentNode.insertBefore(moveUpRow, prevRow);
          patchGlobalRepeaterField(moveUpWrapper);
        }
        return;
      }
      var moveDownButton = evt.target.closest('[data-r4-repeater-move-down]');
      if (moveDownButton) {
        var moveDownWrapper = moveDownButton.closest('[data-r4-global-repeater-field]');
        var moveDownRow = moveDownButton.closest('[data-r4-repeater-row]');
        var nextRow = moveDownRow && moveDownRow.nextElementSibling;
        if (moveDownWrapper && moveDownRow && nextRow) {
          moveDownRow.parentNode.insertBefore(nextRow, moveDownRow);
          patchGlobalRepeaterField(moveDownWrapper);
        }
        return;
      }
    });

    globalDesignPanel.addEventListener('change', function (evt) {
      var repeaterWrapper = evt.target.closest('[data-r4-global-repeater-field]');
      if (repeaterWrapper && evt.target.closest('[data-r4-repeater-subfield]')) {
        patchGlobalRepeaterField(repeaterWrapper);
      }
    });

    // Pre-Task-10 final remediation (Gap 1) — header/footer responsive
    // hide-on-tablet/hide-on-mobile per-component toggles: a distinct
    // ``data-r4-global-responsive-toggle`` marker (not ``data-r4-global-
    // field``) because ONE checkbox only ever carries ONE of the two
    // ``responsive[key]`` sub-props — the server merges it onto the
    // CURRENT stored value (``_merge_shell_responsive_patch``), exactly
    // like color_overrides/theme_overrides' own one-key partial merge
    // above, so toggling tablet visibility can never silently reset the
    // sibling mobile visibility prop back to its default.
    globalDesignPanel.addEventListener('change', function (evt) {
      var responsiveToggle = evt.target.closest('[data-r4-global-responsive-toggle]');
      if (!responsiveToggle) return;
      var responsiveGroup = responsiveToggle.closest('[data-r4-global-mutation]');
      if (!responsiveGroup) return;
      var responsiveKey = responsiveToggle.getAttribute('data-r4-global-responsive-key');
      var responsiveProp = responsiveToggle.getAttribute('data-r4-global-responsive-prop');
      if (!responsiveKey || !responsiveProp) return;
      var nestedProp = {};
      nestedProp[responsiveProp] = responsiveToggle.checked;
      var responsivePatch = {};
      responsivePatch[responsiveKey] = nestedProp;
      R4.enqueueMutation({
        type: responsiveGroup.getAttribute('data-r4-global-mutation'),
        patch: { responsive: responsivePatch },
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
        R4.emit('r4:global-refreshed', { doc: freshDoc });
      })
      .catch(function () {
        // The mutation itself already succeeded — a failed read-side
        // refresh just leaves the panel showing its pre-change values
        // until the merchant's next action.
      });
  }

  R4.refreshGlobalDesignAndPreview = refreshGlobalDesignAndPreview;

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

  function runHistoryCommand(command) {
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return sendHistoryCommand(command);
    });
    return R4.queue.then(function (result) {
      R4.emit('r4:history', { command: command, result: result || null });
      // A restored Draft may change sections/containers/appearance/
      // header/footer all at once — a full reload is the deliberate,
      // non-fragile choice (Task 11 Section 21), never a partial
      // fake re-render of a whole restored Draft.
      if (result && result.ok && result.changed) window.location.reload();
      return result;
    });
  }
  R4.undo = function () { return runHistoryCommand('undo'); };
  R4.redo = function () { return runHistoryCommand('redo'); };

  if (undoButton) {
    undoButton.addEventListener('click', function () { R4.undo(); });
  }

  if (redoButton) {
    redoButton.addEventListener('click', function () { R4.redo(); });
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

  // Identity-replacing actions reload the workspace; a one-shot query flag
  // (read and removed by the Studio on load) only lets it announce what
  // happened. Nothing is stored anywhere.
  function reloadWithNotice(notice) {
    var next = new URL(window.location.href);
    next.searchParams.set('studio_notice', notice);
    window.location.replace(next.pathname + next.search);
  }

  // #r4PublishButton opens the Studio's publish confirmation; its confirm
  // button calls R4.publish() — ONE click path, ONE publish operation.
  R4.publish = function () {
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return sendPublish();
    });
    return R4.queue.then(function (result) {
      // A successful Publish must not continue editing the now-Published
      // Draft — reload so the normal R4 GET resolves/creates the NEXT
      // Draft through the existing layout_service.get_or_create_draft
      // lifecycle (never manually cloned/created here). The query flag
      // only lets the reloaded workspace announce the result.
      if (result && result.ok) reloadWithNotice('published');
      return result;
    });
  };

  R4.discard = function () {
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return sendReplaceDraftAction('discard/');
    });
    return R4.queue.then(function (result) {
      if (result && result.ok) reloadWithNotice('discarded');
      return result;
    });
  };

  // Content-preserving Ready Template switch (preset_service.
  // switch_template_preserving_content) REPLACES the Draft's identity, so it
  // uses the same replace-draft request + reload, never an in-place
  // R4.enqueueMutation. The exact key + version come from the server-rendered
  // template catalog the merchant picked from.
  R4.switchTemplate = function (templateKey, templateVersion) {
    if (!templateKey || !templateVersion) return Promise.resolve();
    R4.queue = (R4.queue || Promise.resolve()).then(function () {
      return sendReplaceDraftAction('switch-template/', {
        template_key: templateKey,
        template_version: String(templateVersion),
      });
    });
    return R4.queue.then(function (result) {
      if (result && result.ok) reloadWithNotice('template');
      return result;
    });
  };

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

  // ---- The ONE preview surface. #r4PreviewFrame normally renders the
  // editable Draft; a Design Lab candidate (?design_lab=<token>) or a Ready
  // Template live preview (non-destructive, ?data=merchant) is shown by
  // pointing the SAME iframe at that existing read-only route — never a
  // second iframe, never inline HTML documents, never a client-side renderer. Only the Draft
  // surface is interactive (its section clicks open the Inspector).
  R4.previewInteractive = true;
  R4.showPreview = function (url, options) {
    if (!previewFrame) return;
    var draftSrc = previewFrame.getAttribute('data-rs-draft-src') || previewFrame.getAttribute('src');
    var next = url || draftSrc;
    R4.previewInteractive = !url;
    previewFrame.setAttribute('data-rastisi-state', (options && options.state) || (url ? 'preview' : 'draft'));
    if (previewFrame.getAttribute('src') !== next) previewFrame.setAttribute('src', next);
    else if (options && options.reload && previewFrame.contentWindow) previewFrame.contentWindow.location.reload();
  };

  // ---- Phase 5 Task 4C — device preview (Desktop / Tablet / Mobile) + zoom.
  // The SAME #r4PreviewFrame iframe is rendered at the real device pixel
  // width and CSS-transform-scaled to fit the canvas (the approved Studio's
  // scalePreview rule) — it reuses the one existing preview surface, never a
  // second one. UI-only state (device, zoom) held in memory only: never
  // persisted to Store/Draft/browser storage, never sent through the queue.
  if (deviceSwitcher && previewFrame && previewCanvas) {
    var currentDevice = 'desktop';
    var currentZoom = 'width';
    var stageCanvas = previewCanvas.closest('.canvas') || previewCanvas.parentElement;
    var browserChrome = stageCanvas ? stageCanvas.querySelector('.browser-chrome') : null;

    function deviceWidth(device) {
      var widths = {
        desktop: parseInt(previewFrame.dataset.desktopViewportWidth, 10) || 1440,
        tablet: parseInt(previewFrame.dataset.tabletViewportWidth, 10) || 768,
        mobile: parseInt(previewFrame.dataset.mobileViewportWidth, 10) || 390,
      };
      return widths[device] || widths.desktop;
    }

    function syncPreviewViewport() {
      var requestedWidth = deviceWidth(currentDevice);
      var available = stageCanvas ? stageCanvas.clientWidth : previewCanvas.clientWidth;
      if (!available) return;
      var scale = Math.min(1, available / requestedWidth);
      if (currentDevice === 'desktop') {
        if (currentZoom === 'overview') scale = Math.min(scale, previewCanvas.clientHeight / 980);
        else if (currentZoom !== 'width') scale = Math.min(scale, Number(currentZoom) || 1);
      }
      var displayWidth = requestedWidth * scale;
      previewCanvas.style.maxWidth = displayWidth + 'px';
      if (browserChrome) browserChrome.style.maxWidth = displayWidth + 'px';
      previewFrame.style.width = requestedWidth + 'px';
      previewFrame.style.height = (previewCanvas.clientHeight / scale) + 'px';
      previewFrame.style.transform = 'scale(' + scale + ')';
    }
    R4.syncPreviewViewport = syncPreviewViewport;

    function setDevice(device) {
      if (['desktop', 'tablet', 'mobile'].indexOf(device) === -1) return;
      currentDevice = device;
      previewCanvas.setAttribute('data-r4-device', device);
      if (shell) shell.dataset.rsDevice = device;
      deviceSwitcher.querySelectorAll('[data-r4-device]').forEach(function (btn) {
        var active = btn.getAttribute('data-r4-device') === device;
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.classList.toggle('active', active);
      });
      syncPreviewViewport();
      R4.emit('r4:device', { device: device, width: deviceWidth(device) });
    }
    R4.setDevice = setDevice;
    R4.getDevice = function () { return currentDevice; };
    R4.setZoom = function (zoom) {
      currentZoom = zoom || 'width';
      syncPreviewViewport();
    };

    deviceSwitcher.addEventListener('click', function (evt) {
      var btn = evt.target.closest('[data-r4-device]');
      if (!btn) return;
      setDevice(btn.getAttribute('data-r4-device'));
    });

    if (window.ResizeObserver) {
      new ResizeObserver(function () { syncPreviewViewport(); }).observe(stageCanvas || previewCanvas);
    }
    window.addEventListener('resize', syncPreviewViewport);
    syncPreviewViewport();
  }

  // ---- P5-W3 — Design Lab / Random Mix (Studio experiment dock).
  // Transient experimentation surface. Candidates are computed SERVER-SIDE
  // (design_lab_service via the read-only /design-lab/ endpoint) and
  // previewed in the SAME #r4PreviewFrame iframe through the EXISTING
  // storefront_preview ?design_lab=<token> route. Nothing is saved until an
  // explicit Apply, which enqueues the ONE canonical
  // design_lab.apply_candidate mutation through the SAME R4.enqueueMutation
  // queue as every other edit. The client holds only the opaque signed
  // tokens + the transient locked-family set — no seed, no manifest, no
  // browser storage. The Studio layer renders this state; it never calls the
  // endpoint itself.
  (function initDesignLab() {
    if (!shell) return;
    var FAMILY_COUNT = 7;
    var DL = {
      active: false,
      busy: false,
      status: 'idle',          // idle | preview | generating | comparing | applying | stale | error
      error: null,             // last controlled error code
      token: null,             // opaque candidate token (server-issued)
      baseToken: null,         // token of the fixed experiment Base (candidate == Base)
      draftId: Number(shell.dataset.r4DraftId) || null,
      baseRevision: null,
      locked: [],              // transient locked family keys
      diffs: [],
      candidateLabels: {},
      baseLabels: {},
      compareBase: false,
    };

    function panel() { return document.querySelector('[data-r4-design-lab-panel]'); }

    function snapshot() {
      return {
        active: DL.active,
        busy: DL.busy,
        status: DL.status,
        error: DL.error,
        locked: DL.locked.slice(),
        diffs: DL.diffs.slice(),
        candidateLabels: Object.assign({}, DL.candidateLabels),
        baseLabels: Object.assign({}, DL.baseLabels),
        compareBase: DL.compareBase,
        stale: DL.status === 'stale',
        canApply: DL.active && !DL.busy && DL.status !== 'stale' && Boolean(DL.token) && DL.diffs.length > 0,
      };
    }

    function announce(extra) {
      var state = snapshot();
      var p = panel();
      if (p) p.setAttribute('data-rastisi-state', DL.active ? DL.status : 'idle');
      var applyButton = p && p.querySelector('[data-r4-design-lab-apply]');
      if (applyButton) applyButton.disabled = !state.canApply;
      R4.emit('r4:lab', Object.assign(state, extra || {}));
    }

    function tokenPreviewUrl(token) {
      var draftSrc = previewFrame ? (previewFrame.getAttribute('data-rs-draft-src') || previewFrame.getAttribute('src')) : '';
      var url = new URL(draftSrc, window.location.href);
      url.searchParams.set('page', shell.dataset.r4PageType || 'home');
      url.searchParams.set('design_lab', token);
      return url.pathname + url.search;
    }

    // Preview the Base or the current candidate in the EXISTING iframe.
    function syncLabPreview() {
      if (!DL.active) { R4.showPreview(null); return; }
      var token = DL.compareBase ? (DL.baseToken || DL.token) : DL.token;
      if (token) R4.showPreview(tokenPreviewUrl(token), { state: DL.compareBase ? 'base' : DL.status });
    }

    function adopt(body) {
      DL.token = body.token;
      DL.draftId = body.draft_id || DL.draftId;
      DL.baseRevision = body.base_revision;
      DL.diffs = body.diffs || [];
      DL.candidateLabels = body.candidate_labels || {};
      DL.baseLabels = body.base_labels || {};
    }

    function callDesignLab(action, extra, status) {
      var p = panel();
      if (!p || DL.busy) return Promise.resolve(null);
      var url = p.getAttribute('data-r4-design-lab-url');
      var body = {
        action: action,
        candidate_token: action === 'reset' ? null : DL.token,
        locked_families: DL.locked.slice(),
      };
      if (extra) Object.keys(extra).forEach(function (k) { body[k] = extra[k]; });
      DL.busy = true;
      DL.status = status || 'generating';
      DL.error = null;
      announce();
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(body),
      })
        .then(function (r) { return r.json().then(function (b) { return { status: r.status, body: b }; }); })
        .then(function (result) {
          DL.busy = false;
          if (result.status === 200 && result.body && result.body.ok) {
            adopt(result.body);
            DL.status = 'preview';
            DL.compareBase = false;
            return result.body;
          }
          DL.status = 'error';
          DL.error = (result.body && result.body.code) || 'request_failed';
          return null;
        })
        .catch(function () {
          DL.busy = false;
          DL.status = 'error';
          DL.error = 'network';
          return null;
        })
        .then(function (resultBody) {
          syncLabPreview();
          announce({ action: action, ok: Boolean(resultBody) });
          return resultBody;
        });
    }

    function begin() {
      // A fresh experiment always starts from the CURRENT committed Draft;
      // its first token is both the candidate and the fixed Base.
      DL.token = null;
      DL.baseToken = null;
      DL.locked = [];
      DL.diffs = [];
      DL.compareBase = false;
      DL.active = true;
      return callDesignLab('reset', null, 'generating').then(function (body) {
        if (body) DL.baseToken = body.token;
        else DL.active = Boolean(DL.token);
        announce();
        return body;
      });
    }

    function exit() {
      DL.active = false;
      DL.busy = false;
      DL.status = 'idle';
      DL.error = null;
      DL.token = null;
      DL.baseToken = null;
      DL.locked = [];
      DL.diffs = [];
      DL.candidateLabels = {};
      DL.baseLabels = {};
      DL.compareBase = false;
      R4.showPreview(null);
      announce();
    }

    // Apply: server-side materialise the canonical mutation from the current
    // signed token (which carries the candidate's generation revision), then
    // enqueue it through the SAME single mutation queue as every edit. The
    // /design-lab/ apply_payload preflight rejects a stale candidate (HTTP 409,
    // code=stale_candidate) BEFORE any mutation is produced; the canonical
    // mutate endpoint remains the final transactional stale-write enforcement.
    // A stale experiment is never rebased: the merchant restarts it.
    function applyCandidate() {
      var p = panel();
      if (!p || !DL.token || !DL.draftId || DL.busy || DL.status === 'stale') return Promise.resolve(null);
      var url = p.getAttribute('data-r4-design-lab-url');
      DL.busy = true;
      DL.status = 'applying';
      announce();
      function fail(status, code) {
        DL.busy = false;
        DL.status = status;
        DL.error = code;
        announce({ action: 'apply', ok: false });
        return null;
      }
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ action: 'apply_payload', candidate_token: DL.token }),
      })
        .then(function (r) { return r.json().then(function (body) { return { status: r.status, body: body }; }); })
        .then(function (res) {
          var body = res.body;
          if (res.status === 409 && body && body.code === 'stale_candidate') return fail('stale', 'stale_candidate');
          if (!body || !body.ok || !body.mutation) return fail('error', (body && body.code) || 'apply_failed');
          return R4.enqueueMutation(body.mutation).then(function (result) {
            if (result && result.ok) {
              // The transient experiment is gone the instant the canonical
              // mutation succeeds; success is announced only once the fresh
              // committed Global Design DOM is installed.
              exit();
              return refreshGlobalDesignAndPreview().then(function () {
                R4.emit('r4:lab-applied', { revision: R4.revision });
                return result;
              });
            }
            if (result && result.code === 'stale_revision') return fail('stale', 'stale_revision');
            return fail('error', (result && result.code) || 'apply_failed');
          });
        })
        .catch(function () { return fail('error', 'network'); });
    }

    R4.lab = {
      state: snapshot,
      isActive: function () { return DL.active; },
      start: begin,
      // Stale experiment: discard the old token and start again from the
      // newest Draft (never a silent rebase of the old candidate).
      restart: begin,
      exit: exit,
      randomMix: function () {
        if (!DL.active) return Promise.resolve(null);
        if (DL.locked.length >= FAMILY_COUNT) {
          announce({ notice: 'all_locked' });
          return Promise.resolve(null);
        }
        return callDesignLab('random_mix');
      },
      randomizeFamily: function (family) {
        if (!DL.active || DL.locked.indexOf(family) !== -1) return Promise.resolve(null);
        return callDesignLab('randomize_one', { family: family });
      },
      toggleLock: function (family) {
        if (!DL.active || DL.busy || !family) return;
        var at = DL.locked.indexOf(family);
        if (at === -1) DL.locked.push(family);
        else DL.locked.splice(at, 1);
        announce();
      },
      setTheme: function (componentKey, intensity) {
        if (!DL.active) return Promise.resolve(null);
        return callDesignLab('set_theme', { theme_component_key: componentKey, intensity: intensity });
      },
      removeTheme: function () {
        if (!DL.active) return Promise.resolve(null);
        return callDesignLab('remove_theme');
      },
      // «برگشت به شروع»: Candidate -> the fixed experiment Base, locks cleared.
      resetToBase: function () {
        if (!DL.active) return Promise.resolve(null);
        return callDesignLab('reset_to_base').then(function (body) {
          if (body) { DL.locked = []; announce(); }
          return body;
        });
      },
      // «بازگشت به سبک اولیه»: design families -> the exact current Ready
      // Template's DNA (Theme, locks and Base untouched; fails closed).
      returnToTemplateDna: function () {
        if (!DL.active) return Promise.resolve(null);
        return callDesignLab('return_to_template_dna');
      },
      showBase: function () {
        if (!DL.active) return;
        DL.compareBase = true;
        syncLabPreview();
        announce();
      },
      showCandidate: function () {
        if (!DL.active) return;
        DL.compareBase = false;
        syncLabPreview();
        announce();
      },
      apply: applyCandidate,
    };
  })();

})();
