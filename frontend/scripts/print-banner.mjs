import { readFileSync } from 'node:fs';

const bannerUrl = new URL('../banner.txt', import.meta.url);
process.stdout.write(`${readFileSync(bannerUrl, 'utf8').trimEnd()}\n`);
