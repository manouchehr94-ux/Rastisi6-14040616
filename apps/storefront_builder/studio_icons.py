"""Stroke icon paths for the R4 Design Studio workspace chrome.

Single source for both server templates (``{% rs_icon %}``) and the Studio
presentation script (serialized once into the page via ``json_script``), so
the workspace never carries two drifting icon sets. Geometry is the approved
RastiSi_Design_Studio.html reference's own 24x24 stroke set.
"""

STUDIO_ICON_PATHS = {
    "arrow": "m14 5-7 7 7 7",
    "chevron": "m8 10 4 4 4-4",
    "close": "m6 6 12 12M6 18 18 6",
    "check": "m5 12 4 4L19 6",
    "plus": "M12 5v14M5 12h14",
    "grid": "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "layers": "m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5",
    "sliders": "M4 5h16M4 12h16M4 19h16M8 3v4M16 10v4M9 17v4",
    "spark": "m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7zM20 2v4M18 4h4",
    "desktop": "M3 4h18v13H3zM12 17v4M8 21h8",
    "tablet": "M5 2h14v20H5zM11 19h2",
    "mobile": "M7 2h10v20H7zM11 19h2",
    "undo": "M9 5 4 10l5 5M4 10h10a6 6 0 0 1 0 12",
    "redo": "m15 5 5 5-5 5M20 10h-10a6 6 0 0 0 0 12",
    "eye": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
    "lock": "M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4M12 14v3",
    "unlock": "M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0M12 14v3",
    "refresh": "M20 11a8 8 0 1 0-2 7M20 4v7h-7",
    "shuffle": "M3 5h3c4 0 8 14 12 14h3M17 15l4 4-4 3M3 19h3c2 0 4-3 6-7s4-7 6-7h3M17 1l4 4-4 4",
    "header": "M3 4h18v16H3zM3 9h18M7 6.5h2",
    "footer": "M3 4h18v16H3zM3 15h18M7 17.5h2",
    "image": "M3 4h18v16H3zM3 17l6-6 4 4 3-3 5 5M15 8h.01",
    "card": "M5 3h14v18H5zM5 13h14M8 16h8M8 18h4",
    "tag": "m3 3 9 0 9 9-9 9-9-9zM7 7h.01",
    "trash": "M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7",
    "copy": "M9 8h11v13H9zM15 8V3H4v13h5",
    "up": "m6 14 6-6 6 6",
    "down": "m6 10 6 6 6-6",
    "history": "M3 10a9 9 0 1 1 1 8M3 3v7h7M12 7v5l3 2",
    "help": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5M12 17h.01",
    "bag": "M5 7h14l2 14H3zM8 7V5a4 4 0 0 1 8 0v2",
    "search": "M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0m-2 5 6 6",
    "home": "m2 10 10-8 10 8M5 8v13h14V8M9 21v-8h6v8",
    "user": "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 22v-3a8 8 0 0 1 16 0v3",
    "external": "M14 3h7v7M21 3l-11 11M10 3H3v18h18v-7",
    "globe": "M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0M2 12h20M12 2c-6 6-6 14 0 20 6-6 6-14 0-20",
    "dots": "M5 12h.01M12 12h.01M19 12h.01",
}

#: Icon per Design Lab family (presentation only; family keys/labels come from
#: the server's canonical Design Lab projection).
DESIGN_LAB_FAMILY_ICONS = {
    "header": "header",
    "hero": "image",
    "product_view": "grid",
    "card": "card",
    "footer": "footer",
    "badge": "tag",
    "bottom_nav": "mobile",
}


def icon_svg(name: str) -> str:
    path = STUDIO_ICON_PATHS.get(name, STUDIO_ICON_PATHS["grid"])
    return (
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        f'<path d="{path}"/></svg>'
    )
