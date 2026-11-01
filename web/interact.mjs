import { chromium } from '/tmp/ui-verify/node_modules/playwright/index.mjs';
const URL = 'http://127.0.0.1:8787/';
const b = await chromium.launch({ args:['--no-sandbox'] });
const ctx = await b.newContext({ viewport:{width:1440,height:1000}, permissions:['clipboard-read','clipboard-write'] });
const p = await ctx.newPage();
const errs=[]; p.on('pageerror',e=>errs.push(String(e)));
await p.goto(URL,{waitUntil:'networkidle'});
const readClip = () => p.evaluate(()=>navigator.clipboard.readText());

// 1. 点第 5 行 -> 详情面板切换
await p.locator('.row').nth(4).click();
console.log('1) 点第5行后详情标题:', await p.locator('#detail .d-name').innerText());

// 2. 详情里「复制名字」
await p.locator('#detail .d-actions .btn').first().click();
await p.waitForTimeout(150);
console.log('2) 复制名字 ->', JSON.stringify(await readClip()));

// 3. 键盘 ↓ 选择
await p.locator('body').click({position:{x:700,y:300}});
await p.keyboard.press('ArrowDown'); await p.keyboard.press('ArrowDown');
console.log('3) 按两次 ↓ 后详情标题:', await p.locator('#detail .d-name').innerText());
await p.keyboard.press('Enter'); await p.waitForTimeout(120);
console.log('   回车复制 ->', JSON.stringify(await readClip()));

// 4. 搜索
await p.locator('#q').fill('kakao'); await p.waitForTimeout(120);
console.log('4) 搜索 kakao -> 结果数', await p.locator('.row').count(), '首个:', await p.locator('.row').first().innerText().then(t=>t.replace(/\n/g,' | ')));
await p.locator('#copyAllNames').click(); await p.waitForTimeout(120);
console.log('   复制全部名字 ->', JSON.stringify(await readClip()));
await p.locator('#q').fill(''); await p.waitForTimeout(120);

// 5. 作品区点画师名跳转
await p.locator('#worksBody .lk').first().click(); await p.waitForTimeout(400);
console.log('5) 作品区点画师 -> 详情标题:', await p.locator('#detail .d-name').innerText());

// 6. 评论区点标签跳转
await p.locator('.tg').nth(1).click(); await p.waitForTimeout(400);
console.log('6) 评论区点标签 -> 详情标题:', await p.locator('#detail .d-name').innerText());

// 7. 评论分类筛选 + 复制该条画师名
await p.locator('.fbtn').nth(1).click(); await p.waitForTimeout(150);
console.log('7) 切到「推荐作品（未点名）」条数:', await p.locator('.cm').count());
await p.locator('.fbtn').first().click(); await p.waitForTimeout(150);
await p.locator('.cm .cp').first().click(); await p.waitForTimeout(150);
console.log('   复制该条画师名 ->', JSON.stringify(await readClip()));

// 8. 深色模式
await p.emulateMedia({colorScheme:'dark'}); await p.waitForTimeout(250);
await p.locator('.row').nth(2).click();
await p.screenshot({path:'shots/r5-dark.png'});
console.log('8) 深色模式截图已存');

// 9. 移动端底部抽屉
const m = await ctx.newPage();
await m.setViewportSize({width:390,height:844});
await m.goto(URL,{waitUntil:'networkidle'});
await m.locator('.row').nth(3).click(); await m.waitForTimeout(500);
console.log('9) 移动端点行 -> 抽屉可见:', await m.locator('#sheet').evaluate(e=>getComputedStyle(e).transform));
await m.screenshot({path:'shots/r5-mobile-sheet.png'});
console.log('JS 错误:', errs.length? errs.join(' | ') : '无');
await b.close();
