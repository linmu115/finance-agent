/**
 * Narrow, offline repair for Pi 1.0.0's published npm-shrinkwrap pin.
 * npm ignores root overrides for this pinned nested brace-expansion package.
 * Only official brace-expansion 5.0.12 files and three matching lock entries
 * are updated; no library source is rewritten and no network request occurs.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';

const root = fs.realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const checkOnly = process.argv.includes('--check');
const integrity = 'sha512-YovQ3rzhaLMIrDjNDMkNS01tea93qhEhG5xy8f6+R0l+dw3Ki+5sCoIoI942iuLZTHWogWktgwVDhU09iNEimQ==';
const version = '5.0.12';
const resolved = 'https://registry.npmjs.org/brace-expansion/-/brace-expansion-5.0.12.tgz';
const packagePath = 'node_modules/@earendil-works/pi-coding-agent/node_modules/brace-expansion';
const piPath = 'node_modules/@earendil-works/pi-coding-agent';
const target = path.join(root, packagePath);
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function assertSafePath(candidate) {
  const relative = path.relative(root, path.resolve(candidate));
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Dependency repair path escapes project root');
  let current = root;
  for (const part of relative.split(path.sep)) {
    current = path.join(current, part);
    if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) throw new Error('Dependency repair refuses symbolic links: ' + path.relative(root, current));
  }
}

function unpackVerifiedTar(archive) {
  const actual = 'sha512-' + createHash('sha512').update(archive).digest('base64');
  if (actual !== integrity) throw new Error('Official brace-expansion tarball integrity mismatch; no files were changed');
  const tar = gunzipSync(archive, { maxOutputLength: 1024 * 1024 });
  const entries = new Map();
  const text = (buffer, start, end) => buffer.subarray(start, end).toString('utf8').replace(/\0.*$/s, '');
  for (let offset = 0; offset + 512 <= tar.length;) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every(byte => byte === 0)) break;
    const sum = [...header].reduce((total, byte, index) => total + (index >= 148 && index < 156 ? 32 : byte), 0);
    if (sum !== Number.parseInt(text(header, 148, 156).trim(), 8)) throw new Error('Invalid tar header checksum');
    const prefix = text(header, 345, 500); const base = text(header, 0, 100);
    const name = prefix ? prefix + '/' + base : base;
    const size = Number.parseInt(text(header, 124, 136).trim(), 8);
    const type = String.fromCharCode(header[156]);
    if (!Number.isSafeInteger(size) || size < 0 || size > 1024 * 1024 || offset + 512 + size > tar.length) throw new Error('Invalid tar entry size');
    if (!['0', '\0'].includes(type)) throw new Error('Repair archive must contain ordinary files only');
    if (!name.startsWith('package/') || name.includes('\\') || name.includes(':') || name.split('/').includes('..')) throw new Error('Unsafe tar path');
    const relative = name.slice('package/'.length);
    if (!relative || path.posix.normalize(relative) !== relative || entries.has(relative)) throw new Error('Unexpected or duplicate package path');
    entries.set(relative, tar.subarray(offset + 512, offset + 512 + size));
    offset += 512 + Math.ceil(size / 512) * 512;
  }
  if (entries.size !== 13) throw new Error('Unexpected official package file count');
  const manifest = JSON.parse(entries.get('package.json')?.toString('utf8') || '{}');
  if (manifest.name !== 'brace-expansion' || manifest.version !== version) throw new Error('Unexpected package identity');
  return { entries, manifest };
}

function patchLock(relative, key, manifest) {
  const filename = path.join(root, relative); assertSafePath(filename);
  if (!fs.existsSync(filename)) throw new Error('Required npm lockfile missing: ' + relative);
  const lock = readJson(filename); const entry = lock.packages?.[key];
  if (!entry || !['5.0.9', version].includes(entry.version)) throw new Error('Unexpected brace-expansion lock entry; review upstream update: ' + relative);
  const expected = { ...entry, version, resolved, integrity, dependencies: manifest.dependencies, engines: manifest.engines, license: manifest.license };
  const changed = JSON.stringify(entry) !== JSON.stringify(expected);
  if (changed && checkOnly) throw new Error('Dependency lock is not repaired: ' + relative + '; run npm run deps:repair');
  if (changed) { lock.packages[key] = expected; fs.writeFileSync(filename, JSON.stringify(lock, null, 2) + '\n'); }
  return { path: relative, changed, version, sha256: hash(fs.readFileSync(filename)) };
}

function main() {
  assertSafePath(target);
  const pi = readJson(path.join(root, piPath, 'package.json'));
  if (pi.name !== '@earendil-works/pi-coding-agent' || pi.version !== '1.0.0') throw new Error('This repair is scoped to Pi 1.0.0; review and remove it when upgrading Pi');
  const installed = readJson(path.join(target, 'package.json'));
  if (installed.name !== 'brace-expansion' || !['5.0.9', version].includes(installed.version)) throw new Error('Unexpected installed brace-expansion version; refusing to downgrade or broaden repair');
  const archivePath = path.join(root, 'vendor/brace-expansion-5.0.12.tgz'); assertSafePath(archivePath);
  const { entries, manifest } = unpackVerifiedTar(fs.readFileSync(archivePath));
  let changedFiles = 0;
  for (const [relative, bytes] of entries) {
    const filename = path.join(target, relative); assertSafePath(filename);
    const identical = fs.existsSync(filename) && fs.readFileSync(filename).equals(bytes);
    if (!identical) {
      if (checkOnly) throw new Error('Installed dependency is not the verified official 5.0.12 package; run npm run deps:repair');
      fs.mkdirSync(path.dirname(filename), { recursive: true }); fs.writeFileSync(filename, bytes); changedFiles++;
    }
  }
  const locks = [
    patchLock('package-lock.json', packagePath, manifest),
    patchLock('node_modules/.package-lock.json', packagePath, manifest),
    patchLock(piPath + '/npm-shrinkwrap.json', 'node_modules/brace-expansion', manifest),
  ];
  for (const [relative, bytes] of entries) if (!fs.readFileSync(path.join(target, relative)).equals(bytes)) throw new Error('Post-repair file verification failed');
  if (!checkOnly) {
    const directory = path.join(root, 'scripts/dependency-evidence'); fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, 'repair-latest.json'), JSON.stringify({ timestamp: new Date().toISOString(), package: 'brace-expansion', priorVersion: installed.version, version, integrity, source: resolved, changedFiles, verifiedFiles: entries.size, locks, node: process.version, scope: 'Only the nested dependency pinned by Pi 1.0.0 shrinkwrap; no network or upstream source changes' }, null, 2) + '\n');
  }
  console.log('[dependency integrity] brace-expansion ' + version + ': ' + entries.size + ' official files and 3 lock entries verified' + (checkOnly ? '' : '; ' + changedFiles + ' files updated'));
}
try { main(); } catch (error) { console.error('[dependency integrity] ' + error.message); process.exitCode = 1; }
