/*
 * Phase 5 Task 5 — shared public-storefront overlay-mechanics primitive.
 *
 * ONE reusable Alpine component that owns ONLY generic overlay mechanics:
 * open/close lifecycle, Escape handling, backdrop click, focus containment
 * (focus-trap), focus return to the trigger, and body scroll lock. It owns NO
 * domain data whatsoever — the consuming feature keeps its own domain state
 * entirely separate and mixes this in via `x-data="sfbOverlay()"`. This is the
 * single canonical storefront overlay primitive — do not copy its Escape/
 * backdrop/focus/scroll-lock logic per feature.
 *
 * Loaded before Alpine (defer) so the `alpine:init` listener is registered
 * before Alpine initializes, matching the repo's existing Alpine.data pattern.
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('sfbOverlay', () => ({
    overlayOpen: false,
    _returnFocusEl: null,

    openOverlay(returnFocusEl) {
      // Remember what to restore focus to on close. Prefer an explicit trigger
      // element (a mouse click with preventDefault may not focus the button),
      // falling back to whatever is currently focused.
      this._returnFocusEl = returnFocusEl || document.activeElement;
      this.overlayOpen = true;
      // Body scroll lock while the overlay is open.
      document.documentElement.style.overflow = 'hidden';
      document.body.style.overflow = 'hidden';
      // Move focus into the panel after it renders.
      this.$nextTick(() => {
        const panel = this.$refs.overlayPanel;
        if (!panel) return;
        const focusable = panel.querySelector(
          'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        (focusable || panel).focus();
      });
    },

    closeOverlay() {
      this.overlayOpen = false;
      // Release the body scroll lock.
      document.documentElement.style.overflow = '';
      document.body.style.overflow = '';
      // Return focus to the trigger that opened the overlay.
      const el = this._returnFocusEl;
      this._returnFocusEl = null;
      this.$nextTick(() => {
        if (el && typeof el.focus === 'function') el.focus();
      });
    },

    toggleOverlay() {
      this.overlayOpen ? this.closeOverlay() : this.openOverlay();
    },

    // Escape closes the overlay. Bind with @keydown.escape.window on the panel.
    onOverlayKeydown(e) {
      if (e.key === 'Escape') { this.closeOverlay(); return; }
      // Focus trap: keep Tab focus inside the panel while open.
      if (e.key !== 'Tab' || !this.overlayOpen) return;
      const panel = this.$refs.overlayPanel;
      if (!panel) return;
      const items = panel.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    },
  }));
});
