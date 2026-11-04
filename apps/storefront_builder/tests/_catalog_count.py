"""The ONE place that pins how many official Ready Templates the catalog holds (50 token-built A8 + 51-53 reference-fidelity
+ the V5 six-site kit 54-59 + the four Hero Stage templates 60-63). Adding a template means changing this single number — never a literal in a dozen tests."""

READY_TEMPLATE_COUNT = 63
#: every registered layout preset = the 5 historical/internal presets + the 8 retained pre-A8 identities' extra recipes + the Ready Templates
#: (the number below was 58 when the catalog held 53 Ready Templates).
LAYOUT_PRESET_COUNT = READY_TEMPLATE_COUNT + 5

#: Total certification cells of the W4C harness for the current catalogue (every Ready Template contributes its own page matrix, so this
#: moves with READY_TEMPLATE_COUNT; the harness test recomputes it from the real catalogue and compares).
W4C_TOTAL_CELLS = 704 + 13 * (READY_TEMPLATE_COUNT - 50)  # 743 at 53 templates, 821 at 59, 873 at 63

#: Registered palettes: 67 at 53 Ready Templates; every V5 six-site template (54-59) and every Hero Stage template (60-63) ships exactly one palette of its own.
PALETTE_COUNT = 67 + (READY_TEMPLATE_COUNT - 53)
