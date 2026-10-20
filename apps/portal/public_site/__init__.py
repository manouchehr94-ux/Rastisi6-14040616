"""Editable public marketing website (landing "Sardar" design).

* ``registry``  — every editable text/colour/font/image reference and its shipped default.
* ``services``  — resolve overrides (``PublicSiteSetting``), design switch, theme CSS.
* ``rendering`` — ``render`` drop-in that picks the v2 template when the new design is active.

Only the platform owner (superuser) edits this through Platform Admin; nothing here
touches storefront/tenant code or data.
"""
