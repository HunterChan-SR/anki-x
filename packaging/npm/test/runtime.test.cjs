const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { zipSync } = require('fflate');
const { platformKey, unpack, ensureRuntime } = require('../lib/runtime.cjs');

async function temp(t) {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'anki-x-npm-test-'));
  t.after(() => fs.rm(folder, { recursive: true, force: true }));
  return folder;
}
const sha = data => createHash('sha256').update(data).digest('hex');

test('reject corrupt download and traversal before writing', async t => {
  const folder = await temp(t);
  const data = zipSync({ 'anki-x/../escape': Buffer.from('bad') });
  await assert.rejects(unpack(data, '0'.repeat(64), folder), /checksum/);
  await assert.rejects(unpack(data, sha(data), folder), /Unsafe/);
  assert.deepEqual(await fs.readdir(folder), []);
});

test('concurrent first launches download once, cached launch works offline', async t => {
  const cache = await temp(t);
  const name = process.platform === 'win32' ? 'anki-x.exe' : 'anki-x';
  const data = zipSync({ [`anki-x/${name}`]: Buffer.from('native runtime') });
  const manifest = { version: '1.0.0rc2', platforms: { [platformKey()]: { sha256: sha(data), url: 'fixture' } } };
  let calls = 0;
  const download = async () => { calls++; await new Promise(r => setTimeout(r, 300)); return data; };
  const binaries = await Promise.all([ensureRuntime(manifest, { cache, download }), ensureRuntime(manifest, { cache, download })]);
  assert.equal(calls, 1);
  assert.equal(binaries[0], binaries[1]);
  assert.equal(await fs.readFile(binaries[0], 'utf8'), 'native runtime');
  await ensureRuntime(manifest, { cache, download: () => { throw Error('offline'); } });
});

test('failed download can be retried without a stale lock', async t => {
  const cache = await temp(t);
  const manifest = { version: '1.0.0rc2', platforms: { [platformKey()]: { sha256: '0'.repeat(64), url: 'fixture' } } };
  await assert.rejects(ensureRuntime(manifest, { cache, download: async () => { throw Error('offline'); } }), /offline/);
  assert.deepEqual(await fs.readdir(cache), []);
});

test('unsupported architectures fail with actionable message', () => {
  assert.throws(() => platformKey('win32', 'arm64'), /Unsupported platform/);
  assert.throws(() => platformKey('linux', 'arm64'), /Unsupported platform/);
});
