'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { unzipSync } = require('fflate');

function platformKey(platform = process.platform, arch = process.arch) {
  const key = `${platform}-${arch}`;
  if (!['darwin-arm64', 'darwin-x64', 'linux-x64', 'win32-x64'].includes(key)) {
    throw new Error(`Unsupported platform ${key}. See https://github.com/HunterChan-SR/anki-x#readme`);
  }
  if (platform === 'linux' && !process.report.getReport().header.glibcVersionRuntime) {
    throw new Error('Linux requires glibc; Alpine/musl is not supported.');
  }
  return key;
}

function cacheRoot() {
  if (process.env.ANKI_X_NPM_CACHE) return path.resolve(process.env.ANKI_X_NPM_CACHE);
  if (process.platform === 'win32') return path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'anki-x', 'npm');
  if (process.platform === 'darwin') return path.join(os.homedir(), 'Library', 'Caches', 'anki-x', 'npm');
  return path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'anki-x', 'npm');
}

async function unpack(buffer, digest, destination) {
  if (createHash('sha256').update(buffer).digest('hex') !== digest) {
    throw new Error('Download checksum mismatch. No program was installed; please retry.');
  }
  const files = unzipSync(buffer);
  const names = Object.keys(files);
  // Validate the entire archive before writing any file. Release archives only
  // contain regular files; fflate never creates symlinks from ZIP metadata.
  for (const name of names) {
    const parts = name.split('/');
    if (!name.startsWith('anki-x/') || /[\\:\x00]/.test(name) || parts.includes('..') || parts.includes('.')) {
      throw new Error(`Unsafe release archive path: ${name}`);
    }
  }
  for (const name of names) {
    const target = path.join(destination, name);
    if (name.endsWith('/')) await fs.mkdir(target, { recursive: true });
    else {
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.writeFile(target, files[name], { mode: 0o644, flag: 'wx' });
    }
  }
}

async function download(url) {
  const parsed = new URL(url);
  if (parsed.origin !== 'https://github.com' || !parsed.pathname.startsWith('/HunterChan-SR/anki-x/releases/download/')) {
    throw new Error('Unexpected release URL.');
  }
  const response = await fetch(url, { signal: AbortSignal.timeout(120000) });
  if (!response.ok) throw new Error(`Download failed (HTTP ${response.status}). Check your connection and retry.`);
  return Buffer.from(await response.arrayBuffer());
}

async function ensureRuntime(manifest, options = {}) {
  const key = platformKey();
  const asset = manifest.platforms[key];
  if (!asset || !/^[a-zA-Z0-9.\-]+$/.test(manifest.version) || !/^[a-f0-9]{64}$/.test(asset.sha256)) {
    throw new Error('Invalid release manifest. Reinstall anki-x with npm.');
  }
  const root = options.cache || cacheRoot();
  const target = path.join(root, `${manifest.version}-${key}-${asset.sha256.slice(0, 12)}`);
  const binary = path.join(target, 'anki-x', process.platform === 'win32' ? 'anki-x.exe' : 'anki-x');
  const ready = path.join(target, '.ready');
  const exists = async () => {
    try { return (await fs.readFile(ready, 'utf8')) === asset.sha256 && (await fs.stat(binary)).isFile(); }
    catch { return false; }
  };
  if (await exists()) return binary;
  await fs.mkdir(root, { recursive: true });
  const lock = `${target}.lock`;
  const deadline = Date.now() + 150000;
  while (true) {
    try { await fs.mkdir(lock); break; }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      if (await exists()) return binary;
      if (Date.now() > deadline) throw new Error(`Another download did not finish. Close other anki-x processes, remove ${lock}, and retry.`);
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }
  let stage;
  try {
    if (await exists()) return binary;
    console.error(`anki-x: downloading native runtime ${manifest.version} (first launch only)…`);
    const buffer = await (options.download || download)(asset.url);
    stage = await fs.mkdtemp(path.join(root, '.download-'));
    await unpack(buffer, asset.sha256, stage);
    const stagedBinary = path.join(stage, 'anki-x', path.basename(binary));
    if (!(await fs.stat(stagedBinary)).isFile()) throw new Error('Release executable is missing.');
    await fs.chmod(stagedBinary, 0o755);
    await fs.writeFile(path.join(stage, '.ready'), asset.sha256);
    // Only touch this version's cache, never the user's Anki data or settings.
    await fs.rm(target, { recursive: true, force: true });
    await fs.rename(stage, target);
    stage = null;
    return binary;
  } finally {
    if (stage) await fs.rm(stage, { recursive: true, force: true });
    await fs.rmdir(lock);
  }
}
module.exports = { platformKey, unpack, ensureRuntime };
