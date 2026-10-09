/**
 * Contract check for the built browser bundle.
 *
 * Loads `lib/client.js` through a stub of the client module system, drives its
 * `apply(ctx)` with a recording fake locale service, and asserts the exact
 * registration contract the real runtime expects:
 *   - one `addLanguage({ id, label, fallback })` with an ASCII tag and an
 *     already-shipped fallback;
 *   - one `register(ns, 'ru', dict)` per namespace, with dictionary keys equal
 *     to the English key set for that namespace.
 *
 * Run: node tools/verify.js
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(toolsDir);
const bundlePath = path.join(root, 'lib', 'client.js');
const localesDir = path.join(root, 'locales', 'ru');

// --- stub the browser module system -------------------------------------
let registrations = [];
let factory;
const previousWindow = globalThis.window;
globalThis.window = {
  __ModuleLoader__: {
    load(entry) { factory = entry.factory; },
  },
};

try {
  // The bundle is a plain script that registers itself.
  const source = fs.readFileSync(bundlePath, 'utf8');
  const run = new Function('window', source);
  run(globalThis.window);
} finally {
  if (previousWindow === undefined) delete globalThis.window;
  else globalThis.window = previousWindow;
}

if (typeof factory !== 'function') {
  console.error('FAIL: bundle did not register a factory');
  process.exit(1);
}

const mod = factory((id) => {
  throw new Error(`unexpected module request: ${id}`);
});

if (typeof mod.apply !== 'function') {
  console.error('FAIL: bundle exports no apply()');
  process.exit(1);
}

// --- drive apply() with a recording locale service -----------------------
const fakeCtx = {
  effect(run) { const d = run(); return typeof d === 'function' ? d : () => {}; },
  locale: {
    addLanguage(input) { registrations.push({ kind: 'language', input }); return () => {}; },
    register(...args) { registrations.push({ kind: 'register', ns: args[0], locale: args[1], dict: args[2] }); return () => {}; },
  },
};

mod.apply(fakeCtx);

// --- assertions ----------------------------------------------------------
const problems = [];

const languages = registrations.filter((r) => r.kind === 'language');
if (languages.length !== 1) problems.push(`expected exactly 1 addLanguage call, got ${languages.length}`);
const language = languages[0]?.input ?? {};
if (!/^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(language.id ?? '')) problems.push(`language id "${language.id}" is not a BCP 47-style ASCII tag`);
if (language.fallback !== 'en') problems.push(`language fallback must be "en", got ${JSON.stringify(language.fallback)}`);
if (typeof language.label !== 'string' || language.label.length === 0) problems.push('language label is missing');

const expectedNamespaces = fs.readdirSync(localesDir)
  .filter((f) => f.endsWith('.json'))
  .map((f) => path.basename(f, '.json'))
  .filter((ns) => Object.keys(JSON.parse(fs.readFileSync(path.join(localesDir, ns + '.json'), 'utf8'))).length > 0)
  .sort();

const registered = registrations.filter((r) => r.kind === 'register');
const registeredNs = registered.map((r) => r.ns).sort();

if (JSON.stringify(registeredNs) !== JSON.stringify(expectedNamespaces)) {
  problems.push(`namespace mismatch\n  registered: ${registeredNs.join(', ')}\n  expected  : ${expectedNamespaces.join(', ')}`);
}

let totalKeys = 0;
for (const r of registered) {
  if (r.locale !== 'ru') problems.push(`namespace "${r.ns}" registered under locale "${r.locale}", expected "ru"`);
  const source = JSON.parse(fs.readFileSync(path.join(localesDir, r.ns + '.json'), 'utf8'));
  const srcKeys = Object.keys(source).sort();
  const outKeys = Object.keys(r.dict ?? {}).sort();
  if (JSON.stringify(srcKeys) !== JSON.stringify(outKeys)) problems.push(`namespace "${r.ns}" key set changed during build`);
  totalKeys += outKeys.length;
}

// placeholders must survive translation
const placeholder = /\{[A-Za-z0-9_.]+\}/g;
for (const r of registered) {
  const source = JSON.parse(fs.readFileSync(path.join(localesDir, r.ns + '.json'), 'utf8'));
  for (const [key, value] of Object.entries(r.dict)) {
    const before = (source[key].match(placeholder) ?? []).sort().join(',');
    const after = (value.match(placeholder) ?? []).sort().join(',');
    if (before !== after) problems.push(`placeholder drift in ${r.ns} :: ${key}: ${before} -> ${after}`);
  }
}

if (problems.length > 0) {
  console.error('FAIL');
  for (const p of problems) console.error('  - ' + p);
  process.exit(1);
}

console.log(`OK  language=${language.id} (${language.label}), namespaces=${registered.length}, keys=${totalKeys}`);
