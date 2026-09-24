import { cp, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const appRoot = process.cwd();
const standaloneApp = resolve(appRoot, '.next/standalone/apps/web');
const standaloneNext = resolve(standaloneApp, '.next');

await mkdir(standaloneNext, { recursive: true });
await cp(resolve(appRoot, 'public'), resolve(standaloneApp, 'public'), {
  recursive: true,
  force: true,
});
await cp(resolve(appRoot, '.next/static'), resolve(standaloneNext, 'static'), {
  recursive: true,
  force: true,
});

console.log('Prepared public and static assets for the standalone E2E server.');
