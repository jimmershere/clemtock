/**
 * capture-site-demo.mjs — record a scripted walkthrough of a website as video.
 *
 * An ad that says "go to our site and start a project" is far more persuasive showing
 * someone actually doing it. Playwright drives a real browser; we record the window and
 * draw our own cursor, because a real pointer is not captured in video frames.
 *
 *   node scripts/capture-site-demo.mjs --out out/ads/au2/site-demo.webm
 *
 * Flags: --url --out --width --height --slow (ms between actions)
 *
 * The cursor is a DOM element we move ourselves, kept in sync with Playwright's mouse.
 * Moving it in steps rather than jumping is what makes the recording read as a person
 * using the site instead of a script hitting selectors.
 */
import { chromium } from '/app/clemtock/node_modules/playwright-core/index.mjs';
import path from 'node:path';
import fs from 'node:fs';

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
};
const URL_    = arg('url', 'https://appearance-unlimited.com/');
const OUT     = path.resolve(arg('out', 'out/ads/au2/site-demo.webm'));
const WIDTH   = parseInt(arg('width', '810'), 10);
const HEIGHT  = parseInt(arg('height', '1440'), 10);
const SLOW    = parseInt(arg('slow', '450'), 10);
const EXEC    = process.env.CLEMTOCK_CHROMIUM;

const DIR = path.dirname(OUT);
fs.mkdirSync(DIR, { recursive: true });

const CURSOR_JS = `
  (() => {
    if (document.getElementById('__adcursor')) return;
    const c = document.createElement('div');
    c.id = '__adcursor';
    c.style.cssText = [
      'position:fixed','left:0','top:0','width:28px','height:28px','z-index:2147483647',
      'pointer-events:none','transition:transform 90ms linear','will-change:transform',
      "background:url(\\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><path d='M4 2 L4 22 L9.5 17 L13 25 L17 23 L13.5 15 L21 15 Z' fill='white' stroke='black' stroke-width='1.6' stroke-linejoin='round'/></svg>\\") no-repeat",
    ].join(';');
    document.documentElement.appendChild(c);
    window.__moveCursor = (x, y) => { c.style.transform = 'translate(' + x + 'px,' + y + 'px)'; };
    window.__clickPulse = () => {
      const r = document.createElement('div');
      const m = c.getBoundingClientRect();
      r.style.cssText = 'position:fixed;left:' + (m.left - 12) + 'px;top:' + (m.top - 12) + 'px;' +
        'width:52px;height:52px;border:3px solid #d81a24;border-radius:50%;z-index:2147483646;' +
        'pointer-events:none;opacity:.95;transition:all 380ms ease-out';
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.9)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 420);
    };
  })();
`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({
    executablePath: EXEC || undefined,
    args: ['--no-sandbox', '--hide-scrollbars', '--disable-gpu'],
  });
  const ctx = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 1,
    recordVideo: { dir: DIR, size: { width: WIDTH, height: HEIGHT } },
  });
  const page = await ctx.newPage();
  // Re-inject on every navigation: the cursor is a DOM node and does not survive one.
  await page.addInitScript(CURSOR_JS);

  let cur = { x: WIDTH / 2, y: HEIGHT * 0.35 };
  const move = async (x, y, steps = 22) => {
    for (let i = 1; i <= steps; i++) {
      const nx = cur.x + (x - cur.x) * (i / steps);
      const ny = cur.y + (y - cur.y) * (i / steps);
      await page.mouse.move(nx, ny);
      await page.evaluate(([a, b]) => window.__moveCursor && window.__moveCursor(a, b), [nx, ny]);
      await sleep(16);
    }
    cur = { x, y };
  };
  const clickAt = async (loc, label) => {
    await loc.scrollIntoViewIfNeeded();
    await sleep(260);
    const b = await loc.boundingBox();
    if (!b) throw new Error(`no bounding box for ${label}`);
    await move(b.x + b.width / 2, b.y + b.height / 2);
    await sleep(180);
    await page.evaluate(() => window.__clickPulse && window.__clickPulse());
    await sleep(150);
    await loc.click();
    console.log(`clicked: ${label}`);
    await sleep(SLOW);
  };

  await page.goto(URL_, { waitUntil: 'domcontentloaded' });
  await page.evaluate(CURSOR_JS);
  await sleep(700);

  // 1. Start Your Project — the hero CTA, not the nav one (bigger, reads better on video)
  // The hero button, not the nav link — .or() of two locators trips strict mode when
  // both exist, and the big red one reads far better on video.
  const cta = page.locator('a.btn-lg:has-text("Start Your Project")').first();
  await clickAt(cta, 'Start Your Project');
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate(CURSOR_JS);
  await sleep(600);

  // 2. the Resto-Mod Build card
  const card = page.locator('button.tc[data-type="restomod"]').first();
  await clickAt(card, 'Resto-Mod Build');

  // 3. type a name, slowly enough to read
  const name = page.locator('#f-name');
  await clickAt(name, 'Full name field');
  await name.type('Rodney Dangerfield', { delay: 105 });
  console.log('typed: Rodney Dangerfield');
  await sleep(1100);

  const video = page.video();
  await ctx.close();
  await browser.close();
  if (video) {
    const tmp = await video.path();
    fs.renameSync(tmp, OUT);
    console.log(`wrote ${OUT}`);
  }
})().catch((e) => { console.error('capture failed:', e.message); process.exit(1); });
