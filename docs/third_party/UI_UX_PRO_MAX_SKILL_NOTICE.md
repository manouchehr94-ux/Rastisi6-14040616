# UI UX Pro Max skill-guidance notice

Companion to `docs/third_party/UI_UX_PRO_MAX_PALETTES_NOTICE.md` (which covers the
64-palette color library). This notice covers a second, separate adaptation: a
curated design-guidance reference used by `.claude/skills/ui-ux-pro-max-guidance/`.

- Project: `nextlevelbuilder/ui-ux-pro-max-skill`
- Pinned upstream version referenced: `2.13.0` (per upstream `skill.json`, homepage
  `https://uupm.cc`, repo `https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`)
- Data files referenced (read-only, for authoring the guidance excerpt below):
  `src/ui-ux-pro-max/data/ux-guidelines.csv`, `.../typography.csv`, `.../motion.csv`
- Upstream license: MIT
- Upstream copyright: Copyright (c) 2024 Next Level Builder

## What was and was NOT done

- **Not installed**: the upstream `ui-ux-pro-max-cli` npm package was **not** installed,
  globally or project-locally, and its installer script was not run. That installer
  scaffolds a much larger, multi-stack footprint (22 target tech stacks, including
  React/Next.js/Vue/Tailwind/etc. implementation guidance) that is out of scope for
  RastiSi, whose production frontend remains Django templates + CSS + JS.
- **Adapted, not vendored verbatim**: a small number of representative, platform-agnostic
  guideline rows (accessibility, responsive, typography, motion/reduced-motion) were read
  from the upstream MIT-licensed CSV data and rewritten as a curated markdown reference
  adapted for RastiSi's Django-template/CSS/JS architecture, mirroring how
  `UI_UX_PRO_MAX_PALETTES_NOTICE.md` already adapted `colors.csv`.
- **No stack-specific, framework, or chart guidance was imported.**
- **No scripts, hooks, or MCP servers were installed from this upstream project.** The
  RastiSi skill at `.claude/skills/ui-ux-pro-max-guidance/SKILL.md` is a plain markdown
  reference with no executable code.

## Removal procedure

Delete `.claude/skills/ui-ux-pro-max-guidance/` and this notice file. Nothing else
depends on them (no scripts, hooks, or settings reference this skill by name).

## MIT License (upstream)

Copyright (c) 2024 Next Level Builder

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
