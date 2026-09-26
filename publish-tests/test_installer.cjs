'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

const source = path.resolve(__dirname, '..');
const installer = path.join(source, 'bin', 'install.cjs');
const content = ['SKILL.md', 'AGENTS.md', 'agents', 'assets', 'references', 'scripts', 'tests', 'README.md', 'docs', 'LICENSE'];

function run(root) {
  return spawnSync(process.execPath, [installer, '--skills-root', root], { encoding: 'utf8' });
}

function workspace(fn) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'cinematic-install-test-'));
  try { fn(directory); }
  finally { fs.rmSync(directory, { recursive: true, force: true }); }
}

test('fresh install, repeat install, and local edit protection', () => workspace(directory => {
  const root = path.join(directory, 'skills');
  const target = path.join(root, 'cine-ai-video-director');
  assert.equal(run(root).status, 0);
  assert.equal(run(root).status, 0);
  assert.match(fs.readFileSync(path.join(target, 'SKILL.md'), 'utf8'), /cine-ai-video-director/);
  assert.ok(fs.existsSync(path.join(target, 'docs', 'USAGE.md')));
  assert.ok(fs.existsSync(path.join(target, 'docs', 'diagram', 'workbench-map.svg')));
  assert.equal(fs.readdirSync(path.join(target, 'assets', 'visual-style-atlas', 'images')).length, 53);
  fs.appendFileSync(path.join(target, 'SKILL.md'), '\n本地修改\n');
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /本地修改/);
  assert.match(fs.readFileSync(path.join(target, 'SKILL.md'), 'utf8'), /本地修改/);
}));

test('identical legacy Skill is adopted; divergent legacy Skill is preserved', () => workspace(directory => {
  const root = path.join(directory, 'skills');
  const target = path.join(root, 'cine-ai-video-director');
  fs.mkdirSync(target, { recursive: true });
  for (const name of content) fs.cpSync(path.join(source, name), path.join(target, name), { recursive: true });
  assert.equal(run(root).status, 0);
  assert.ok(fs.existsSync(path.join(target, '.cine-ai-video-director-install.json')));

  fs.rmSync(path.join(target, '.cine-ai-video-director-install.json'));
  fs.appendFileSync(path.join(target, 'SKILL.md'), '\n旧版改动\n');
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /无法区分旧版与本地修改/);
  assert.match(fs.readFileSync(path.join(target, 'SKILL.md'), 'utf8'), /旧版改动/);
}));

test('two active locations stop without changing either', () => workspace(directory => {
  const agents = path.join(directory, '.agents', 'skills', 'cine-ai-video-director');
  const codex = path.join(directory, '.codex', 'skills', 'cine-ai-video-director');
  fs.mkdirSync(agents, { recursive: true });
  fs.mkdirSync(codex, { recursive: true });
  const result = spawnSync(process.execPath, [installer], {
    encoding: 'utf8', env: { ...process.env, HOME: directory, CODEX_HOME: path.join(directory, '.codex') }
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /多个新旧名称的 Skill/);
  assert.deepEqual(fs.readdirSync(agents), []);
  assert.deepEqual(fs.readdirSync(codex), []);
}));

function legacyInstall(root) {
  assert.equal(run(root).status, 0);
  const target = path.join(root, 'cine-ai-video-director');
  const old = path.join(root, 'cinematic-storyboard');
  fs.renameSync(target, old);
  const markerPath = path.join(old, '.cine-ai-video-director-install.json');
  const marker = JSON.parse(fs.readFileSync(markerPath, 'utf8'));
  marker.name = 'cinematic-storyboard';
  fs.writeFileSync(path.join(old, '.cinematic-storyboard-install.json'), JSON.stringify(marker));
  fs.unlinkSync(markerPath);
  return old;
}

test('managed legacy name migrates once and keeps project data outside the Skill', () => workspace(directory => {
  const root = path.join(directory, 'skills');
  const old = legacyInstall(root);
  const project = path.join(directory, 'project.json');
  fs.writeFileSync(project, '{"title":"My existing film"}');
  assert.equal(run(root).status, 0);
  assert.equal(fs.existsSync(old), false);
  const target = path.join(root, 'cine-ai-video-director');
  assert.ok(fs.existsSync(path.join(target, 'docs', 'USAGE.md')));
  const marker = JSON.parse(fs.readFileSync(path.join(target, '.cine-ai-video-director-install.json'), 'utf8'));
  assert.equal(marker.name, 'cine-ai-video-director');
  assert.equal(fs.readFileSync(project, 'utf8'), '{"title":"My existing film"}');
  assert.equal(run(root).status, 0);
}));

test('modified legacy installation is preserved under its original name', () => workspace(directory => {
  const root = path.join(directory, 'skills');
  const old = legacyInstall(root);
  fs.appendFileSync(path.join(old, 'SKILL.md'), '\nmy local requirements\n');
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /本地修改/);
  assert.match(fs.readFileSync(path.join(old, 'SKILL.md'), 'utf8'), /my local requirements/);
  assert.equal(fs.existsSync(path.join(root, 'cine-ai-video-director')), false);
}));

test('both names in the same root stop without deleting either', () => workspace(directory => {
  const root = path.join(directory, 'skills');
  const old = legacyInstall(root);
  const current = path.join(root, 'cine-ai-video-director');
  fs.mkdirSync(current);
  const result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /多个新旧名称/);
  assert.ok(fs.existsSync(old));
  assert.ok(fs.existsSync(current));
}));
