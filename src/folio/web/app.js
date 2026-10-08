// folio front end: vanilla JS, no build step.
"use strict";

const TOKEN = document.querySelector('meta[name="folio-token"]').content;
const LANG = (navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en";
const $ = (id) => document.getElementById(id);

// ── Strings ────────────────────────────────────────────────────────────────

const STRINGS = {
  fr: {
    resumeIndex: "Reprendre l'indexation",
    continueBattery: "Continuer sur batterie",
    batteryTitle: "Indexer sur batterie",
    cancel: "Annuler",
    firstEyebrow: "Premier lancement",
    firstTitle: "Retrouve un fichier en décrivant ce dont tu te souviens.",
    firstLead: "folio cherche dans les noms, les dossiers et le contenu de tes fichiers, en français et en anglais. L'index reste sur ce Mac : rien n'est envoyé ailleurs.",
    firstExample: "le devis de la cuisine en chêne",
    firstEx1: "slides du cours sur la VaR", firstEx2: "pdf de la semaine dernière", firstEx3: "notes de la réunion budget",
    firstScope: "À indexer", firstNext: "Ce qui va se passer",
    firstCaption: "L'indexation tourne en priorité basse et se met en pause sur batterie faible.",
    startMeta: "la recherche par nom marche au bout d'une seconde",
    startIndexLabel: "Indexer mes fichiers",
    resumeIndex: "Reprendre l'indexation",
    alreadyDone: (n) => `${fmtInt(n)} fichier${n > 1 ? "s" : ""} déjà indexé${n > 1 ? "s" : ""} : folio reprend à partir de là`,
    stoppedFirst: "Indexation arrêtée.",
    stoppedUpdate: "Mise à jour arrêtée. L'index reste utilisable.",
    startRunning: "Indexation lancée. La recherche s'ouvre dès que les noms sont prêts.",
  },
  en: {
    resumeIndex: "Resume indexing",
    continueBattery: "Continue on battery",
    batteryTitle: "Index on battery",
    cancel: "Cancel",
    firstEyebrow: "First launch",
    firstTitle: "Find a file by describing what you remember about it.",
    firstLead: "folio searches the names, folders and content of your files, in French and English. The index stays on this Mac: nothing is sent anywhere.",
    firstExample: "the kitchen quote in solid oak",
    firstEx1: "slides from the VaR course", firstEx2: "pdf from last week", firstEx3: "budget meeting notes",
    firstScope: "To index", firstNext: "What happens next",
    firstCaption: "Indexing runs at low priority and pauses on low battery.",
    startMeta: "search by name works after one second",
    startIndexLabel: "Index my files",
    resumeIndex: "Resume indexing",
    alreadyDone: (n) => `${fmtInt(n)} file${n > 1 ? "s" : ""} already indexed: folio picks up from there`,
    stoppedFirst: "Indexing stopped.",
    stoppedUpdate: "Update stopped. The index stays usable.",
    startRunning: "Indexing started. Search opens as soon as names are ready.",

    startIndex: "Index my files",
    placeholder: "Find a file: “kitchen quote pdf from March”, “budget meeting notes”…",
    all: "All", allDates: "All", docs: "Docs", sheets: "Sheets", slides: "Slides", images: "Images",
    kNav: "select", kOpen: "open", kReveal: "show in Finder", kCopy: "copy path", kPreview: "preview", kClear: "clear",
    statusTitle: "Index", close: "Close", theme: "Change theme", stopIndex: "Stop indexing",
  },
};
const T = {
  fr: {
    statusTitle: "Index",
    mb: "Mo",
    about: (d) => `≈ ${d}`,
    namesTodo: "≈ 1 s · la recherche marche dès cette étape",
    contentEstimate: (d, n) => `${d} · ${fmtInt(n)} fichiers à lire`,
    firstNext: "Ce qui va se passer",
    firstRunning: "Indexation en cours",
    stepReady: "prêt",
    firstHint: (n, r) => `fichiers dans ${r} dossier${r > 1 ? "s" : ""}, comptés sans les ouvrir`,
    rootNames: { Documents: "Documents", Downloads: "Téléchargements", Desktop: "Bureau", "iCloud Drive": "iCloud Drive" },
    kpiReadable: "Contenu lisible",
    kpiCloud: "iCloud, par nom",
    kpiDuration: "Durée estimée",
    indexN: (n) => `Indexer ${fmtInt(n)} fichiers`,
    firstCaption: "L'indexation tourne en priorité basse et se met en pause sur batterie faible.",
    startMeta: "la recherche par nom marche au bout d'une seconde",
    startIndexLabel: "Indexer mes fichiers",
    resumeIndex: "Reprendre l'indexation",
    alreadyDone: (n) => `${fmtInt(n)} fichier${n > 1 ? "s" : ""} déjà indexé${n > 1 ? "s" : ""} : folio reprend à partir de là`,
    stoppedFirst: "Indexation arrêtée.",
    stoppedUpdate: "Mise à jour arrêtée. L'index reste utilisable.",
    startRunning: "Indexation lancée. La recherche s'ouvre dès que les noms sont prêts.",
    firstCaptionRunning: "La recherche s'ouvre dès que les noms sont indexés. Tu peux fermer cette page : l'indexation continue.",
    files: (n) => `${fmtInt(n)} fichier${n > 1 ? "s" : ""}`,
    upToDate: "à jour",
    incomplete: "incomplet",
    indexing: "indexation",
    paused: "en pause",
    pausedBattery: (n) => `Batterie à ${n} %. L'indexation est en pause pour préserver la batterie ; elle reprend toute seule sur secteur.`,
    phaseScanning: "Parcours des dossiers",
    phaseNames: "Indexation des noms",
    phaseContent: "Contenu et vecteurs",
    phaseModel: "Téléchargement du modèle",
    etaIn: (s) => `fin dans ≈ ${fmtDuration(s)}`,
    stepModel: "Télécharger les modèles de langue",
    stepScan: "Trouver tes fichiers",
    stepNames: "Indexer les noms et les dossiers",
    stepContent: "Lire le contenu et en calculer le sens",
    stepState: { done: "terminé", current: "en cours", todo: "à venir" },
    modelNames: { "e5-small": "modèle de recherche", "e5-base": "modèle de recherche", "mmarco-minilm": "modèle de classement", vocabulary: "vocabulaire" },
    modelBytes: (name, done, total, i, n) => `${name} · ${done} / ${total} Mo${n > 1 ? ` · fichier ${i} sur ${n}` : ""}`,
    connecting: "connexion à Hugging Face…",
    modelsTodo: "≈ 240 Mo, une seule fois",
    modelsDone: "téléchargés, folio fonctionne maintenant hors ligne",
    modelsReady: "déjà installés : rien à télécharger",
    filesFound: (n) => `${fmtInt(n)} fichier${n > 1 ? "s" : ""} trouvé${n > 1 ? "s" : ""}`,
    modelsWillDownload: "La première fois, folio télécharge ses deux modèles de langue (≈ 240 Mo). Ensuite, il fonctionne hors ligne.",
    modelsInstalled: "Les modèles de langue sont déjà installés : rien à télécharger, folio fonctionne hors ligne.",
    namesDone: "la recherche par nom est prête",
    contentTodo: "l'étape la plus longue : quelques minutes",
    contentDetail: (d, t) => `${fmtInt(d)} / ${fmtInt(t)} fichiers`,
    bannerFirst: "Première indexation",
    bannerUpdate: "Mise à jour de l'index",
    bannerPaused: "Indexation en pause",
    bannerFirstText: "Tu peux déjà chercher par nom et par dossier. Le contenu des fichiers s'ajoute au fur et à mesure : un résultat peut encore monter dans la liste.",
    bannerUpdateText: "Les résultats restent disponibles pendant la mise à jour.",
    bannerCount: (d, t, ok) => `${fmtInt(d)} / ${fmtInt(t)} fichiers · ${fmtInt(ok)} lus`,
    reading: (name) => `en cours : ${name}`,
    bannerReady: "Index prêt",
    bannerPartial: "Index incomplet",
    continueBattery: "Continuer sur batterie",
    batteryWhy: (n) => `folio met l'indexation en pause quand la batterie passe sous ${n} % : lire et analyser des centaines de fichiers occupe le processeur plusieurs minutes, ce qui vide la batterie plus vite et fait chauffer le Mac. Sur secteur, l'indexation reprend toute seule.`,
    batteryNow: "Batterie",
    batteryLeft: "Fichiers restants",
    batteryTime: "Temps estimé",
    batteryScope: "Ce choix vaut pour cette indexation. La suivante se remettra en pause sous le seuil, réglable dans la configuration (min_battery_percent).",
    batteryContinued: "L'indexation continue sur batterie.",
    cancel: "Annuler",
    bannerPartialText: (n) => `L'indexation a été arrêtée. La recherche par nom et par dossier marche pour tous les fichiers ; le contenu de ${fmtInt(n)} fichier${n > 1 ? "s" : ""} n'est pas encore lu.`,
    bannerReadyText: (n, ok, cloud, watching) =>
      (ok >= n ? `${fmtInt(n)} fichiers, tous avec leur contenu.` : `${fmtInt(n)} fichiers : ${fmtInt(ok)} avec leur contenu, les autres par nom et dossier${cloud ? ` (dont ${fmtInt(cloud)} dans iCloud, non téléchargés)` : ""}.`) +
      (watching ? " Les modifications sont suivies automatiquement." : ""),
    bannerUpdated: "Index à jour",
    noResults: "Aucun fichier ne correspond. Essaie d'autres mots, ou retire un filtre.",
    recent: "Récents",
    relaxed: "Aucun résultat avec ces filtres : résultats sans filtre, les plus proches en premier.",
    copied: "Chemin copié.",
    opened: "Ouvert.",
    gone: "Le fichier n'existe plus.",
    icloud: "iCloud, non téléchargé",
    reasons: { name: "nom", folder: "dossier", content: "contenu", meaning: "sens", history: "déjà ouvert" },
    today: "aujourd'hui", yesterday: "hier",
    at: (t) => `à ${t}`,
    sDocs: "Fichiers", sContent: "Avec contenu", sVectors: "Vecteurs", sErrors: "Erreurs",
    sProgress: "Progression", sFolders: "Dossiers indexés", sState: "État des fichiers", sCheck: "Vérifications",
    sLast: (d) => `Dernière indexation ${d}`,
    sFda: "Accès complet au disque", sFdaOk: "accordé", sFdaNo: "non accordé : les dossiers protégés sont ignorés",
    sWatch: "Suivi des modifications", sOn: "actif", sOff: "inactif",
    sMem: "Mémoire du serveur",
    sUpdate: "Mettre à jour", sRebuild: "Tout réindexer", sConfig: "Configuration",
    sDelete: "Supprimer l'index…",
    sDeleteTitle: "Supprimer l'index",
    sDeleteWhat: (mb) => `folio supprime son index (${mb} Mo) et l'historique de tes recherches. Tes fichiers ne sont pas touchés.`,
    sDeleteKeep: "Les modèles de langue et la configuration restent installés : une nouvelle indexation ne télécharge rien.",
    sUninstallHint: "Pour tout retirer de ce Mac, modèles compris :",
    sCancel: "Annuler",
    sDeleteConfirm: "Supprimer l'index",
    sDeleting: "Suppression…",
    sDeleted: "Index supprimé.",
    sErrList: "Fichiers dont le contenu n'a pas pu être lu (indexés par nom et dossier)",
    st: { ok: "contenu indexé", empty: "sans texte", skipped: "nom seulement (type sans texte)", dataless: "nom seulement (iCloud, non téléchargé)", too_big: "nom seulement (trop gros)", error: "erreur de lecture", timeout: "délai dépassé", pending: "en attente" },
    semanticLoading: "chargement du modèle",
    failed: (m) => `Échec : ${m}`,
  },
  en: {
    statusTitle: "Index",
    mb: "MB",
    about: (d) => `≈ ${d}`,
    namesTodo: "≈ 1 s · search works from this step",
    contentEstimate: (d, n) => `${d} · ${fmtInt(n)} files to read`,
    firstNext: "What happens next",
    firstRunning: "Indexing",
    stepReady: "ready",
    firstHint: (n, r) => `files in ${r} folder${r > 1 ? "s" : ""}, counted without opening them`,
    rootNames: { Documents: "Documents", Downloads: "Downloads", Desktop: "Desktop", "iCloud Drive": "iCloud Drive" },
    kpiReadable: "Readable content",
    kpiCloud: "iCloud, by name",
    kpiDuration: "Estimated time",
    indexN: (n) => `Index ${fmtInt(n)} files`,
    firstCaption: "Indexing runs at low priority and pauses on low battery.",
    startMeta: "search by name works after one second",
    startIndexLabel: "Index my files",
    resumeIndex: "Resume indexing",
    alreadyDone: (n) => `${fmtInt(n)} file${n > 1 ? "s" : ""} already indexed: folio picks up from there`,
    stoppedFirst: "Indexing stopped.",
    stoppedUpdate: "Update stopped. The index stays usable.",
    startRunning: "Indexing started. Search opens as soon as names are ready.",
    firstCaptionRunning: "Search opens as soon as names are indexed. You can close this page: indexing goes on.",
    files: (n) => `${fmtInt(n)} file${n > 1 ? "s" : ""}`,
    upToDate: "up to date",
    incomplete: "incomplete",
    indexing: "indexing",
    paused: "paused",
    pausedBattery: (n) => `Battery at ${n} %. Indexing is paused to save the battery; it resumes by itself on power.`,
    phaseScanning: "Walking folders",
    phaseNames: "Indexing names",
    phaseContent: "Content and vectors",
    phaseModel: "Downloading the model",
    etaIn: (s) => `done in ≈ ${fmtDuration(s)}`,
    stepModel: "Download the language models",
    stepScan: "Find your files",
    stepNames: "Index names and folders",
    stepContent: "Read the content and compute its meaning",
    stepState: { done: "done", current: "running", todo: "next" },
    modelNames: { "e5-small": "search model", "e5-base": "search model", "mmarco-minilm": "ranking model", vocabulary: "vocabulary" },
    modelBytes: (name, done, total, i, n) => `${name} · ${done} / ${total} MB${n > 1 ? ` · file ${i} of ${n}` : ""}`,
    connecting: "connecting to Hugging Face…",
    modelsTodo: "≈ 240 MB, once",
    modelsDone: "downloaded, folio now works offline",
    modelsReady: "already installed: nothing to download",
    filesFound: (n) => `${fmtInt(n)} file${n > 1 ? "s" : ""} found`,
    modelsWillDownload: "The first time, folio downloads its two language models (≈ 240 MB). After that it works offline.",
    modelsInstalled: "The language models are already installed: nothing to download, folio works offline.",
    namesDone: "search by name is ready",
    contentTodo: "the longest step: a few minutes",
    contentDetail: (d, t) => `${fmtInt(d)} / ${fmtInt(t)} files`,
    bannerFirst: "First indexing",
    bannerUpdate: "Updating the index",
    bannerPaused: "Indexing paused",
    bannerFirstText: "You can already search by name and folder. File content is added as it is read, so a result can still move up the list.",
    bannerUpdateText: "Results stay available during the update.",
    bannerCount: (d, t, ok) => `${fmtInt(d)} / ${fmtInt(t)} files · ${fmtInt(ok)} read`,
    reading: (name) => `reading: ${name}`,
    bannerReady: "Index ready",
    bannerPartial: "Index incomplete",
    continueBattery: "Continue on battery",
    batteryWhy: (n) => `folio pauses indexing when the battery drops below ${n} %: reading and analysing hundreds of files keeps the processor busy for several minutes, which drains the battery faster and warms the Mac. On power, indexing resumes by itself.`,
    batteryNow: "Battery",
    batteryLeft: "Files left",
    batteryTime: "Estimated time",
    batteryScope: "This choice applies to this indexing only. The next one pauses again below the threshold, which you can set in the configuration (min_battery_percent).",
    batteryContinued: "Indexing continues on battery.",
    cancel: "Cancel",
    bannerPartialText: (n) => `Indexing was stopped. Search by name and folder works for every file; the content of ${fmtInt(n)} file${n > 1 ? "s is" : " is"} not read yet.`,
    bannerReadyText: (n, ok, cloud, watching) =>
      (ok >= n ? `${fmtInt(n)} files, all with their content.` : `${fmtInt(n)} files: ${fmtInt(ok)} with their content, the others by name and folder${cloud ? ` (${fmtInt(cloud)} in iCloud, not downloaded)` : ""}.`) +
      (watching ? " Changes are tracked automatically." : ""),
    bannerUpdated: "Index up to date",
    noResults: "No file matches. Try other words, or remove a filter.",
    recent: "Recent",
    relaxed: "No result with these filters: showing unfiltered results, closest first.",
    copied: "Path copied.",
    opened: "Opened.",
    gone: "The file no longer exists.",
    icloud: "iCloud, not downloaded",
    reasons: { name: "name", folder: "folder", content: "content", meaning: "meaning", history: "opened before" },
    today: "today", yesterday: "yesterday",
    at: (t) => `at ${t}`,
    sDocs: "Files", sContent: "With content", sVectors: "Vectors", sErrors: "Errors",
    sProgress: "Progress", sFolders: "Indexed folders", sState: "File states", sCheck: "Checks",
    sLast: (d) => `Last indexed ${d}`,
    sFda: "Full Disk Access", sFdaOk: "granted", sFdaNo: "not granted: protected folders are skipped",
    sWatch: "Change tracking", sOn: "on", sOff: "off",
    sMem: "Server memory",
    sUpdate: "Update", sRebuild: "Rebuild index", sConfig: "Configuration",
    sDelete: "Delete index…",
    sDeleteTitle: "Delete the index",
    sDeleteWhat: (mb) => `folio deletes its index (${mb} MB) and your search history. Your files are not touched.`,
    sDeleteKeep: "The language models and the configuration stay installed: indexing again downloads nothing.",
    sUninstallHint: "To remove everything from this Mac, models included:",
    sCancel: "Cancel",
    sDeleteConfirm: "Delete the index",
    sDeleting: "Deleting…",
    sDeleted: "Index deleted.",
    sErrList: "Files whose content could not be read (indexed by name and folder)",
    st: { ok: "content indexed", empty: "no text", skipped: "name only (no text in this type)", dataless: "name only (iCloud, not downloaded)", too_big: "name only (too large)", error: "read error", timeout: "timed out", pending: "pending" },
    semanticLoading: "loading the model",
    failed: (m) => `Failed: ${m}`,
  },
}[LANG];

function applyStrings() {
  document.documentElement.lang = LANG;
  const s = STRINGS[LANG];
  document.querySelectorAll("[data-i18n]").forEach((el) => { if (s[el.dataset.i18n]) el.textContent = s[el.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { if (s[el.dataset.i18nPlaceholder]) el.placeholder = s[el.dataset.i18nPlaceholder]; });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    if (s[el.dataset.i18nAria]) el.setAttribute("aria-label", s[el.dataset.i18nAria]);
    if (el.title) el.title = el.getAttribute("aria-label");
  });
}

// ── Formatting ─────────────────────────────────────────────────────────────

const nf = new Intl.NumberFormat(LANG);
const fmtInt = (n) => nf.format(n);
const timeFmt = new Intl.DateTimeFormat(LANG, { hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat(LANG, { day: "numeric", month: "short" });
const fullFmt = new Intl.DateTimeFormat(LANG, { day: "numeric", month: "short", year: "numeric" });

function fmtDate(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (d.getTime() >= startToday) return `${T.today} ${T.at(timeFmt.format(d))}`;
  if (d.getTime() >= startToday - 86400000) return `${T.yesterday} ${T.at(timeFmt.format(d))}`;
  return d.getFullYear() === now.getFullYear() ? dayFmt.format(d) : fullFmt.format(d);
}

function fmtDuration(s) {
  s = Math.max(1, Math.round(s));
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
}

function fold(s) {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// ── API ────────────────────────────────────────────────────────────────────

async function api(path, { method = "GET", body, signal } = {}) {
  const res = await fetch(path, {
    method,
    signal,
    headers: { "X-Folio-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), { status: res.status });
  return data;
}

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  q: "",
  off: new Set(),
  kind: "",
  days: "",
  results: [],
  selected: 0,
  listMode: false,  // true after arrow keys: Space previews instead of typing
  controller: null,
  status: null,
  view: null,
};

const input = $("q");
const list = $("results");

// ── Views ──────────────────────────────────────────────────────────────────

function showView(view) {
  if (state.view === view) return;
  state.view = view;
  $("onboard").hidden = view !== "onboard";
  $("search").hidden = view !== "search";
  $("index-chip").hidden = view !== "search";
  if (view === "search") {
    input.focus();
    search();
  }
}

function meter(el, pct) {
  if (!el.children.length) for (let i = 0; i < 20; i++) el.appendChild(document.createElement("span"));
  const lit = pct > 0 ? Math.max(1, Math.round(pct / 5)) : 0;
  [...el.children].forEach((c, i) => c.classList.toggle("is-lit", i < lit));
  el.setAttribute("aria-valuenow", String(Math.round(pct)));
}

function phaseLabel(p) {
  if (p.phase === "scanning") return T.phaseScanning;
  if (p.phase === "names") return T.phaseNames;
  if (p.phase === "model") return T.phaseModel;
  if (p.phase === "paused") return T.pausedBattery(p.battery);
  return T.phaseContent;
}

const fmtMB = (b) => (b > 0 && b < 1e6 ? "< 1" : fmtInt(Math.round(b / 1e6)));

// First run: the four steps, with estimates before the click and live state after it.
function renderSteps(s) {
  const p = s.progress;
  const pv = state.preview;
  const running = s.indexing;
  const order = ["model", "scanning", "names", "content"];
  const at = running ? Math.max(0, order.indexOf(p.phase === "paused" ? "content" : p.phase)) : -1;
  const est = pv ? T.about(fmtDuration(pv.estimate_s)) : "";
  const steps = [
    {
      name: T.stepModel,
      detail: p.phase === "model"
        ? (p.model_total ? T.modelBytes(T.modelNames[p.model_label] || p.model_label, fmtMB(p.model_done), fmtMB(p.model_total), p.model_index, p.model_count) : T.connecting)
        : s.models_ready ? T.modelsReady : at > 0 ? T.modelsDone : T.modelsTodo,
      pct: p.phase === "model" && p.model_total ? (100 * p.model_done) / p.model_total : null,
    },
    { name: T.stepScan, detail: at >= 1 ? T.filesFound(p.found || (pv && pv.total) || 0) : T.about("1 s") },
    { name: T.stepNames, detail: at > 2 ? T.namesDone : T.namesTodo },
    {
      name: T.stepContent,
      detail: at === 3 ? T.contentDetail(p.done, p.total) + (p.eta_s != null ? ` · ${T.etaIn(p.eta_s)}` : "") : pv ? T.contentEstimate(est, pv.readable) : T.contentTodo,
      pct: at === 3 ? p.pct : null,
    },
  ];
  $("onboard-steps").replaceChildren(...steps.map((st, i) => {
    const ready = i === 0 && s.models_ready && !running;
    const stateName = ready ? "done" : !running ? "todo" : i < at ? "done" : i === at ? "current" : "todo";
    const label = ready ? T.stepReady : running ? T.stepState[stateName] : String(i + 1).padStart(2, "0");
    const li = el("li", `step is-${stateName}`);
    li.append(el("span", "step__name", st.name), el("span", "step__state", label));
    if (st.detail) li.append(el("span", "step__detail", st.detail));
    if (stateName === "current" && st.pct != null) {
      const m = el("div", "ro-meter");
      m.setAttribute("role", "meter");
      m.setAttribute("aria-valuemin", "0");
      m.setAttribute("aria-valuemax", "100");
      m.setAttribute("aria-label", st.name);
      meter(m, st.pct);
      li.append(m);
    }
    return li;
  }));
  $("first-steps-title").textContent = running ? T.firstRunning : T.firstNext;
}

// First run: what folio will index, counted by a quick walk of the folders (no file opened).
function renderPreview(pv) {
  $("first-total").textContent = fmtInt(pv.total);
  $("first-hint").textContent = T.firstHint(pv.total, pv.by_root.length);
  const max = Math.max(1, ...pv.by_root.map((r) => r.count));
  $("first-roots").replaceChildren(...pv.by_root.map((r) => {
    const li = el("li");
    li.append(el("span", "ro-bars__label", T.rootNames[r.label] || r.label));
    const track = el("span", "ro-bars__track");
    const bar = el("span", "ro-bars__bar");
    bar.style.width = `${Math.max(1, (100 * r.count) / max) * 0.82}%`;
    track.append(bar, el("span", "ro-bars__value ro-mono", fmtInt(r.count)));
    li.append(track);
    return li;
  }));
  const kpis = [[T.kpiReadable, fmtInt(pv.readable)], [T.kpiCloud, fmtInt(pv.cloud)], [T.kpiDuration, `≈ ${fmtDuration(pv.estimate_s)}`]];
  $("first-kpis").replaceChildren(...kpis.map(([dt, dd]) => { const d = el("div"); d.append(el("dt", null, dt), el("dd", null, dd)); return d; }));
  renderStartMeta();
}

function renderStartMeta() {
  const meta = $("first-start-meta");
  const s = state.status;
  if (s && s.indexing) {
    meta.textContent = T.startRunning;
    return;
  }
  const pv = state.preview;
  const done = s ? s.files - (s.by_status.pending || 0) : 0;
  const resume = s && done > 0;
  $("start-label").textContent = resume ? T.resumeIndex : pv ? T.indexN(pv.total) : T.startIndexLabel;
  const lead = resume ? T.alreadyDone(done) : `${pv ? `≈ ${fmtDuration(pv.estimate_s)} · ` : ""}${T.startMeta}`;
  meta.replaceChildren(`${lead} · `, el("kbd", null, "↵"));
}

async function stopIndex() {
  try {
    await api("/api/index/cancel", { method: "POST", body: {} });
    toast(state.status && state.status.last_index ? T.stoppedUpdate : T.stoppedFirst);
  } catch (e) {
    toast(T.failed(e.message));
  }
  pollStatus();
}
$("banner-stop").addEventListener("click", stopIndex);
$("first-stop").addEventListener("click", stopIndex);

let previewLoading = false;
async function loadPreview() {
  if (state.preview || previewLoading) return;
  previewLoading = true;
  try {
    state.preview = await api("/api/preview");
    renderPreview(state.preview);
    if (state.status) renderSteps(state.status);
  } catch (e) {
    previewLoading = false;
  }
}

// Search view: what indexing is doing, what already works, and when it ends.
let bannerDone = null;
function renderBanner(s) {
  const p = s.progress;
  const banner = $("banner");
  const busy = s.indexing && ["content", "paused", "scanning", "names", "model"].includes(p.phase);
  $("banner-actions").hidden = true;
  $("banner-resume").hidden = false;
  $("banner-battery").hidden = true;
  banner.classList.remove("is-partial", "is-paused");
  if (!s.indexing && !s.last_index && s.files > 0) {
    // A first run that was stopped: names work, part of the content is missing.
    const pending = s.by_status.pending || 0;
    banner.hidden = false;
    banner.classList.remove("is-done");
    banner.classList.add("is-partial");
    $("banner-close").hidden = true;
    $("banner-stop").hidden = true;
    $("banner-actions").hidden = false;
    $("banner-title").textContent = T.bannerPartial;
    $("banner-pct").textContent = `${Math.floor((100 * (s.files - pending)) / s.files)} %`;
    meter($("banner-meter"), (100 * (s.files - pending)) / s.files);
    $("banner-text").textContent = T.bannerPartialText(pending);
    $("banner-count").textContent = T.bannerCount(s.files - pending, s.files, s.by_status.ok || 0);
    $("banner-eta").textContent = "";
    return;
  }
  if (busy) {
    bannerDone = null;
    banner.hidden = false;
    banner.classList.remove("is-done");
    $("banner-close").hidden = true;
    $("banner-stop").hidden = false;
    const paused = p.phase === "paused";
    banner.classList.toggle("is-paused", paused);
    if (paused) {
      $("banner-actions").hidden = false;
      $("banner-resume").hidden = true;
      $("banner-battery").hidden = false;
    }
    $("banner-title").textContent = paused ? T.bannerPaused : p.first_run ? T.bannerFirst : T.bannerUpdate;
    $("banner-pct").textContent = p.phase === "content" || paused ? `${Math.floor(p.pct)} %` : "";
    meter($("banner-meter"), p.pct);
    $("banner-text").textContent = paused ? T.pausedBattery(p.battery) : p.first_run ? T.bannerFirstText : T.bannerUpdateText;
    $("banner-count").textContent = p.total ? T.bannerCount(p.done, p.total, p.content_ok) : phaseLabel(p);
    if (p.eta_s != null && !paused) state.lastEta = p.eta_s;
    $("banner-eta").textContent = p.eta_s != null && !paused ? T.etaIn(p.eta_s) : "";
    const cur = $("banner-current");
    cur.textContent = p.current && !paused ? T.reading(p.current) : "";
    cur.hidden = !cur.textContent;
    return;
  }
  // Just finished in this page: say so, then step aside.
  const wasBusy = state.status && state.status.indexing;
  if (wasBusy && p.phase === "done") bannerDone = Date.now();
  if (bannerDone && Date.now() - bannerDone < 15000) {
    banner.hidden = false;
    banner.classList.add("is-done");
    $("banner-close").hidden = false;
    $("banner-stop").hidden = true;
    $("banner-title").textContent = p.first_run ? T.bannerReady : T.bannerUpdated;
    $("banner-pct").textContent = "";
    const b = s.by_status;
    $("banner-text").textContent = T.bannerReadyText(s.files, b.ok || 0, b.dataless || 0, s.watching);
    return;
  }
  banner.hidden = true;
}
$("banner-resume").addEventListener("click", () => startIndex(false));

// Continue on battery: explain why indexing paused, then let the user decide for this run.
function openBattery() {
  const s = state.status;
  const p = s.progress;
  $("battery-why").textContent = T.batteryWhy(s.min_battery);
  const facts = [[T.batteryNow, `${p.battery ?? "—"} %`], [T.batteryLeft, `${fmtInt(p.total - p.done)} / ${fmtInt(p.total)}`]];
  if (state.lastEta) facts.push([T.batteryTime, `≈ ${fmtDuration(state.lastEta)}`]);
  $("battery-facts").replaceChildren(...facts.map(([dt, dd]) => { const d = el("div"); d.append(el("dt", null, dt), el("dd", null, dd)); return d; }));
  $("battery-scope").textContent = T.batteryScope;
  $("battery-scrim").hidden = false;
  $("battery-cancel").focus();
}
function closeBattery() {
  $("battery-scrim").hidden = true;
  input.focus();
}
$("banner-battery").addEventListener("click", openBattery);
$("battery-close").addEventListener("click", closeBattery);
$("battery-cancel").addEventListener("click", closeBattery);
$("battery-scrim").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeBattery(); });
$("battery-confirm").addEventListener("click", async () => {
  $("battery-confirm").disabled = true;
  try {
    await api("/api/index/continue", { method: "POST", body: {} });
    closeBattery();
    toast(T.batteryContinued);
  } catch (e) {
    toast(T.failed(e.message));
  }
  $("battery-confirm").disabled = false;
  pollStatus();
});
$("banner-close").addEventListener("click", () => { bannerDone = null; $("banner").hidden = true; input.focus(); });

function renderStatus(s) {
  const p = s.progress;
  // Names are searchable as soon as the walk and the names step are done; a stopped first run keeps them.
  const early = s.indexing && ["model", "scanning", "names"].includes(p.phase);
  const hasIndex = s.files > 0 && (s.last_index || !early);
  if (!hasIndex) {
    showView("onboard");
    loadPreview();
    const running = s.indexing;
    $("start-index").disabled = running;
    $("first-stop").hidden = !running;
    $("first-caption").textContent = running ? T.firstCaptionRunning : T.firstCaption;
    renderSteps(s);
    state.status = s;
    renderStartMeta();
    if (p.phase === "error" && state.status && state.status.indexing) toast(p.message);
    state.status = s;
    return;
  }
  showView("search");
  renderBanner(s);
  state.status = s;
  const chip = $("index-chip");
  chip.classList.toggle("is-busy", s.indexing);
  chip.classList.toggle("is-warning", !s.full_disk_access);
  const tail = s.indexing
    ? (p.phase === "paused" ? T.paused : p.phase === "content" ? `${T.indexing} ${Math.floor(p.pct)} %` : T.indexing)
    : s.last_index ? T.upToDate : T.incomplete;
  $("index-label").textContent = `${T.files(s.files)} · ${tail}`;
  if (!$("status-scrim").hidden) renderStatusDialog();
}

let statusTimer = null;
async function pollStatus() {
  clearTimeout(statusTimer);
  try {
    const s = await api("/api/status");
    const wasIndexing = state.status && state.status.indexing;
    renderStatus(s);
    if (wasIndexing && !s.indexing && state.view === "search") search();
    statusTimer = setTimeout(pollStatus, s.indexing ? 1000 : 15000);
  } catch (e) {
    statusTimer = setTimeout(pollStatus, 3000);
  }
}

// ── Search ─────────────────────────────────────────────────────────────────

let debounce = null;
function scheduleSearch() {
  clearTimeout(debounce);
  debounce = setTimeout(search, 120);
}

async function search() {
  if (state.controller) state.controller.abort();
  const controller = new AbortController();
  state.controller = controller;
  const params = new URLSearchParams({ q: state.q });
  if (state.off.size) params.set("off", [...state.off].join(","));
  if (state.kind) params.set("kind", state.kind);
  if (state.days) params.set("days", state.days);
  list.classList.add("is-stale");
  const refine = state.status && state.status.rerank && state.q.trim();
  try {
    // Two phases: fast results at once, then the re-ranked list replaces them (≈ 80 ms later).
    params.set("rerank", "0");
    render(await api(`/api/search?${params}`, { signal: controller.signal }));
    list.classList.remove("is-stale");
    if (refine && state.results.length > 1) {
      params.set("rerank", "1");
      render(await api(`/api/search?${params}`, { signal: controller.signal }), true);
    }
  } catch (e) {
    if (e.name !== "AbortError") toast(T.failed(e.message));
  } finally {
    if (state.controller === controller) list.classList.remove("is-stale");
  }
}

function render(data, refined = false) {
  const keepId = refined ? state.results[state.selected]?.id : null;
  state.results = data.results;
  state.selected = 0;
  if (keepId != null) {
    const i = data.results.findIndex((r) => r.id === keepId);
    if (i >= 0 && state.listMode) state.selected = i;
  }
  $("ms").textContent = state.q.trim() ? `${Math.round(data.ms)} ms` : "";
  renderChips(data);
  list.replaceChildren(...data.results.map((r, i) => resultRow(r, i)));
  const empty = $("empty");
  empty.hidden = data.results.length > 0;
  empty.textContent = state.q.trim() ? T.noResults : "";
  updateSelection(false);
}

function renderChips(data) {
  const box = $("chips");
  const nodes = [];
  if (!state.q.trim()) {
    const l = document.createElement("span");
    l.className = "ro-eyebrow";
    l.textContent = T.recent;
    nodes.push(l);
  }
  for (const c of data.chips) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-filter";
    b.title = LANG === "fr" ? "Retirer ce filtre" : "Remove this filter";
    const label = document.createElement("span");
    label.textContent = c.label;
    const x = document.createElement("span");
    x.className = "chip-filter__x";
    x.setAttribute("aria-hidden", "true");
    x.textContent = "×";
    b.append(label, x);
    b.setAttribute("aria-label", `${c.label} — ${b.title}`);
    b.addEventListener("click", () => { state.off.add(c.id); search(); input.focus(); });
    nodes.push(b);
  }
  if (data.relaxed) {
    const r = document.createElement("span");
    r.className = "relaxed";
    r.textContent = T.relaxed;
    nodes.push(r);
  }
  box.replaceChildren(...nodes);
}

function highlighted(text, ranges) {
  const frag = document.createDocumentFragment();
  let pos = 0;
  for (const [a, b] of ranges) {
    if (a < pos) continue;
    frag.append(text.slice(pos, a));
    const m = document.createElement("mark");
    m.textContent = text.slice(a, b);
    frag.append(m);
    pos = b;
  }
  frag.append(text.slice(pos));
  return frag;
}

function resultRow(r, i) {
  const li = document.createElement("li");
  li.className = "result";
  li.id = `r${i}`;
  li.setAttribute("role", "option");
  li.dataset.index = String(i);

  const icon = document.createElement("span");
  icon.className = "result__icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = (r.ext || "—").slice(0, 4);

  const name = document.createElement("span");
  name.className = "result__name";
  name.append(highlighted(r.name, r.name_highlights));
  name.title = r.name;

  const date = document.createElement("span");
  date.className = "result__date";
  date.textContent = fmtDate(r.mtime);
  date.title = new Date(r.mtime * 1000).toLocaleString(LANG);

  const path = document.createElement("span");
  path.className = "result__path";
  const bdi = document.createElement("bdi");
  bdi.textContent = r.icloud ? `${r.parent} · ${T.icloud}` : r.parent;
  path.append(bdi);
  path.title = r.path;

  li.append(icon, name, date, path);
  if (r.snippet) {
    const p = document.createElement("p");
    p.className = "result__snippet";
    p.append(highlighted(r.snippet, r.highlights));
    li.append(p);
  }
  if (r.reasons.length) {
    const meta = document.createElement("div");
    meta.className = "result__meta";
    for (const reason of r.reasons) {
      const s = document.createElement("span");
      s.className = "reason";
      s.textContent = T.reasons[reason] || reason;
      meta.append(s);
    }
    li.append(meta);
  }

  li.addEventListener("mousemove", () => { if (state.selected !== i) { state.selected = i; updateSelection(false); } });
  li.addEventListener("click", (e) => { state.selected = i; act(e.metaKey ? "reveal" : "open"); });
  return li;
}

function updateSelection(scroll = true) {
  [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === state.selected)));
  const cur = list.children[state.selected];
  input.setAttribute("aria-activedescendant", cur ? cur.id : "");
  if (scroll && cur) cur.scrollIntoView({ block: "nearest" });
}

// ── Actions ────────────────────────────────────────────────────────────────

async function act(action) {
  const r = state.results[state.selected];
  if (!r) return;
  try {
    await api(`/api/${action}`, { method: "POST", body: { id: r.id, query: state.q, rank: state.selected } });
  } catch (e) {
    toast(e.status === 410 ? T.gone : T.failed(e.message));
  }
}

async function copyPath() {
  const r = state.results[state.selected];
  if (!r) return;
  try {
    await navigator.clipboard.writeText(r.path);
    toast(T.copied);
    api("/api/copied", { method: "POST", body: { id: r.id, query: state.q, rank: state.selected } }).catch(() => {});
  } catch (e) {
    toast(T.failed(e.message));
  }
}

let toastTimer = null;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 1800);
}

// ── Keyboard ───────────────────────────────────────────────────────────────

function syncUrl() {
  const url = new URL(location.href);
  if (state.q) url.searchParams.set("q", state.q);
  else url.searchParams.delete("q");
  history.replaceState(null, "", url);
}

input.addEventListener("input", () => {
  state.q = input.value;
  state.off.clear();
  state.listMode = false;
  scheduleSearch();
  syncUrl();
});

document.addEventListener("keydown", (e) => {
  if (!$("battery-scrim").hidden) {
    if (e.key === "Escape") closeBattery();
    return;
  }
  if (!$("status-scrim").hidden) {
    if (e.key === "Escape") closeStatus();
    return;
  }
  if (state.view === "onboard" && e.key === "Enter" && !$("start-index").disabled) {
    e.preventDefault();
    $("start-index").click();
    return;
  }
  if (state.view !== "search") return;
  const n = state.results.length;
  if (e.key === "ArrowDown" || (e.ctrlKey && e.key === "n")) {
    e.preventDefault();
    if (n) { state.selected = Math.min(n - 1, state.selected + 1); state.listMode = true; updateSelection(); }
  } else if (e.key === "ArrowUp" || (e.ctrlKey && e.key === "p")) {
    e.preventDefault();
    if (n) { state.selected = Math.max(0, state.selected - 1); state.listMode = true; updateSelection(); }
  } else if (e.key === "Enter") {
    e.preventDefault();
    act(e.metaKey ? "reveal" : "open");
  } else if (e.key === "Escape") {
    e.preventDefault();
    input.value = "";
    state.q = "";
    state.off.clear();
    state.listMode = false;
    syncUrl();
    search();
    input.focus();
  } else if (e.key === " " && (state.listMode || document.activeElement !== input)) {
    e.preventDefault();
    act("preview");
  } else if (e.metaKey && e.key.toLowerCase() === "c") {
    const hasSelection = input.selectionStart !== input.selectionEnd && document.activeElement === input;
    if (!hasSelection && !String(window.getSelection())) {
      e.preventDefault();
      copyPath();
    }
  } else if ((e.metaKey && e.key.toLowerCase() === "k") || (e.key === "/" && document.activeElement !== input)) {
    e.preventDefault();
    input.focus();
    input.select();
  } else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && document.activeElement !== input) {
    input.focus();
  }
});

// ── Filters ────────────────────────────────────────────────────────────────

function segmented(groupId, key) {
  const group = $(groupId);
  group.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    group.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    state[key] = b.dataset[key];
    search();
    input.focus();
  });
}
segmented("kind-filter", "kind");
segmented("days-filter", "days");

// ── Status dialog ──────────────────────────────────────────────────────────

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function renderStatusDialog() {
  const s = state.status;
  if (!s) return;
  const body = $("status-body");
  if (state.confirmDelete) return renderDeleteConfirm(s, body);
  $("status-title").textContent = T.statusTitle;
  const errors = (s.by_status.error || 0) + (s.by_status.timeout || 0);
  const kpis = el("dl", "ro-kpis");
  for (const [label, value] of [[T.sDocs, s.files], [T.sContent, s.by_status.ok || 0], [T.sVectors, s.chunks], [T.sErrors, errors]]) {
    const d = el("div");
    d.append(el("dt", null, label), el("dd", null, fmtInt(value)));
    kpis.append(d);
  }
  const nodes = [kpis];

  if (s.indexing && s.progress.total) {
    const sec = el("section");
    const pct = s.progress.pct;
    const eta = s.progress.eta_s != null ? T.etaIn(s.progress.eta_s) : "";
    const head = el("div", "ro-gauge__head");
    head.append(el("span", "ro-gauge__label", phaseLabel(s.progress)), el("span", "ro-gauge__value", `${Math.floor(pct)} %`));
    const m = el("div", "ro-meter");
    m.setAttribute("role", "meter");
    m.setAttribute("aria-valuemin", "0");
    m.setAttribute("aria-valuemax", "100");
    m.setAttribute("aria-label", T.sProgress);
    meter(m, pct);
    const meta = el("div", "ro-gauge__meta");
    meta.append(el("span", null, `${fmtInt(s.progress.done)} / ${fmtInt(s.progress.total)}`), el("span", null, eta));
    sec.append(head, m, meta);
    nodes.push(sec);
  }

  const states = el("section");
  states.append(el("h3", "ro-eyebrow", T.sState));
  const ul = el("ul", "status__list");
  for (const [k, v] of Object.entries(s.by_status).sort((a, b) => b[1] - a[1])) {
    const li = el("li");
    li.append(el("span", null, T.st[k] || k), el("span", "ro-mono", fmtInt(v)));
    ul.append(li);
  }
  states.append(ul);
  nodes.push(states);

  const checks = el("section");
  checks.append(el("h3", "ro-eyebrow", T.sCheck));
  const cl = el("ul", "status__list");
  const row = (label, value, cls) => { const li = el("li"); li.append(el("span", null, label), el("span", cls || "ro-mono", value)); cl.append(li); };
  row(T.sFda, s.full_disk_access ? T.sFdaOk : T.sFdaNo, s.full_disk_access ? "status__ok" : "status__warn");
  row(T.sWatch, s.watching ? T.sOn : T.sOff);
  row(T.sMem, `${fmtInt(Math.round(s.rss_mb))} ${T.mb}`);
  if (s.last_index) row(T.sLast(""), `${fmtDate(s.last_index)}${s.progress.last_run_s ? ` · ${fmtDuration(s.progress.last_run_s)}` : ""}`);
  checks.append(cl);
  nodes.push(checks);

  const folders = el("section");
  folders.append(el("h3", "ro-eyebrow", T.sFolders));
  const fl = el("ul", "status__list");
  s.roots.forEach((r) => fl.append(el("li", "ro-mono", r)));
  const cfg = el("li");
  cfg.append(el("span", null, T.sConfig), el("span", "ro-mono", s.config_path));
  fl.append(cfg);
  folders.append(fl);
  nodes.push(folders);

  if (s.errors.length) {
    const sec = el("section");
    sec.append(el("h3", "ro-eyebrow", T.sErrList));
    const ul2 = el("ul", "status__errors");
    for (const e of s.errors) {
      const li = el("li");
      li.append(el("div", "path", e.path.replace(/^\/Users\/[^/]+/, "~")), el("div", null, e.error || T.st[e.status]));
      ul2.append(li);
    }
    sec.append(ul2);
    nodes.push(sec);
  }

  const actions = el("div", "ro-actions status__tools");
  const upd = el("button", "ro-button", T.sUpdate);
  upd.type = "button";
  upd.disabled = s.indexing;
  upd.addEventListener("click", () => startIndex(false));
  const full = el("button", "ro-button", T.sRebuild);
  full.type = "button";
  full.disabled = s.indexing;
  full.addEventListener("click", () => startIndex(true));
  const del = el("button", "ro-button status__delete", T.sDelete);
  del.type = "button";
  del.addEventListener("click", () => { state.confirmDelete = true; renderStatusDialog(); $("delete-cancel").focus(); });
  actions.append(upd, full, del);
  nodes.push(actions);
  body.replaceChildren(...nodes);
}

// Deleting the index: a second step in the same dialog, with what goes and what stays.
function renderDeleteConfirm(s, body) {
  $("status-title").textContent = T.sDeleteTitle;
  const intro = el("p", "status__text", T.sDeleteWhat(fmtMB(s.index_bytes || 0)));
  const keep = el("p", "status__text", T.sDeleteKeep);
  const all = el("p", "status__hint");
  all.append(T.sUninstallHint, " ", el("code", "ro-mono", "folio uninstall"));
  const actions = el("div", "ro-actions status__confirm");
  const cancel = el("button", "ro-button", T.sCancel);
  cancel.type = "button";
  cancel.id = "delete-cancel";
  cancel.addEventListener("click", () => { state.confirmDelete = false; renderStatusDialog(); });
  const confirm = el("button", "ro-button ro-button--critical", T.sDeleteConfirm);
  confirm.type = "button";
  confirm.addEventListener("click", async () => {
    confirm.disabled = cancel.disabled = true;
    confirm.textContent = T.sDeleting;
    try {
      await api("/api/reset", { method: "POST", body: {} });
      state.confirmDelete = false;
      closeStatus();
      state.results = [];
      list.replaceChildren();
      input.value = state.q = "";
      syncUrl();
      toast(T.sDeleted);
      pollStatus();
    } catch (e) {
      toast(T.failed(e.message));
      confirm.disabled = cancel.disabled = false;
      confirm.textContent = T.sDeleteConfirm;
    }
  });
  actions.append(cancel, confirm);
  body.replaceChildren(intro, keep, all, actions);
}

function openStatus() {
  $("status-scrim").hidden = false;
  renderStatusDialog();
  $("status-close").focus();
}
function closeStatus() {
  state.confirmDelete = false;
  $("status-scrim").hidden = true;
  input.focus();
}
$("index-chip").addEventListener("click", openStatus);
$("status-close").addEventListener("click", closeStatus);
$("status-scrim").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeStatus(); });

async function startIndex(full) {
  try {
    await api("/api/index", { method: "POST", body: { full } });
  } catch (e) {
    if (e.status !== 409) toast(T.failed(e.message));
  }
  pollStatus();
}
$("start-index").addEventListener("click", () => { $("start-index").disabled = true; state.preview = null; previewLoading = false; startIndex(false); });

// ── Theme ──────────────────────────────────────────────────────────────────

$("theme").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("folio-theme", root.dataset.theme); } catch (e) {}
});

applyStrings();
state.q = new URLSearchParams(location.search).get("q") || "";
input.value = state.q;
pollStatus();
