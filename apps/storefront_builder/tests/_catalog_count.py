"""The ONE place that pins how many official Ready Templates the catalog holds (50 token-built A8 + 51-53 reference-fidelity
+ the V5 six-site kit 54-59). Adding a template means changing this single number — never a literal in a dozen tests."""

READY_TEMPLATE_COUNT = 54
#: every registered layout preset = the 5 historical/internal presets + the 8 retained pre-A8 identities' extra recipes + the Ready Templates
#: (the number below was 58 when the catalog held 53 Ready Templates).
LAYOUT_PRESET_COUNT = READY_TEMPLATE_COUNT + 5
