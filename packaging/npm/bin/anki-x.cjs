#!/usr/bin/env node
'use strict';
const { spawn } = require('node:child_process');
const { ensureRuntime } = require('../lib/runtime.cjs');

async function main() {
  const manifest = require('../manifest.json');
  const executable = await ensureRuntime(manifest);
  const child = spawn(executable, process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env, ANKI_X_PACKAGE_MANAGER: 'npm' },
  });
  // The terminal sends Ctrl+C to the whole foreground process group. Let the
  // native client finish saving before the wrapper exits.
  const interrupt = () => {};
  const terminate = () => child.kill('SIGTERM');
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  child.once('error', fail);
  child.once('exit', (code, signal) => {
    process.removeListener('SIGINT', interrupt);
    process.removeListener('SIGTERM', terminate);
    process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 143);
  });
}
function fail(error) {
  console.error(`anki-x: ${error.message}`);
  process.exitCode = 1;
}
main().catch(fail);
