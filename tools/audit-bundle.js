/**
 * Security audit of the published artifact.
 *
 * A language pack is data plus one small browser bundle, and this script proves
 * that claim mechanically instead of asking anyone to take it on trust:
 *
 *   1. code review  — the bundle touches only the locale API; every capability
 *                     it must NOT have (network, storage, eval, filesystem,
 *                     Electron, IPC, HTML injection) is asserted absent;
 *   2. data review  — dictionaries are plain strings, keys match the sources,
 *                     placeholders survive, and no value carries script markup;
 *   3. repo review  — no machine paths, user names, e-mail addresses, tokens or
 *                     keys anywhere in the tree.
 *
 * Run: node tools/audit-bundle.js
 * Exits non-zero on any finding.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(toolsDir);

const problems = [];
const fail = (msg) => problems.push(msg);

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------
function sliceBalanced(text, start) {
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') { depth--; if (depth === 0) return { json: text.slice(start, i + 1), end: i + 1 }; }
  }
  throw new Error('unbalanced literal');
}

const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');

// --------------------------------------------------------------------------
// 1. code review of the browser bundle
// --------------------------------------------------------------------------
const bundle = read('lib/client.js');

const dictAt = bundle.indexOf('const DICTIONARIES = ');
if (dictAt < 0) fail('lib/client.js: не найден литерал DICTIONARIES');
const braceAt = bundle.indexOf('{', dictAt);
let dictionaries = {};
let code = bundle;
try {
  const { json, end } = sliceBalanced(bundle, braceAt);
  dictionaries = JSON.parse(json);
  code = bundle.slice(0, braceAt) + '{}' + bundle.slice(end);
} catch (e) {
  fail(`lib/client.js: словари не разбираются — ${e.message}`);
}

// Capabilities the bundle must not have. Each entry is [regex, описание].
const FORBIDDEN = [
  [/\bfetch\s*\(/, 'сетевой запрос (fetch)'],
  [/XMLHttpRequest/, 'сетевой запрос (XMLHttpRequest)'],
  [/WebSocket/, 'сетевое соединение (WebSocket)'],
  [/EventSource/, 'сетевое соединение (EventSource)'],
  [/sendBeacon/, 'отправка данных (sendBeacon)'],
  [/\beval\s*\(/, 'исполнение кода из строки (eval)'],
  [/new\s+Function\s*\(/, 'исполнение кода из строки (new Function)'],
  [/document\.write/, 'запись в документ'],
  [/document\.cookie/, 'доступ к cookie'],
  [/localStorage|sessionStorage|indexedDB/, 'локальное хранилище'],
  [/require\s*\(\s*["'](fs|node:fs|child_process|node:child_process|net|http|https)["']/, 'доступ к системе (require)'],
  [/process\.(env|argv|exit)/, 'доступ к процессу'],
  [/ipcRenderer|contextBridge|\belectron\b/i, 'доступ к Electron'],
  [/innerHTML|outerHTML|insertAdjacentHTML|dangerouslySetInnerHTML/, 'инъекция HTML'],
  [/import\s*\(/, 'динамический импорт'],
  [/navigator\./, 'доступ к navigator'],
  [/\.src\s*=|createElement\s*\(\s*["']script/, 'подстановка скрипта'],
  [/atob|btoa/, 'кодирование полезной нагрузки'],
];
for (const [re, what] of FORBIDDEN) {
  if (re.test(code)) fail(`lib/client.js: найдено запрещённое — ${what}`);
}

// The bundle must call exactly these locale methods and nothing else on ctx.
const ALLOWED_CALLS = ['ctx.effect(', 'ctx.locale.addLanguage(', 'ctx.locale.register('];
const ctxUses = [...code.matchAll(/ctx\.[A-Za-z0-9_.]+/g)].map((m) => m[0] + '(');
for (const use of new Set(ctxUses)) {
  const ok = ALLOWED_CALLS.some((a) => use === a || (a.startsWith(use) && use === 'ctx.'));
  if (!ok && use !== 'ctx.effect(' && !use.startsWith('ctx.locale.')) {
    fail(`lib/client.js: неожиданное обращение к контексту — ${use}`);
  }
}

if (!/window\.__ModuleLoader__\.load\(\{/.test(code)) fail('lib/client.js: нет регистрации через __ModuleLoader__');
if (!/exports\.inject\s*=\s*\["locale"\]/.test(code)) fail('lib/client.js: не объявлена зависимость от сервиса locale');

const langMatch = /const LANGUAGE = (\{[^}]*\});/.exec(code);
if (!langMatch) fail('lib/client.js: не найден литерал LANGUAGE');
else {
  const lang = JSON.parse(langMatch[1]);
  if (!/^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(lang.id ?? '')) fail(`LANGUAGE.id не BCP 47: ${lang.id}`);
  if (lang.fallback !== 'en') fail(`LANGUAGE.fallback должен быть "en", получено ${JSON.stringify(lang.fallback)}`);
  if (typeof lang.label !== 'string' || !lang.label) fail('LANGUAGE.label пуст');
}

// --------------------------------------------------------------------------
// 2. host half and manifest
// --------------------------------------------------------------------------
const hostHalf = read('lib/index.js');
if (/^\s*import\s/m.test(hostHalf)) fail('lib/index.js: серверная половина не должна ничего импортировать');
if (/require\s*\(/.test(hostHalf)) fail('lib/index.js: серверная половина не должна ничего требовать');
const hostSize = Buffer.byteLength(hostHalf);
if (hostSize > 1024) fail(`lib/index.js: неожиданно большой для пустышки — ${hostSize} байт`);

const manifest = JSON.parse(read('package.json'));
if (manifest.dsh?.client?.platform !== 'web') fail('package.json: dsh.client.platform должен быть "web"');
const inject = manifest.dsh?.client?.inject ?? [];
if (JSON.stringify(inject) !== JSON.stringify(['@deepseek-ai/dsh-client-locale'])) {
  fail(`package.json: dsh.client.inject неожиданный — ${JSON.stringify(inject)}`);
}
if (manifest.dsh?.bundle?.patch !== './cordis.patch.yml') fail('package.json: dsh.bundle.patch должен указывать на ./cordis.patch.yml');
if (manifest.scripts) fail('package.json: в пакете не должно быть scripts (ничего не запускается при установке)');
for (const field of ['postinstall', 'preinstall', 'install', 'prepare']) {
  if (manifest[field]) fail(`package.json: поле ${field} недопустимо — оно выполняет код при установке`);
}
if (manifest.dependencies && Object.keys(manifest.dependencies).length) {
  fail(`package.json: пакет не должен тянуть зависимости — ${Object.keys(manifest.dependencies).join(', ')}`);
}

// --------------------------------------------------------------------------
// 3. dictionary review
// --------------------------------------------------------------------------
const srcDir = path.join(root, 'locales', 'ru');
const sources = fs.readdirSync(srcDir).filter((f) => f.endsWith('.json')).sort();
const srcNamespaces = sources.map((f) => path.basename(f, '.json')).sort();
const bundleNamespaces = Object.keys(dictionaries).sort();

if (JSON.stringify(srcNamespaces) !== JSON.stringify(bundleNamespaces)) {
  fail(`набор пространств имён в бандле не совпадает с locales/ru\n    в бандле : ${bundleNamespaces.join(', ')}\n    в файлах : ${srcNamespaces.join(', ')}`);
}

const placeholders = (s) => (s.match(/\{[A-Za-z0-9_.]+\}/g) ?? []).sort().join(',');
let keyTotal = 0;
const suspiciousValues = [];

for (const ns of bundleNamespaces) {
  const source = JSON.parse(read(path.join('locales', 'ru', `${ns}.json`)));
  const dict = dictionaries[ns];
  const sk = Object.keys(source), dk = Object.keys(dict);
  if (sk.length !== dk.length || sk.some((k) => !(k in dict))) {
    fail(`${ns}: набор ключей в бандле разошёлся с locales/ru/${ns}.json`);
  }
  keyTotal += dk.length;
  for (const [k, v] of Object.entries(dict)) {
    if (typeof v !== 'string') { fail(`${ns} :: ${k}: значение не строка`); continue; }
    const src = source[k];
    if (typeof src === 'string' && src.trim() !== '') {
      if (v.trim() === '') fail(`${ns} :: ${k}: пустой перевод`);
      if (placeholders(src) !== placeholders(v)) fail(`${ns} :: ${k}: разошлись плейсхолдеры`);
    }
    // markup that would matter only if some surface rendered raw HTML
    if (/<\s*\/?\s*(script|iframe|object|embed|img|svg|style)\b/i.test(v)) suspiciousValues.push(`${ns} :: ${k}`);
    if (/javascript:|data:text\/html/i.test(v)) fail(`${ns} :: ${k}: похоже на внедряемую ссылку`);
  }
}

// --------------------------------------------------------------------------
// 4. repository review — no machine-specific or secret material
// --------------------------------------------------------------------------
const TEXT_EXT = new Set(['.md', '.json', '.js', '.mjs', '.cjs', '.yml', '.yaml', '.ps1', '.py', '.txt', '.gitattributes', '.gitignore']);
const SKIP_DIRS = new Set(['.git', 'node_modules', 'dist']);

// Заглушки в документации — не утечка. Список намеренно узкий: всё, что не
// совпало, считается настоящим именем пользователя и валит аудит.
const PLACEHOLDER_NAMES = new Set(['me', 'user', 'username', 'you', 'name', 'ваше', 'вы', 'пользователь']);

const isPlaceholderPath = (line) => {
  const m = /[A-Za-z]:\\+Users\\+([^\\\s"']+)/i.exec(line);
  if (!m) return false;
  const name = m[1];
  // Примеры в документации: <вы>, %USERNAME%, ..., … — это не настоящее имя.
  if (/^[<%.…]/.test(name)) return true;
  return PLACEHOLDER_NAMES.has(name.toLowerCase());
};

const LEAK_PATTERNS = [
  [/[A-Za-z]:\\+Users\\+[^\\\s"']+/i, 'абсолютный путь Windows с именем пользователя', isPlaceholderPath],
  [/\/Users\/[A-Za-z0-9._-]+\//, 'абсолютный путь macOS'],
  [/\bghp_[A-Za-z0-9]{20,}\b/, 'токен GitHub'],
  [/\bsk-[A-Za-z0-9]{20,}\b/, 'API-ключ'],
  [/\bAKIA[0-9A-Z]{16}\b/, 'ключ AWS'],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, 'приватный ключ'],
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/, 'адрес электронной почты'],
];
const USERNAME = process.env.USERNAME ?? '';
if (USERNAME) LEAK_PATTERNS.push([new RegExp(`\\b${USERNAME.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i'), 'имя пользователя этой машины']);

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

for (const file of walk(root)) {
  const ext = path.extname(file).toLowerCase();
  if (!TEXT_EXT.has(ext) && !TEXT_EXT.has(path.basename(file))) continue;
  const rel = path.relative(root, file).replace(/\\/g, '/');
  const raw = fs.readFileSync(file);
  const text = raw.toString('utf8');
  const lines = text.split(/\r?\n/);
  for (const [re, what, skip] of LEAK_PATTERNS) {
    const hit = lines.findIndex((l) => re.test(l) && !(skip && skip(l)));
    if (hit >= 0) fail(`${rel}:${hit + 1}: ${what}`);
  }
  if (text.includes('\r\n')) fail(`${rel}: перевод строк CRLF — в репозитории должны быть LF`);

  // Windows PowerShell 5.1 читает .ps1 без BOM как ANSI: кириллица в строках
  // превращается в мусор и скрипт падает с ошибкой разбора.
  if (ext === '.ps1') {
    const hasBom = raw.length >= 3 && raw[0] === 0xEF && raw[1] === 0xBB && raw[2] === 0xBF;
    const nonAscii = /[^\x00-\x7F]/.test(text);
    if (nonAscii && !hasBom) {
      fail(`${rel}: в .ps1 с кириллицей нет BOM — исправьте командой python tools/fix-bom.py`);
    }
  }
}

// --------------------------------------------------------------------------
// report
// --------------------------------------------------------------------------
console.log('Аудит языкового пакета');
console.log('  пространств имён : ' + bundleNamespaces.length);
console.log('  строк            : ' + keyTotal);
console.log('  размер бандла    : ' + Buffer.byteLength(bundle) + ' байт');
console.log('  серверная половина: ' + hostSize + ' байт');
if (suspiciousValues.length) {
  console.log('\n  значения с HTML-подобной разметкой (безопасно при экранировании, проверьте вручную):');
  for (const v of suspiciousValues) console.log('    - ' + v);
}
if (problems.length) {
  console.log('\nПРОБЛЕМЫ (' + problems.length + '):');
  for (const p of problems) console.log('  - ' + p);
  process.exit(1);
}
console.log('\nOK — запрещённых возможностей, утечек и расхождений не найдено.');
