import { createWriteStream } from 'node:fs';
import { mkdir, readFile, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from 'node:stream/promises';
import { spawn } from 'node:child_process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const nodeModules = join(root, 'node_modules');
const packageJson = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const installed = new Set();

await mkdir(nodeModules, { recursive: true });

for (const [name, range] of Object.entries(packageJson.dependencies || {})) {
  await installPackage(name, range);
}

async function installPackage(name, range) {
  if (installed.has(name)) return;
  installed.add(name);

  const metadata = await fetchJson(`https://registry.npmjs.org/${encodeURIComponentPackage(name)}`);
  const version = resolveVersion(metadata, range);
  const manifest = metadata.versions[version];
  if (!manifest) throw new Error(`Cannot resolve ${name}@${range}`);

  const packageDir = join(nodeModules, name);
  await mkdir(dirname(packageDir), { recursive: true });
  await rm(packageDir, { recursive: true, force: true });

  const tarball = manifest.dist.tarball;
  const tempFile = join(root, `.tmp-${name.replaceAll('/', '-')}-${version}.tgz`);
  await download(tarball, tempFile);
  await extract(tempFile, packageDir);
  await rm(tempFile, { force: true });

  const deps = { ...(manifest.dependencies || {}), ...(manifest.optionalDependencies || {}) };
  for (const [depName, depRange] of Object.entries(deps)) {
    await installPackage(depName, depRange);
  }
}

function encodeURIComponentPackage(name) {
  return name.startsWith('@') ? `@${encodeURIComponent(name.slice(1))}` : encodeURIComponent(name);
}

function resolveVersion(metadata, range) {
  if (!range || range === 'latest') return metadata['dist-tags'].latest;
  const clean = range.replace(/^[~^]/, '');
  if (metadata.versions[clean]) return clean;
  const major = clean.match(/^(\d+)/)?.[1];
  const candidates = Object.keys(metadata.versions).filter((version) => !version.includes('-'));
  if (range.startsWith('^') && major) {
    return candidates.reverse().find((version) => version.startsWith(`${major}.`)) || metadata['dist-tags'].latest;
  }
  return metadata['dist-tags'].latest;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return response.json();
}

async function download(url, file) {
  const response = await fetch(url);
  if (!response.ok || !response.body) throw new Error(`Failed to download ${url}`);
  await pipeline(response.body, createWriteStream(file));
}

async function extract(tarball, targetDir) {
  await mkdir(targetDir, { recursive: true });
  await new Promise((resolve, reject) => {
    const tar = spawn('tar', ['-xzf', tarball, '-C', targetDir, '--strip-components', '1']);
    tar.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`tar exited ${code}`))));
    tar.on('error', reject);
  });
}
