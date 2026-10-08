// Applies the stored theme before first paint. Loaded as a file: the page's CSP forbids inline scripts.
try {
  var t = new URLSearchParams(location.search).get("theme") || localStorage.getItem("folio-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
