#!/usr/bin/env node
// folio launcher. Sets up the Python environment once (with uv), then runs folio.
// With no arguments: starts the server if needed and opens the page.

import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { homedir, arch, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const UV_VERSION = "0.11.2";
const PKG = dirname(dirname(fileURLToPath(import.meta.url)));
const DATA = process.env.FOLIO_DATA_DIR || join(homedir(), "Library", "Application Support", "folio");
const VENV = join(DATA, "venv");
const PORT = Number(process.env.FOLIO_PORT || 7381);

const dim = (s) => (process.stderr.isTTY ? `\x1b[2m${s}\x1b[0m` : s);
const log = (s) => process.stderr.write(`${s}\n`);

function fail(msg) {
  log(`folio: ${msg}`);
  process.exit(1);
}

if (platform() !== "darwin") fail("folio runs on macOS only.");

function which(cmd) {
  const r = spawnSync("/usr/bin/which", [cmd], { encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : null;
}

async function ensureUv() {
  for (const p of [process.env.FOLIO_UV, which("uv"), join(homedir(), ".local/bin/uv"), "/opt/homebrew/bin/uv", join(DATA, "bin", "uv")]) {
    if (p && existsSync(p)) return p;
  }
  // Standalone uv binary from its GitHub release (≈ 18 MB, once).
  const target = arch() === "arm64" ? "aarch64-apple-darwin" : "x86_64-apple-darwin";
  const url = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${target}.tar.gz`;
  log(dim(`Downloading uv ${UV_VERSION} (Python package manager, once)…`));
  const res = await fetch(url);
  if (!res.ok) fail(`couldn't download uv: HTTP ${res.status} from ${url}`);
  const dir = join(DATA, "bin");
  mkdirSync(dir, { recursive: true });
  const tgz = join(dir, "uv.tar.gz");
  writeFileSync(tgz, Buffer.from(await res.arrayBuffer()));
  const t = spawnSync("tar", ["-xzf", tgz, "-C", dir, "--strip-components", "1"], { stdio: "inherit" });
  rmSync(tgz, { force: true });
  if (t.status !== 0) fail("couldn't unpack uv.");
  return join(dir, "uv");
}

function lockHash() {
  const h = createHash("sha256");
  h.update(readFileSync(join(PKG, "uv.lock")));
  h.update(readFileSync(join(PKG, "pyproject.toml")));
  return h.digest("hex").slice(0, 16);
}

async function ensureEnv() {
  const stamp = join(VENV, ".folio-lock");
  const want = lockHash();
  if (existsSync(join(VENV, "bin", "python")) && existsSync(stamp) && readFileSync(stamp, "utf8") === want) return;
  const uv = await ensureUv();
  const t0 = Date.now();
  log(dim("Installing folio's Python environment (once)…"));
  mkdirSync(DATA, { recursive: true });
  const r = spawnSync(
    uv,
    ["sync", "--frozen", "--no-dev", "--no-install-project", "--python", "3.13", "--project", PKG, "--quiet"],
    { stdio: "inherit", env: { ...process.env, UV_PROJECT_ENVIRONMENT: VENV, UV_PYTHON_PREFERENCE: "managed" } },
  );
  if (r.status !== 0) fail("the Python environment couldn't be installed (see above).");
  writeFileSync(stamp, want);
  log(dim(`Ready in ${((Date.now() - t0) / 1000).toFixed(1)} s.`));
}

async function serverUp() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/ping`, { signal: AbortSignal.timeout(500) });
    return r.ok;
  } catch {
    return false;
  }
}

function python(args, opts = {}) {
  return spawn(join(VENV, "bin", "python"), ["-m", "folio", ...args], {
    stdio: "inherit",
    ...opts,
    env: { ...process.env, PYTHONPATH: join(PKG, "src"), PYTHONDONTWRITEBYTECODE: "1", ...(opts.env || {}) },
  });
}

const args = process.argv.slice(2);
if (args[0] === "--version" || args[0] === "-v") {
  log(JSON.parse(readFileSync(join(PKG, "package.json"), "utf8")).version);
  process.exit(0);
}

await ensureEnv();

if (args.length === 0) {
  // Default: open the page, starting the server first if it isn't running.
  const url = `http://127.0.0.1:${PORT}/`;
  if (await serverUp()) {
    spawnSync("open", [url]);
    log(`folio is running at ${url}`);
    process.exit(0);
  }
  const child = python(["serve", "--open"]);
  child.on("exit", (code) => process.exit(code ?? 0));
} else {
  const child = python(args);
  child.on("exit", (code) => process.exit(code ?? 0));
}
