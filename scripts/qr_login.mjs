// 无头浏览器扫码登录 B站，成功后导出完整 cookie（含 buvid3/buvid4/b_nut/_uuid 等风控指纹）
import { chromium } from '/tmp/ui-verify/node_modules/playwright/index.mjs';
import fs from 'fs';

const OUT = '/vol1/1000/Data/codes/files/bili-painter-report/store/login';
fs.mkdirSync(OUT, { recursive: true });

const b = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await b.newContext({
  viewport: { width: 1100, height: 850 },
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  locale: 'zh-CN',
});
const p = await ctx.newPage();
const log = (...a) => console.log(new Date().toLocaleTimeString('zh-CN'), ...a);

for (let round = 1; round <= 12; round++) {
  try {
    await p.goto('https://passport.bilibili.com/login', { waitUntil: 'networkidle', timeout: 60000 });
  } catch (e) { log('打开登录页失败，重试', String(e.message).slice(0, 50)); }
  await p.waitForTimeout(3000);
  await p.mouse.move(20, 820);              // 挪开鼠标，避免提示气泡挡住二维码
  await p.waitForTimeout(600);

  const el = p.locator('.login-scan').first();
  try { await el.screenshot({ path: `${OUT}/qrcode.png` }); }
  catch { await p.screenshot({ path: `${OUT}/qrcode.png`, clip: { x: 545, y: 185, width: 275, height: 270 } }); }
  fs.writeFileSync(`${OUT}/qrcode-round.txt`, String(round));
  log(`第 ${round} 轮二维码已写入 store/login/qrcode.png`);

  for (let i = 0; i < 58; i++) {           // 每轮盯 174 秒
    await p.waitForTimeout(3000);
    const cookies = await ctx.cookies();
    const sess = cookies.find(c => c.name === 'SESSDATA' && c.value);
    if (sess) {
      const set = Object.fromEntries(cookies.map(c => [c.name, c.value]));
      fs.writeFileSync(`${OUT}/cookies.json`, JSON.stringify(set, null, 1));
      fs.writeFileSync(`${OUT}/cookies-full.json`, JSON.stringify(cookies, null, 1));
      fs.writeFileSync(`${OUT}/logged-in.txt`, new Date().toISOString());
      log('检测到登录成功，cookie 已导出（' + Object.keys(set).length + ' 项）');
      await p.waitForTimeout(2500);
      await p.screenshot({ path: `${OUT}/after-login.png` }).catch(() => {});
      await b.close();
      process.exit(0);
    }
    // 页面文案里出现"扫描成功/确认"就提示一下
    const txt = await p.locator('.login-scan').first().innerText().catch(() => '');
    if (/扫描成功|请在手机|确认/.test(txt) && i % 4 === 0) log('  检测到：' + txt.replace(/\s+/g, ' ').slice(0, 40));
    if (/已失效|过期|刷新/.test(txt)) break;   // 码失效，换新一轮
  }
  log(`第 ${round} 轮二维码超时，自动刷新`);
}
log('多轮都未检测到登录，退出');
await b.close();
