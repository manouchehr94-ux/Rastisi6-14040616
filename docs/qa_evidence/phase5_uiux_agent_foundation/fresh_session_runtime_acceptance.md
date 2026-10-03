# Phase-5 UI/UX agent foundation — fresh-session runtime acceptance

- Date: 2026-09-11
- Purpose: The prior smoke test (`read_only_design_review_smoke_test.md`, same
  directory) was contaminated — it ran in the *same* session that had just
  configured `.claude/agents/rastisi-ui-ux-design-lead.md`, `.mcp.json`, and
  `.claude/settings.json`, so the harness had not (and could not, mid-session)
  hot-reload the new subagent type or MCP server. That session had to fake the
  custom-agent path via a `general-purpose` worker that manually read and adopted
  the persona file, and it never got a callable `mcp__chrome-devtools__*` tool at
  all. This document is the uncontaminated re-run: a genuinely fresh Claude Code
  session, checked out cold on `chore/phase5-uiux-agent-foundation`, verifying the
  same tooling actually registers and works at runtime — not just that the config
  files exist. **This document supersedes the prior file for every runtime-proof
  question below; the prior file is left as-is as a historical record of the
  contaminated attempt.**
- This is a QA/tooling verification exercise. **No storefront production code,
  template, CSS, JS, model, or migration was modified.** The only repository
  change made by this exercise is this evidence file itself.

Throughout this document, **CONFIGURED** means "present and declared in
`.claude/` or `.mcp.json`" — a static fact about the repo. **ACTUALLY LOADED /
CALLED** means "observed working at runtime in this session" — a real tool
invocation, a real transcript, a real screenshot. Only the latter is used to
justify a PASS in the final checklist.

---

## A. Custom subagent registration (`rastisi-ui-ux-design-lead`)

- **CONFIGURED**: `.claude/agents/rastisi-ui-ux-design-lead.md` is checked into
  the branch (confirmed present via `ls -la .claude/agents/`, 7168 bytes).
- **ACTUALLY LOADED**: At the very start of this session, before any file was
  read or any special action taken, the system's own agent-type listing (the
  `<system-reminder>` enumerating "Available agent types for the Agent tool")
  already included:

  > `rastisi-ui-ux-design-lead: RastiSi-specific Senior E-commerce UI/UX Design
  > Lead, Design-System Curator, and Visual QA Lead. ... (Tools: Read, Grep,
  > Glob, Bash, Skill, mcp__chrome-devtools)`

  This is exactly what a real, hot-registered custom subagent looks like on a
  cold session — no workaround, no manual persona adoption, no
  `general-purpose` stand-in was needed. The tool list shown
  (`Read, Grep, Glob, Bash, Skill, mcp__chrome-devtools`) matches the agent
  file's own `tools:` frontmatter, confirming the browser-tool grant is real
  and scoped to this one agent (see §D).
- This subagent was then actually dispatched (§D/§F below) via
  `Agent({subagent_type: "rastisi-ui-ux-design-lead", ...})` and ran to
  completion with 31 real tool calls in ~156 seconds. It is unambiguously a
  real, callable, registered subagent in this fresh session.

**Verdict: PASS.**

---

## B. `frontend-design` plugin (declared via `extraKnownMarketplaces` /
`enabledPlugins` in `.claude/settings.json`)

- **CONFIGURED**: `.claude/settings.json` declares
  `"extraKnownMarketplaces": {"claude-plugins-official": {"source": {"source":
  "github", "repo": "anthropics/claude-plugins-official"}, "autoUpdate":
  false}}` and `"enabledPlugins": {"frontend-design@claude-plugins-official":
  true}`. Confirmed present by reading the file directly in this session.
- **ACTUALLY LOADED**: Checked via the `ListPlugins` tool — "List the plugins
  enabled for this session" — twice: once filtered to keyword
  `"frontend-design"`, once with no filter at all (i.e. "list everything").
  Both calls returned `{"results": []}`.
- No trust/install prompt for the `claude-plugins-official` marketplace or the
  `frontend-design` plugin was shown at any point in this session — there was
  nothing to go through the "normal official Anthropic flow" for, because no
  prompt appeared. This session did not fabricate a workaround, vendor plugin
  content into the repo, or otherwise force it.
- This matches the prior (contaminated) session's own observation and rules
  out "it would have worked if the session weren't contaminated" as an
  explanation — a genuinely fresh session still does not auto-load a
  declared-but-not-yet-installed marketplace plugin. This is a real,
  reportable gap between "declared in settings" and "loaded," not a config
  mistake in this repo — `enabledPlugins` in settings is (per Claude Code's
  own model) the repo-level intent, but the actual install/trust step is a
  separate per-environment action this harness did not perform automatically
  for a plugin from an external marketplace.

**Verdict: FAIL** (genuinely not loaded — `ListPlugins` is authoritative and
returned empty both filtered and unfiltered).

---

## C. `chrome-devtools` MCP server (`.mcp.json`)

- **CONFIGURED**: `.mcp.json` pins `chrome-devtools-mcp@1.9.0`, run via `npx
  -y`, with `--headless --isolated --executablePath /opt/pw-browsers/chromium
  --chromeArg=--no-sandbox --no-usage-statistics --no-performance-crux`, and
  `env.CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`. Confirmed present by reading
  the file directly.
- Verified the pinned Chromium binary is still present in this cloud
  environment: `/opt/pw-browsers/chromium` is a symlink to
  `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, and the directory
  listing of `/opt/pw-browsers/` shows `chromium-1194/`,
  `chromium_headless_shell-1194/`, and `ffmpeg-1011/` all present.
- **ACTUALLY LOADED**: This session's own deferred-tools listing (the
  `<system-reminder>` enumerating tools available via `ToolSearch`) included,
  unprompted, at session start:
  `mcp__chrome-devtools__navigate_page`, `take_screenshot`, `emulate`,
  `resize_page`, `list_console_messages`, `take_snapshot`,
  `list_network_requests`, `evaluate_script`, `press_key`, `new_page`,
  `list_pages`, and the rest of the `chrome-devtools` tool family — i.e. the
  server registered and its tools were discoverable in a cold session, no
  restart or manual trust step needed.
- **ACTUALLY CALLED**: Not just discoverable — genuinely invoked, and not by
  this main session pretending on the agent's behalf, but by the
  `rastisi-ui-ux-design-lead` subagent itself (§D). 31 real tool calls
  succeeded end-to-end (see §D/§F transcript summary) with zero failures.

**Verdict: PASS.**

---

## D. The real `rastisi-ui-ux-design-lead` subagent calling chrome-devtools MCP
itself

This is the specific thing the prior (contaminated) session could not prove.
In this session:

- The `Agent` tool was invoked with `subagent_type:
  "rastisi-ui-ux-design-lead"` (not `general-purpose`, no manual persona
  adoption instruction).
- The dispatched agent's own transcript (returned via the task-notification
  on completion) shows it made these **real** MCP calls, in this order, all
  succeeding:
  `new_page` → `list_pages` → `resize_page(1440×900)` → `take_screenshot` →
  `resize_page(768×1024)` → `take_screenshot` → `resize_page(375×812)` →
  `take_screenshot` → `list_console_messages` → `take_snapshot` →
  `resize_page(1440×900)` → `evaluate_script` (×3, reading `dir`/`lang`,
  computed direction on the phone-number wrapper, computed badge colors) →
  `evaluate_script` (button bounding rects) → `press_key("Tab")` ×7 →
  `evaluate_script` (active element / outline) → `take_screenshot`
  (focus-ring check) → `list_network_requests` → `evaluate_script`
  (`prefers-reduced-motion` stylesheet scan).
- 31 total tool uses, 0 failures, ~156s duration (per the task-notification's
  own `<usage>` block).
- The agent explicitly reported: *"All tool calls succeeded; none failed or
  was unavailable. This was a genuine live run, no step was skipped or
  faked."*

**Verdict: PASS.**

---

## E. Starting the real RastiSi dev server (existing mechanisms only)

Investigated existing, documented run mechanisms before doing anything else:
no `README`, `Makefile`, or `docker-compose.yml` exist at the repo root; the
project is a plain Django app (`manage.py` at the root, `requirements.txt`,
`shop_core/settings.py`) with `.env.example` explicitly documenting: *"Local
development and the test suite need NONE of these set: every variable has a
safe default... falls back to a local SQLite file."* This is the project's own
documented local-dev path.

Steps actually taken, all using existing project mechanisms (no invented run
script):

1. `python3 -m venv .app-venv` (`.app-venv/` is already listed in `.gitignore`
   as the project's own recognized local-venv convention — not invented by
   this session) and `pip install -r requirements.txt` — installed cleanly.
2. `python manage.py migrate` — applied ~60 existing migrations across all
   apps (`core`, `customers`, `notifications`, `orders`, `portal`, `sms`,
   `storefront_builder`, `stores`, `subscriptions`, ...) against the SQLite
   fallback. All `OK`.
3. `python manage.py seed_shop` — an existing, idempotent management command
   ("پر می‌کند... داده‌ی نمونه‌ی جنریک" — fills the DB with generic sample
   data). Created 1 seller/store ("Akhlaghi", slug `akhlaghi`), 15 categories,
   5 brands, 15 products, 4 product images, 5 customers, 3 shipping methods,
   4 payment gateways, 4 discount codes, 6 sample orders, 4 blog posts.
4. `python manage.py runserver 0.0.0.0:8000` (`DJANGO_DEBUG=True`), run in the
   background. Log confirms: `System check identified no issues (0
   silenced).` / `Django version 5.2.17` / `Starting development server at
   http://0.0.0.0:8000/`.
5. Verified live: `curl http://localhost:8000/products/` returned `HTTP 200`
   with a real rendered page (`<title>فروشگاه — جستجو و فیلتر کالاها |
   دیجی‌مارکت</title>`, 24 occurrences of the `pcard` product-card class in
   the HTML).

Note: `apps/stores/middleware.py`'s own docstring states `request.store` is
"infrastructure for future PRs" and nothing downstream currently consumes it
— consistent with `catalog/urls.py`'s `products/` route rendering directly on
`localhost:8000` without needing a `StoreDomain`/tenant-host setup for this
generic catalog listing. No tenant-domain workaround was needed or attempted.

**Verdict: PASS.**

---

## F. Real read-only browser design review by the real subagent

Target: `http://localhost:8000/products/` — the real, live product-listing
page rendering the shared `product_card.html` partial (the same component the
prior source-only smoke test reviewed statically). Full findings are in the
subagent's own report (captured verbatim in the task-notification); summarized
here with the acceptance-relevant specifics:

### Desktop (1440×900)
Full-page screenshot taken and visually inspected. 4-column grid, right-hand
filter rail (RTL-correct trailing position), promo/badge stack correctly
varies per product (discount %, "جدید", "پرفروش", "حراج", "ناموجود"),
out-of-stock card correctly omits the add-to-cart button. No overflow/clipping
observed.

### Tablet (768×1024)
Full-page screenshot taken. Grid drops to 3 columns; the right-rail filter
panel is replaced by a collapsed "فیلترها و مرتب‌سازی ▾" accordion — confirmed
as an actual `DisclosureTriangle` node in the accessibility snapshot, not
inferred from appearance alone. No broken layout observed.

### Mobile (375×812)
Full-page screenshot taken. Grid drops to 2 columns; header collapses to
icon-only controls; promo bar text wraps without truncation; badge stack does
not collide with the wishlist icon. No horizontal scroll or clipped content
observed.

### Console messages (`list_console_messages`, verbatim)
```
msgid=2 [issue] An element doesn't have an autocomplete attribute (count: 1)
msgid=3 [verbose] [DOM] Input elements should have autocomplete attributes
  (suggested: "current-password"): (More info: https://goo.gl/9p2vKq) %o (0 args)
```
No JS errors. One minor DevTools autocomplete-attribute advisory, not a
functional defect.

### RTL — actually observed, not source-inferred
- `evaluate_script` confirmed live: `document.documentElement.dir === "rtl"`,
  `lang === "fa"`, computed `body { direction: rtl }` — the real rendered DOM
  state, not just what `base.html`'s source claims.
- Breadcrumbs, filter-rail placement, and badge-stack positioning all read
  correctly right-to-left in the screenshots.
- The phone-number wrapper was directly inspected and confirmed
  `direction: ltr; unicode-bidi: isolate` — a deliberate, correctly-rendered
  LTR island inside the RTL page, matching what the screenshot shows (digits
  read left-to-right, not reversed).
- Persian-digit, fa-IR-formatted prices/ratings observed (e.g.
  "۲٬۲۸۰٬۰۰۰ تومان"), consistent with genuine RTL/Persian rendering rather
  than an LTR template with a `dir` attribute bolted on.
- **LTR limitation explicitly noted by the agent**: it did not force an LTR
  locale/mode to verify the layout also holds up mirrored — it only observed
  the page's default `dir="rtl"` state. This is reported as untested, not
  claimed as passing.

### Accessibility — actually observed
- Real visible keyboard focus ring confirmed by tabbing (`press_key("Tab")`
  ×7) and reading `document.activeElement`'s computed outline, then
  screenshotting it.
- Accessibility-tree snapshot (`take_snapshot`) confirmed: disabled
  "قبلی"/Previous pagination renders as plain text (not a dead link),
  out-of-stock card genuinely lacks an add-to-cart control in the tree (not
  just visually hidden), wishlist icon buttons expose real accessible names.
- **Contrast finding, computed from live styles**: white text on the
  "پرفروش" amber badge (`rgb(245,158,11)`) measures ≈2.1:1 — fails WCAG AA;
  the purple "حراج"/"جدید" badges measure ≈7:1 — pass. This is a genuine
  measured finding from the running page, matching (and now confirming at
  runtime) the same amber-token contrast issue the prior source-only review
  flagged from reading `tokens.css` directly.
- Touch-target size measured directly via bounding rect
  (170×38px add-to-cart button at desktop width) — above the WCAG 2.5.8 AA
  floor, below the comfort recommendation; agent explicitly noted it did not
  re-measure at the mobile viewport, flagging that as untested rather than
  assumed.
- `prefers-reduced-motion` media rules confirmed present (12 rules) in the
  page's actually-loaded stylesheets via `evaluate_script`.
- Product images confirmed `200 OK` via `list_network_requests` — the flat
  color/emoji placeholders seen on some cards are demo seed-data content, not
  broken images (verified via network responses, not assumed from
  appearance).

### Architecture-boundary restatement (from the agent's own persona file)
The agent explicitly restated: it is a design reviewer/advisor, not a merge
authority, and does not introduce a parallel renderer, editor, persistence
system, Ready Template authority, ResourceSource authority, media authority,
or production component engine — and confirmed this review proposes none of
those. Its one concrete finding (amber badge contrast) is a CSS-token-level
fix candidate for a human/engineer to apply, not an architectural change, and
the agent did not itself open or edit the CSS source file.

### Zero file edits
The agent explicitly confirmed: no repository file was created, modified, or
deleted; all MCP calls were read-only browser inspection; screenshots were
written only to the session scratchpad, never into the repository; no
form/cart/wishlist state was mutated.

**Verdict: PASS** (desktop, tablet, mobile, and RTL each individually PASS —
see checklist below).

---

## G. Repository cleanliness

`git status` after the entire exercise (venv creation, migrations, DB seed,
dev server run, subagent browser review) reports: `nothing to commit, working
tree clean` — `.app-venv/` and the SQLite database file are both already
covered by the repository's own `.gitignore` (`.app-venv/`, `db.sqlite3`), so
no local-dev-environment artifact leaked into tracked state. The only
intentional change in this exercise is this evidence file itself.

---

## Final checklist

```
CUSTOM AGENT REGISTERED: PASS — rastisi-ui-ux-design-lead appeared unprompted in this session's own agent-type listing at start, with the exact tools declared in its frontmatter, and was successfully dispatched.
FRONTEND-DESIGN LOADED: FAIL — ListPlugins (filtered and unfiltered) returned zero plugins loaded this session despite the settings.json declaration; no install/trust prompt appeared to act on.
CHROME MCP LOADED: PASS — the full mcp__chrome-devtools__* tool family was discoverable via this session's deferred-tools listing at start, with no manual restart or trust step.
DESIGN AGENT CALLED CHROME MCP: PASS — the rastisi-ui-ux-design-lead subagent itself made 31 real chrome-devtools MCP calls (navigate/resize/screenshot/console/snapshot/network/evaluate/press_key), all succeeding, per its own returned transcript.
REAL PAGE VISUAL INSPECTION: PASS — http://localhost:8000/products/ was actually navigated, screenshotted, and DOM/accessibility-tree inspected by the agent, not inferred from source.
DESKTOP: PASS — 1440x900 full-page screenshot taken and visually described (4-column grid, right-hand filter rail, badge stack, out-of-stock handling).
TABLET: PASS — 768x1024 full-page screenshot taken; 3-column grid and collapsed filter accordion (confirmed via accessibility snapshot) observed.
MOBILE: PASS — 375x812 full-page screenshot taken; 2-column grid, collapsed header, no overflow observed.
RTL REVIEW: PASS — dir="rtl"/lang="fa" and an LTR-pinned phone-number island were directly confirmed via evaluate_script and screenshots, not source inference; the agent explicitly flagged that a mirrored LTR mode was not tested, rather than claiming it.
NO PRODUCTION CHANGE: PASS — git status is clean after the full exercise; only this evidence file was added to the repository.
```
