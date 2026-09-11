# Anthropic frontend-design plugin — provenance and version status

Companion notice for the `frontend-design@claude-plugins-official` entry declared in
`.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`). No plugin
content is vendored into this repository — this file only records what was
inspected and how the declaration behaves.

## What was actually verified (corrected 2026-09-11)

An earlier pass of this task cited `"version": "1.1.0"` for this plugin. That
number is real, but it comes from a **different repository**
(`anthropics/claude-code`, path `plugins/frontend-design/.claude-plugin/plugin.json`)
that is **not** the source our marketplace declaration resolves to. Corrected,
verified-by-raw-fetch facts:

- **Official marketplace we declare**: `anthropics/claude-plugins-official`
  (`extraKnownMarketplaces.claude-plugins-official`).
- **Marketplace listing entry** (`.claude-plugin/marketplace.json`) for
  `frontend-design`: `"source": "./plugins/frontend-design"` — a relative path
  inside that same repo, with **no `ref` pinned**, so it tracks that repo's
  default branch (`main`) unless we pin it or disable auto-update (see below).
- **The plugin's own manifest at that path**
  (`anthropics/claude-plugins-official/plugins/frontend-design/.claude-plugin/plugin.json`)
  has **no `version` field at all**:
  ```json
  {
    "name": "frontend-design",
    "description": "Frontend design skill for UI/UX implementation",
    "author": { "name": "Anthropic", "email": "support@anthropic.com" }
  }
  ```
- Content-wise, the `SKILL.md` served from `anthropics/claude-plugins-official`,
  `anthropics/claude-code`, and `anthropics/claude-plugins-public` is byte-identical
  (verified by `md5sum` of the raw file from all three), so the guidance itself is
  consistent across mirrors even though only one (`claude-code`) happens to carry a
  `version: 1.1.0` field on its copy of `plugin.json`. That field is **not**
  authoritative for what this project actually installs.
- **Exact commit inspected**: `anthropics/claude-plugins-official` `main` was at
  commit `3b600518a637492d37c9877aeb49c2a55d939c04` at the time of this audit
  (via `git ls-remote`, since `api.github.com` is not reachable from this session
  for repos outside its configured scope).

**Correct verdict: FRONTEND-DESIGN UPSTREAM VERSION STATUS = unversioned at the
plugin.json level, as installed via our declared marketplace.** Treat "1.1.0" as
informational only, sourced from a mirror we do not install from.

## Update behavior

`.claude/settings.json` sets `extraKnownMarketplaces.claude-plugins-official.
autoUpdate: false` (a supported field per the current Claude Code settings schema:
"Whether to automatically update this marketplace on Claude Code startup"). This
means the marketplace should not silently re-sync to a newer commit on ordinary
session startup — RastiSi design-guidance sessions stay on whatever commit was
last fetched until a human deliberately re-enables/refreshes it.

We did **not** attempt to pin `extraKnownMarketplaces.claude-plugins-official.
source.ref` to the exact commit SHA above: the current settings schema documents
`ref` for a GitHub-source marketplace as "Git branch or tag to use", and does not
confirm arbitrary full-commit-SHA values are accepted there. Since a bad `ref`
value could break marketplace resolution entirely (worse than an un-pinned but
auto-update-disabled marketplace), we chose the schema-confirmed `autoUpdate:
false` mechanism instead of an unconfirmed SHA pin. If/when upstream publishes a
tagged release for this plugin, prefer switching `ref` to that tag.

## Removal procedure

Remove the `frontend-design@claude-plugins-official` entry from `enabledPlugins`
and the `claude-plugins-official` entry from `extraKnownMarketplaces` in
`.claude/settings.json`, and delete this file. Nothing else in the repo depends on
this declaration.
