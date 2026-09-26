#!/usr/bin/env node
'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const NAME = 'cinematic-storyboard';
const MARKER = '.cinematic-storyboard-install.json';
const CONTENT = ['SKILL.md', 'AGENTS.md', 'agents', 'assets', 'references', 'scripts', 'tests', 'README.md', 'docs'];
const source = path.resolve(__dirname, '..');
const version = require(path.join(source, 'package.json')).version;

function fail(message) {
  throw new Error(message);
}

function readArgs() {
  if (process.argv.length === 2) return null;
  if (process.argv.length !== 4 || process.argv[2] !== '--skills-root') {
    fail('用法：cinematic-storyboard-install [--skills-root 绝对路径]');
  }
  if (!path.isAbsolute(process.argv[3])) fail('--skills-root 必须是绝对路径');
  return path.resolve(process.argv[3]);
}

function statIfPresent(file) {
  try { return fs.lstatSync(file); }
  catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

function hash(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function inventory(root, names) {
  const files = {};
  function visit(relative) {
    const base = path.basename(relative);
    if (base === '__pycache__' || base === '.DS_Store' || base.endsWith('.pyc')) return;
    const full = path.join(root, relative);
    const stat = fs.lstatSync(full);
    if (stat.isSymbolicLink()) fail(`不处理符号链接：${full}`);
    if (stat.isDirectory()) {
      for (const name of fs.readdirSync(full).sort()) visit(path.join(relative, name));
    } else if (stat.isFile()) {
      files[relative.split(path.sep).join('/')] = hash(full);
    } else {
      fail(`不支持的文件类型：${full}`);
    }
  }
  for (const name of names) visit(name);
  return files;
}

function existingInventory(root) {
  return inventory(root, fs.readdirSync(root).filter(name => name !== MARKER).sort());
}

function sameFiles(a, b) {
  const left = Object.keys(a).sort();
  const right = Object.keys(b).sort();
  return left.length === right.length && left.every((name, i) => name === right[i] && a[name] === b[name]);
}

function candidateRoots(override) {
  if (override) return [override];
  const home = os.homedir();
  return [...new Set([
    path.join(home, '.agents', 'skills'),
    path.join(process.env.CODEX_HOME || path.join(home, '.codex'), 'skills'),
    path.join(home, '.codex', 'skills')
  ])];
}

function ensureNoInterruptedUpdate(root) {
  if (!statIfPresent(root)) return;
  const leftovers = fs.readdirSync(root).filter(name =>
    name.startsWith(`.${NAME}-previous-`) || name.startsWith(`.${NAME}-stage-`));
  if (leftovers.length) fail(`发现未收口的安装事务：${leftovers.map(name => path.join(root, name)).join('、')}。请先核对并恢复或清理。`);
}

function chooseTarget(roots) {
  const existing = [];
  for (const root of roots) {
    ensureNoInterruptedUpdate(root);
    const target = path.join(root, NAME);
    const stat = statIfPresent(target);
    if (!stat) continue;
    if (!stat.isDirectory() || stat.isSymbolicLink()) fail(`同名入口不是普通目录：${target}`);
    existing.push(target);
  }
  if (existing.length > 1) {
    fail(`发现多个同名 Skill，未作任何修改：${existing.join('、')}`);
  }
  return existing[0] || path.join(roots[0], NAME);
}

function verifyExisting(target, expected) {
  const actual = existingInventory(target);
  const markerPath = path.join(target, MARKER);
  const markerStat = statIfPresent(markerPath);
  if (markerStat) {
    if (!markerStat.isFile() || markerStat.isSymbolicLink()) fail(`安装记录异常：${markerPath}`);
    let marker;
    try { marker = JSON.parse(fs.readFileSync(markerPath, 'utf8')); }
    catch { fail(`安装记录无法读取：${markerPath}`); }
    if (marker.schema !== 1 || marker.name !== NAME || !marker.files || typeof marker.files !== 'object') {
      fail(`安装记录无法核实：${markerPath}`);
    }
    if (!sameFiles(actual, marker.files)) fail(`现有 Skill 含本地修改，已保留原状：${target}`);
  } else if (!sameFiles(actual, expected)) {
    fail(`现有 Skill 没有安装记录，且与此发布包不同；无法区分旧版与本地修改，已保留原状：${target}`);
  }
}

function install() {
  const roots = candidateRoots(readArgs());
  const target = chooseTarget(roots);
  const expected = inventory(source, CONTENT);
  if (statIfPresent(target)) verifyExisting(target, expected);

  const root = path.dirname(target);
  fs.mkdirSync(root, { recursive: true });
  const stage = fs.mkdtempSync(path.join(root, `.${NAME}-stage-`));
  const previous = path.join(root, `.${NAME}-previous-${process.pid}-${Date.now()}`);
  let movedOld = false;
  let installed = false;
  try {
    for (const name of CONTENT) fs.cpSync(path.join(source, name), path.join(stage, name), { recursive: true, force: false });
    const copied = inventory(stage, CONTENT);
    if (!sameFiles(copied, expected)) fail('安装暂存内容与发布包不一致');
    fs.writeFileSync(path.join(stage, MARKER), JSON.stringify({
      schema: 1, name: NAME, version, files: copied
    }, null, 2) + '\n', { flag: 'wx' });
    if (statIfPresent(target)) {
      fs.renameSync(target, previous);
      movedOld = true;
    }
    fs.renameSync(stage, target);
    installed = true;
    if (movedOld) fs.rmSync(previous, { recursive: true, force: true });
  } catch (error) {
    if (movedOld && !installed) {
      try { fs.renameSync(previous, target); }
      catch (restoreError) {
        fail(`安装失败，且自动恢复未完成。请保留 ${previous}：${restoreError.message}；原错误：${error.message}`);
      }
    }
    throw error;
  } finally {
    if (!installed) fs.rmSync(stage, { recursive: true, force: true });
  }
  process.stdout.write(`已安装 ${NAME} ${version}：${target}\n请让 Codex 重新加载 Skill。\n`);
}

try { install(); }
catch (error) {
  process.stderr.write(`安装停止：${error.message}\n`);
  process.exitCode = 1;
}
