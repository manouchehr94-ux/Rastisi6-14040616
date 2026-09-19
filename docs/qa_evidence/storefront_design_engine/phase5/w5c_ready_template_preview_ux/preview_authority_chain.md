# W5C — Preview Authority Chain

```
layout_preset_registry.list_ready_templates()      (UNCHANGED — 50 presets)
    -> storefront_template_gallery()                (UNCHANGED view/context)
    -> template_gallery.html card triggers           (NEW: 2 data-attribute
                                                        URLs + a label per
                                                        card, all built
                                                        server-side via
                                                        {% url %})
    -> ONE shared dialog + ONE <iframe>               (NEW markup)
    -> template_gallery_preview.js                    (NEW, small,
                                                        presentation-only
                                                        controller)
    -> storefront_template_live_preview()             (UNCHANGED route/
                                                        logic — ONE line
                                                        added:
                                                        @xframe_options_
                                                        sameorigin, see
                                                        below)
    -> preset_service.resolve_preset_candidate()      (UNCHANGED)
    -> build_candidate_render_items /
       build_candidate_container_rows /
       store_appearance_global_renderer_template      (UNCHANGED — the
                                                        SAME shared
                                                        renderer every
                                                        other candidate-
                                                        rendering path in
                                                        this codebase uses)
    -> ready_template_live_preview.html               (UNCHANGED)
```

No parallel authority is introduced anywhere in this chain.

## The one production-logic change, and why it was necessary

`storefront_template_live_preview` gained exactly one decorator:
`@xframe_options_sameorigin`. Independent code review (`code-review`
skill, high effort) flagged that without it, Django's global
`X-Frame-Options: DENY` default (no override — the same default every
other view in this codebase gets, `XFrameOptionsMiddleware`'s own
fallback) would make every browser refuse to render this view inside the
new in-page `<iframe>`, even same-origin — the dialog would open but the
iframe would stay blank for all 50 templates, in both data modes. This is
not a new pattern: `storefront_preview` (the view R4's own preview
iframe already loads) carries the exact same decorator for the exact same
reason, documented in that view's own docstring. W5C's dialog is simply
the second legitimate consumer of "render this view inside an iframe on
an authenticated admin page" — the fix mirrors the existing precedent
byte-for-byte rather than inventing a new clickjacking-exception pattern.

No other line of `storefront_template_live_preview`, `storefront_template_
gallery`, `preset_service`, or `layout_service` changed. `git diff --stat`
for `views.py` confirms 8 lines added (the decorator + its docstring
justification), 0 removed, 0 changed elsewhere in the file.

## Device presentation contract (shared by convention, not by runtime state)

| | R4 (`r4_editor.js`) | Gallery (`template_gallery_preview.js`) |
|---|---|---|
| Desktop width | 1200 (natural, no scale) | 1200 (natural, no scale) |
| Tablet width | 768 | 768 |
| Mobile width | 390 | 390 |
| Technique | fixed iframe width + `transform: scale()` | fixed iframe width + `transform: scale()` |
| State storage | in-memory closure var (`currentDevice`) | in-memory closure var (`state.device`) |
| Persistence | none | none |
| Data attributes | `data-desktop/tablet/mobile-viewport-width` on the iframe | same names, same values, own iframe |

These are two independent implementations agreeing on a design constant,
not a shared runtime authority — each owns its own DOM references, its
own in-memory state, and its own iframe. See the implementation plan's
§11 for the full reuse-vs-duplication reasoning (why extracting a shared
module was judged higher-risk than independent reimplementation for this
phase).

## No second route, renderer, or mutation type

- Grep confirms zero new `path(...)` entries in `apps/dashboard/urls.py`
  for anything preview-related.
- Grep confirms zero new templates under
  `storefront_builder/partials/` or `storefront_builder/` for rendering
  candidate sections — `ready_template_live_preview.html` is untouched.
- Grep confirms zero new `type:` mutation strings anywhere in
  `template_gallery_preview.js` — the file makes no `fetch()`/`POST` call
  at all; it only ever sets `<iframe>.src` (a GET navigation) to one of
  the two server-supplied canonical URLs.
- The existing Apply `<form>` (`action="{% url 'dashboard:storefront-
  builder-apply-preset' %}"`) is unmodified.
