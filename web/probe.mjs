import { chromium } from '/tmp/ui-verify/node_modules/playwright/index.mjs';
const url = process.argv[2] || 'http://127.0.0.1:8787/';
const sizes = [[1440,1000,'desktop'],[1024,900,'laptop'],[390,844,'mobile'],[768,1024,'tablet']];
const browser = await chromium.launch({ args:['--no-sandbox'] });
for (const [w,h,name] of sizes){
  const page = await browser.newPage({ viewport:{width:w,height:h} });
  const errs=[]; page.on('pageerror',e=>errs.push(String(e)));
  await page.goto(url,{waitUntil:'networkidle'}); await page.waitForTimeout(300);
  const r = await page.evaluate(() => {
    const out = {};
    out.docScrollW = document.documentElement.scrollWidth;
    out.winW = window.innerWidth;
    out.overflowX = document.documentElement.scrollWidth > window.innerWidth + 1;
    const over = [];
    document.querySelectorAll('body *').forEach(el=>{
      const b = el.getBoundingClientRect();
      if (b.width>0 && (b.right > window.innerWidth + 1 || b.left < -1)) {
        over.push(el.tagName + '.' + (el.className||'').toString().slice(0,28) + ' right=' + Math.round(b.right));
      }
    });
    out.overflowing = over.slice(0,8);
    const header = document.querySelector('.topbar').getBoundingClientRect();
    out.headerH = Math.round(header.height);
    out.statsRowH = Math.round(document.querySelector('.stats').getBoundingClientRect().height);
    out.statsCount = document.querySelectorAll('.stat').length;
    const rows = document.querySelectorAll('.row');
    out.rowCount = rows.length;
    out.rowH = rows.length ? Math.round(rows[0].getBoundingClientRect().height) : 0;
    out.visibleRows = rows.length ? Math.round(document.querySelector('.scroller').clientHeight / (out.rowH||1)) : 0;
    out.scrollerH = document.querySelector('.scroller').clientHeight;
    out.detailVisible = window.getComputedStyle(document.querySelector('.detail')).display !== 'none';
    out.firstRowText = rows.length ? rows[0].innerText.replace(/\n/g,' | ') : '';
    return out;
  });
  console.log('==', name, w+'x'+h, '==');
  console.log('  横向溢出:', r.overflowX, r.overflowX? r.overflowing : '(无)');
  console.log('  顶栏高', r.headerH, '| 数字条高', r.statsRowH, '| 统计格', r.statsCount);
  console.log('  列表行高', r.rowH, '| 可见行数', r.visibleRows, '| 列表可视高', r.scrollerH, '| 右侧详情', r.detailVisible);
  console.log('  首行文本:', r.firstRowText.slice(0,90));
  if (errs.length) console.log('  JS 错误:', errs.join(' | '));
  await page.close();
}
await browser.close();
