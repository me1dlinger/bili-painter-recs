import { chromium } from '/tmp/ui-verify/node_modules/playwright/index.mjs';

const url = process.argv[2] || 'http://127.0.0.1:8787/';
const out = process.argv[3] || '/vol1/1000/Data/codes/files/bili-painter-report/web/shots/shot.png';
const w = Number(process.argv[4] || 1440), h = Number(process.argv[5] || 960);
const full = process.argv[6] === 'full';

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
const errs = [];
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
page.on('pageerror', e => errs.push(String(e)));
await page.goto(url, { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
await page.screenshot({ path: out, fullPage: full });
console.log('screenshot ->', out);
if (errs.length) console.log('页面错误:', errs.join(' | '));
await browser.close();
