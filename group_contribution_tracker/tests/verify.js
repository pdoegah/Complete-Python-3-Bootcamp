const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const SRC = path.resolve(__dirname, '..', 'index.html');
const SCR = process.argv[2] || require('os').tmpdir(); fs.mkdirSync(SCR, { recursive: true });
// wrap like the Artifact tool does on first publish
const wrap = body => `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>${body}</body></html>`;
fs.writeFileSync(path.join(SCR, 'v1.html'), wrap(fs.readFileSync(SRC, 'utf8')));

const stub = (writer) => `
  window.__published = null;
  window.claude = { use: async (n) => {
    if (n === 'permissions') return { state: async () => ${writer ? '"granted"' : '"unavailable"'} };
    if (n === 'artifact') return ${writer ? '{ publish: async (html) => { window.__published = html; return {version:"v2"}; } }' : 'null'};
    if (n === 'downloads') return { save: async (r) => { window.__saved = r; return "saved"; } };
    return null;
  }};`;

(async () => {
  const browser = await chromium.launch();
  const fail = (m) => { console.error('FAIL: ' + m); process.exit(1); };

  // --- read-only member ---
  let ctx = await browser.newContext({ viewport: { width: 400, height: 800 } });
  let page = await ctx.newPage(); await page.addInitScript(stub(false));
  page.on('pageerror', e => fail('pageerror ' + e));
  await page.goto('file://' + path.join(SCR, 'v1.html'));
  await page.waitForTimeout(400);
  if (await page.isVisible('#manageBtn')) fail('manage button visible to read-only viewer');
  if ((await page.textContent('#total')).indexOf('800') < 0) fail('total wrong: ' + await page.textContent('#total'));
  if ((await page.textContent('#countMembers')).trim() !== '4') fail('members count');
  const w = await page.evaluate(() => document.documentElement.scrollWidth <= 400);
  if (!w) fail('horizontal overflow at phone width');
  await page.screenshot({ path: path.join(SCR, 'phone.png'), fullPage: true });
  await ctx.close();

  // --- manager ---
  ctx = await browser.newContext({ viewport: { width: 1000, height: 900 } });
  page = await ctx.newPage(); await page.addInitScript(stub(true));
  page.on('pageerror', e => fail('pageerror ' + e));
  await page.goto('file://' + path.join(SCR, 'v1.html'));
  await page.waitForSelector('#manageBtn:visible');
  await page.click('#manageBtn');
  await page.click('#clearExamples');
  await page.fill('#fName', 'Zainab Bello'); await page.fill('#fAmount', '75.5'); await page.fill('#fDate', '2026-09-15'); await page.fill('#fNote', 'Cash "at" meeting, hall');
  await page.click('#fSubmit');
  await page.fill('#sName', 'Old Boys Welfare Fund'); await page.fill('#sCurrency', 'ngn'); await page.fill('#sGoal', '1000'); await page.fill('#sManagers', 'Amina Yusuf, Kwame Mensah');
  await page.click('#settingsForm button[type=submit]');
  if (!(await page.isVisible('#draftBar'))) fail('draft bar hidden');
  if (!/3 unsaved/.test(await page.textContent('#draftText'))) fail('draft count: ' + await page.textContent('#draftText'));
  await page.click('#exportBtn');
  await page.waitForTimeout(100);
  const saved = await page.evaluate(() => window.__saved);
  if (!saved || !/Zainab Bello,75.50,NGN,"Cash ""at"" meeting, hall"/.test(saved.data)) fail('csv wrong: ' + JSON.stringify(saved));
  await page.click('#publishBtn');
  await page.waitForFunction(() => window.__published);
  const v2 = await page.evaluate(() => window.__published);
  if (!v2.startsWith('<!doctype html>')) fail('published page has no doctype');
  if (/data-armed|Hide manager tools/.test(v2.split('<script id="state"')[0])) fail('viewer state leaked into published page');
  fs.writeFileSync(path.join(SCR, 'v2.html'), v2);
  await ctx.close();

  // --- reload the published version as a read-only member ---
  ctx = await browser.newContext({ viewport: { width: 400, height: 800 } });
  page = await ctx.newPage(); await page.addInitScript(stub(false));
  page.on('pageerror', e => fail('pageerror v2 ' + e));
  await page.goto('file://' + path.join(SCR, 'v2.html'));
  await page.waitForTimeout(400);
  const st = await page.evaluate(() => JSON.parse(document.getElementById('state').textContent));
  if (st.contributions.length !== 1 || st.contributions[0].name !== 'Zainab Bello') fail('state not carried: ' + JSON.stringify(st));
  if (st.group.currency !== 'NGN' || st.group.goal !== 1000 || st.group.example) fail('settings not carried');
  if ((await page.textContent('#groupName')) !== 'Old Boys Welfare Fund') fail('group name');
  if (await page.isVisible('#exampleNotice')) fail('example notice still visible');
  if (!(await page.isVisible('#goalBox'))) fail('goal box hidden');
  if (!/Amina Yusuf, Kwame Mensah/.test(await page.textContent('#managers'))) fail('managers');
  if (await page.isVisible('#manageBtn')) fail('manage visible in v2 read-only');
  // v2 must rebuild itself identically (idempotent template)
  await ctx.close();
  ctx = await browser.newContext(); page = await ctx.newPage(); await page.addInitScript(stub(true));
  await page.goto('file://' + path.join(SCR, 'v2.html')); await page.waitForSelector('#manageBtn:visible');
  await page.click('#manageBtn'); await page.fill('#fName', 'Test Two'); await page.fill('#fAmount', '1'); await page.click('#fSubmit'); await page.click('#publishBtn');
  await page.waitForFunction(() => window.__published);
  const v3 = await page.evaluate(() => window.__published);
  const strip = h => h.replace(/<script id="state"[\s\S]*?<\/script>/, '').replace(/<b id="updated">[^<]*<\/b>/, '').replace(/id="(total|totalSub|countMembers|countEntries|goalLabel|goalPct)"[^>]*>[^<]*/g, '').replace(/<h1 id="groupName">[^<]*/,'').replace(/<b id="managers">[^<]*/,'').replace(/<p class="desc" id="groupDesc">[^<]*/,'');
  if (strip(v2) !== strip(v3)) { fs.writeFileSync(path.join(SCR,'v3.html'), v3); fail('template not stable between publishes (see v2/v3)'); }
  await browser.close();
  console.log('ALL CHECKS PASSED; published size', v2.length, 'bytes');
})().catch(e => { console.error(e); process.exit(1); });
