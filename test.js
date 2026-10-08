// usage: node test.js <url> <prefix: local|live>
const { chromium } = require('playwright-core');
const URL_ = process.argv[2] || 'http://127.0.0.1:18935/';
const PRE = process.argv[3] || 'local';
let fails = 0; const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) fails++; };
const QUERIES = ['beans', 'milk', 'bread', 'eggs', 'bananas', 'coffee', 'Heinz beans 415g', 'semi-skimmed milk 4 pint', 'Warburtons toastie', 'cornflakes', 'xyzzy'];
(async () => {
  const b = await chromium.launch({executablePath: '/usr/bin/google-chrome', headless: true});
  for (const [w, h, name] of [[390, 844, 'mobile'], [1280, 900, 'desktop']]) {
    const ctx = await b.newContext({viewport: {width: w, height: h}, deviceScaleFactor: name === 'mobile' ? 2 : 1, isMobile: name === 'mobile', hasTouch: name === 'mobile', timezoneId: 'Europe/London', locale: 'en-GB'});
    const p = await ctx.newPage(); const errs = [], bad = [];
    p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); p.on('pageerror', e => errs.push(e.message));
    p.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().slice(0, 120)); });
    if (name === 'mobile') { const cdp = await ctx.newCDPSession(p); await cdp.send('Network.enable');
      await cdp.send('Network.emulateNetworkConditions', {offline: false, latency: 150, downloadThroughput: 9e6 / 8, uploadThroughput: 3e6 / 8});
      await cdp.send('Emulation.setCPUThrottlingRate', {rate: 4}); }
    const t0 = Date.now();
    await p.goto(URL_, {waitUntil: 'domcontentloaded'});
    await p.waitForFunction(() => /Prices checked|Couldn't/.test(document.getElementById('status').textContent), null, {timeout: 20000});
    const st = await p.textContent('#status');
    ok(/Prices checked/.test(st), `${name}: data loaded in ${Date.now() - t0} ms — ${st.replace(/\s+/g, ' ')}`);
    for (const q of QUERIES) {
      await p.fill('#q', q); await p.click('#go'); await p.waitForTimeout(300);
      const r = await p.evaluate(() => ({
        title: document.getElementById('listTitle').textContent,
        note: document.getElementById('listNote').textContent,
        rows: [...document.querySelectorAll('#items li')].slice(0, 4).map(li => li.innerText.replace(/\s+/g, ' ')),
        groups: document.querySelectorAll('#groups .grp').length,
        summary: document.getElementById('sumCard').hidden ? '' : document.querySelector('#summary .summary').innerText,
        links: document.querySelectorAll('#links a').length,
        firstLink: document.querySelector('#links a').href
      }));
      const expectHits = q !== 'xyzzy';
      ok((expectHits ? r.rows.length > 0 : r.rows.length === 0) && r.links === 10, `${name}: "${q}" -> ${r.title}; groups ${r.groups}; ${r.summary}\n      note: ${r.note}\n      ${r.rows.join('\n      ')}\n      link: ${r.firstLink}`);
      if (name === 'mobile' && q === 'beans') { await p.evaluate(() => window.scrollTo(0, 0)); await p.screenshot({path: PRE === 'live' ? 'shots/mobile-live.png' : `shots/${PRE}-mobile-beans.png`}); }
      if (name === 'mobile' && q === 'milk') await p.screenshot({path: `shots/${PRE}-mobile-milk-full.png`, fullPage: true});
      if (name === 'desktop' && q === 'Heinz beans 415g') await p.screenshot({path: `shots/${PRE}-desktop-heinz.png`, fullPage: true});
    }
    await p.click('.chip >> text=Eggs'); await p.waitForTimeout(200);
    ok(/[?&]q=Eggs/.test(p.url()) && (await p.$$('#items li')).length > 0, `${name}: staple chip Eggs works (${p.url()})`);
    if (name === 'mobile') { const sw = await p.evaluate(() => document.documentElement.scrollWidth); ok(sw <= 392, `mobile: no sideways scroll (${sw})`); }
    ok(errs.length === 0, `${name}: no console errors ${errs.join(' | ')}`);
    ok(bad.length === 0, `${name}: no failed requests ${bad.join(' | ')}`);
    await ctx.close();
  }
  await b.close(); console.log(fails ? `${fails} FAILED` : 'ALL PASSED'); process.exit(fails ? 1 : 0);
})();
