---
name: ui-ux-pro-max-guidance
description: Curated, platform-agnostic UI/UX design-quality checklist (accessibility, responsive, typography, motion) adapted from the MIT-licensed UI UX Pro Max dataset for RastiSi's Django-template/CSS/JS storefront. Use during Phase-5 design review or design-quality work; not a builder, renderer, or code generator.
---

# UI/UX Pro Max guidance (RastiSi adaptation)

This is a **reference checklist**, not a tool, script, or code generator. It has no
executable code, hooks, or MCP servers. See
`docs/third_party/UI_UX_PRO_MAX_SKILL_NOTICE.md` for full provenance, license, and
scope notes — read that first if you plan to pull in more upstream guidance.

Scope: platform-agnostic design-quality principles only. Framework/stack-specific
implementation guidance (React, Vue, Tailwind component code, chart libraries, etc.)
from the upstream project is intentionally **excluded** — RastiSi's production
frontend is Django templates + CSS + JS, and this skill must not be used to justify
introducing a different stack.

## Accessibility

- Visible focus ring on every interactive control, including controls inside modals.
- 4.5:1 minimum text-to-background contrast ratio for body text.
- Never convey meaning through color alone — pair with icon or text.
- `aria-label` on icon-only buttons; descriptive `alt` text on meaningful images.
- Tab order matches visual order; every action must be reachable and testable by keyboard.
- `<label for="id">` associated with every input; do not rely on placeholder-only labels.
- Errors announced via `role="alert"` or an `aria-live` region, and connected to the
  field with `aria-describedby`.
- Provide a "skip to main content" link on pages with substantial navigation chrome.
- Minimum pointer target size 24×24 CSS px (WCAG 2.2); prefer 44–48px on touch surfaces.
- Support `prefers-reduced-motion`: stop non-essential animation, avoid parallax, render
  the end state immediately, and give any auto-rotating carousel a pause control.
- Accessible authentication: allow paste into password fields and support password
  managers.

## Responsive

- Design mobile-first, then progressively enhance for tablet/desktop.
- Test at common breakpoints, at minimum: 320, 375, 414, 768, 1024, 1440px.
- Minimum 16px body text on mobile, scaled fluidly rather than fixed pixel jumps.
- No horizontal overflow/scroll from page content at any tested width.
- `<meta name="viewport" content="width=device-width, initial-scale=1">` present.

## Typography

- 1.5–1.75 line-height multiplier for comfortable body-text reading.
- 65–75 character measure (line length) for body copy.
- One or two type families per surface with a clear, deliberate distinction between
  them — not an accent applied only to a single word or phrase.

## Interaction / feedback

- Loading states use a stable skeleton or `aria-busy` progress indicator, not layout
  shift.
- Structural devices (borders, numbering, dividers, labels) should encode information
  about the content, not just decorate it.
- Motion should be purposeful and orchestrated (e.g., one page-load sequence), not
  scattered micro-animations across unrelated elements.

## RTL / Persian — not covered upstream

The upstream dataset has **no explicit RTL or internationalization guidance rows**.
For RastiSi, RTL/Persian quality is first-class and is authoritative from
`.claude/agents/rastisi-ui-ux-design-lead.md` and RastiSi's own conventions, not from
this upstream checklist. When in doubt, RastiSi project rules win over this document.

## How to use this during Phase-5 design review

1. Treat every bullet above as a checklist item when reviewing or proposing a design
   change to a RastiSi storefront template.
2. Flag violations as design-quality findings, not as blockers to canonical
   architecture — this skill informs recommendations, it does not grant authority to
   change renderer, persistence, or editor architecture.
3. Prefer RastiSi's existing component families/registries over inventing new markup
   patterns to satisfy a checklist item.
