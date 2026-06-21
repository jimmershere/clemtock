/* render-headless.mjs — Phase 4 server-side export.
 *
 * Drives clemtock-renderer.dc.html in headless chromium at native 1080x1920, seeks every
 * frame, screenshots the stage, and pipes PNGs into ffmpeg to write an MP4 to disk.
 *
 *   node web/render-headless.mjs --script web/ad-script.json --out out/clemtock-ad.mp4
 *
 * Uses system chromium via playwright-core (no browser download) and system ffmpeg.
 * Override discovery with CLEMTOCK_PLAYWRIGHT / CLEMTOCK_CHROMIUM / CLEMTOCK_FFMPEG.
 */
import { createRequire } from 'module';
import { spawn } from 'child_process';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';

const require = createRequire(import.meta.url);
const __dir = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dir, '..');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const ALPHA = process.argv.includes('--alpha');  // render graphics layer with transparency
const SCRIPT = path.resolve(arg('script', path.join(REPO, 'web/ad-script.json')));
const OUT = path.resolve(arg('out', path.join(REPO, ALPHA ? 'out/overlay.mov' : 'out/clemtock-ad.mp4')));
const ROOT = path.resolve(arg('root', path.join(REPO, 'web')));   // static + asset root
const FPS = parseInt(arg('fps', '30'), 10);
const W = 1080, H = 1920;

function findChromium() {
  if (process.env.CLEMTOCK_CHROMIUM) return process.env.CLEMTOCK_CHROMIUM;
  for (const c of ['/usr/bin/chromium', '/snap/bin/chromium',
                   '/usr/bin/chromium-browser', '/usr/bin/google-chrome']) {
    if (fs.existsSync(c)) return c;
  }
  return '/usr/bin/chromium';
}
const CHROMIUM = findChromium();
const FFMPEG = process.env.CLEMTOCK_FFMPEG ||
  (fs.existsSync(process.env.HOME + '/bin/ffmpeg') ? process.env.HOME + '/bin/ffmpeg' : 'ffmpeg');

function loadPlaywright() {
  const cands = [
    process.env.CLEMTOCK_PLAYWRIGHT,
    path.join(REPO, 'node_modules/playwright-core'),
    path.join(REPO, 'node_modules/playwright'),
    // control host (laptop)
    '/home/jimmer/.npm-global/lib/node_modules/n8n/node_modules/playwright-core',
    '/home/jimmer/.npm-global/lib/node_modules/openclaw/node_modules/playwright-core',
    // floor2
    '/usr/local/lib/node_modules/n8n/node_modules/playwright-core',
    '/home/floor2/.npm-global/lib/node_modules/openclaw/node_modules/playwright-core',
  ].filter(Boolean);
  for (const c of cands) {
    try { return require(c); } catch (e) { /* try next */ }
  }
  throw new Error('playwright-core not found; set CLEMTOCK_PLAYWRIGHT to its path');
}

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.svg': 'image/svg+xml' };

function staticServer(rootDir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const rel = decodeURIComponent(req.url.split('?')[0]);
      const fp = path.join(rootDir, path.normalize(rel));
      if (!fp.startsWith(rootDir)) { res.writeHead(403); return res.end(); }
      fs.readFile(fp, (err, buf) => {
        if (err) { res.writeHead(404); return res.end('not found'); }
        res.writeHead(200, { 'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream' });
        res.end(buf);
      });
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

async function main() {
  if (!fs.existsSync(SCRIPT)) throw new Error('ad-script not found: ' + SCRIPT);
  const doc = JSON.parse(fs.readFileSync(SCRIPT, 'utf8'));
  const DUR = doc.duration || 15;
  const N = Math.round(FPS * DUR);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });

  const { chromium } = loadPlaywright();
  const srv = await staticServer(ROOT);
  const port = srv.address().port;
  const url = `http://127.0.0.1:${port}/clemtock-renderer.dc.html`;

  const ffArgs = ALPHA
    ? ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
       '-c:v', 'qtrle', '-pix_fmt', 'argb', OUT]                       // lossless + alpha
    : ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-crf', '18',
       '-movflags', '+faststart', OUT];
  const ff = spawn(FFMPEG, ffArgs, { stdio: ['pipe', 'inherit', 'inherit'] });

  const browser = await chromium.launch({ executablePath: CHROMIUM, headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--force-color-profile=srgb'] });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });

  // inject the exact ad-script (+ alpha flag) so the renderer skips its fetch
  await page.addInitScript((cfg) => {
    window.__CLEMTOCK_SCRIPT__ = cfg.doc;
    if (cfg.alpha) window.__CLEMTOCK_ALPHA__ = true;
  }, { doc, alpha: ALPHA });
  await page.goto(url, { waitUntil: 'load' });
  let css = '#ct-controls{display:none!important}';
  if (ALPHA) css += ' html,body,#ct-root,[data-screen-label]{background:transparent!important}';
  await page.addStyleTag({ content: css });

  // wait for stage, fonts, and images
  await page.waitForSelector('[data-screen-label]', { timeout: 15000 });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
    const imgs = Array.from(document.images);
    await Promise.all(imgs.map(im => im.complete ? 0 : new Promise(r => { im.onload = im.onerror = r; })));
  });

  const stage = await page.$('[data-screen-label]');
  process.stderr.write(`clemtock render: ${N} frames @ ${FPS}fps (${DUR}s) -> ${OUT}\n`);
  for (let i = 0; i < N; i++) {
    const t = i / FPS;
    await page.evaluate((tt) => {
      const r = document.querySelector('input[type=range]');
      r.value = String(tt);
      r.dispatchEvent(new Event('input', { bubbles: true }));
    }, t);
    // let React commit, then settle two animation frames
    await page.evaluate(() => new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res))));
    const buf = await stage.screenshot({ type: 'png', omitBackground: ALPHA });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 30 === 0) process.stderr.write(`  frame ${i + 1}/${N} (${Math.round(i / N * 100)}%)\n`);
  }
  ff.stdin.end();
  await browser.close();
  srv.close();
  await new Promise((res, rej) => ff.on('close', (code) => code === 0 ? res() : rej(new Error('ffmpeg exit ' + code))));
  const mb = (fs.statSync(OUT).size / 1048576).toFixed(1);
  process.stdout.write(`clemtock render: wrote ${path.relative(REPO, OUT)} (${mb} MB)\n`);
}

main().catch((e) => { console.error('render-headless:', e.message || e); process.exit(1); });
