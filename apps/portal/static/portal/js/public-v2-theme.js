/* Applies the saved light/dark choice before first paint (no flash). */
(function () {
  try {
    var saved = localStorage.getItem('rs-theme');
    if (saved === 'light' || saved === 'dark') document.documentElement.setAttribute('data-theme', saved);
  } catch (e) { /* storage blocked: follow the system */ }
})();
