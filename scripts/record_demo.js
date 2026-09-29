// Records the dashboard walkthrough video with Playwright.
//   python -m airindex.devserver &      (or uvicorn airindex.api:app --port 8000)
//   node scripts/record_demo.js          -> dist/video/*.webm
// Needs: npm i playwright
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.AIRINDEX_URL || "http://localhost:8000";
const OUT = path.join(__dirname, "..", "dist", "video");
const FONT_DIR = process.env.FONT_DIR || "";      // optional local font substitutes
const W = 1440, H = 900;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const OVERLAY = `
(() => {
  if (document.getElementById('__cap')) return;
  const st = document.createElement('style');
  st.textContent = \`
  #__cap{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;max-width:980px;
    background:rgba(10,16,26,.92);color:#f3f6fa;font:500 19px/1.4 "IBM Plex Sans",system-ui,sans-serif;
    padding:13px 22px 14px;border-radius:10px;border-left:4px solid #f4b43c;box-shadow:0 10px 40px rgba(0,0,0,.35);
    transition:opacity .35s;opacity:0}
  #__cap b{color:#f4b43c;font-weight:600;margin-right:8px;font-family:"IBM Plex Mono",monospace;font-size:14px;letter-spacing:.06em}
  #__cur{position:fixed;z-index:100000;width:22px;height:22px;pointer-events:none;left:0;top:0;
    transform:translate(-3px,-2px);transition:left .05s linear, top .05s linear}
  #__cur svg{filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
  .__click{position:fixed;z-index:99998;width:34px;height:34px;border-radius:50%;border:3px solid #f4b43c;
    pointer-events:none;transform:translate(-50%,-50%) scale(.3);opacity:1;animation:__ck .5s ease-out forwards}
  @keyframes __ck{to{transform:translate(-50%,-50%) scale(1.3);opacity:0}}\`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id='__cap'; document.body.appendChild(c);
  const cur = document.createElement('div'); cur.id='__cur';
  cur.innerHTML='<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2 L3 18 L7.5 13.8 L10.5 20 L13 19 L10.2 12.8 L16 12.6 Z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  document.body.appendChild(cur);
  addEventListener('mousemove', e => { cur.style.left=e.clientX+'px'; cur.style.top=e.clientY+'px'; }, true);
  addEventListener('mousedown', e => { const k=document.createElement('div'); k.className='__click';
    k.style.left=e.clientX+'px'; k.style.top=e.clientY+'px'; document.body.appendChild(k); setTimeout(()=>k.remove(),600); }, true);
  window.__caption = (tag, text) => { c.innerHTML = tag ? '<b>'+tag+'</b>'+text : text; c.style.opacity = text ? 1 : 0; };
})();`;

function card(title, sub, lines) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%;background:#0c1520;color:#f3f6fa;font-family:"IBM Plex Sans",system-ui,sans-serif}
  .c{height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 120px;border-bottom:6px solid #f4b43c;box-sizing:border-box}
  .e{font:600 16px "IBM Plex Mono",monospace;letter-spacing:.14em;color:#f4b43c;text-transform:uppercase}
  h1{font:800 84px/1.02 "Archivo",system-ui,sans-serif;margin:18px 0 14px;letter-spacing:-.01em} h1 span{color:#f4b43c}
  p{font-size:26px;color:#aab6c8;margin:0;max-width:1000px;line-height:1.4}
  ul{list-style:none;padding:0;margin:34px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:10px 40px;max-width:1100px}
  li{font:500 20px "IBM Plex Mono",monospace;color:#d5dde8} li::before{content:"▸ ";color:#f4b43c}
  </style></head><body><div class="c"><div class="e">${sub}</div><h1>${title}</h1>${lines}</div></body></html>`;
}

async function smoothScrollTo(page, selector, offset = 90, ms = 900) {
  await page.evaluate(async ({ selector, offset, ms }) => {
    const el = document.querySelector(selector);
    const target = el ? el.getBoundingClientRect().top + scrollY - offset : 0;
    const start = scrollY, t0 = performance.now();
    await new Promise((res) => {
      const step = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        scrollTo(0, start + (target - start) * e); k < 1 ? requestAnimationFrame(step) : res(); };
      requestAnimationFrame(step);
    });
  }, { selector, offset, ms });
}
async function moveTo(page, selector, dx = 0.5, dy = 0.5, steps = 25) {
  const b = await page.locator(selector).first().boundingBox();
  await page.mouse.move(b.x + b.width * dx, b.y + b.height * dy, { steps });
  return b;
}
async function clickOn(page, selector) {
  await moveTo(page, selector);
  await wait(250);
  await page.locator(selector).first().click();
}
const cap = (page, tag, text) => page.evaluate(([a, b]) => window.__caption(a, b), [tag, text]);

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } }, colorScheme: "light" });

  if (FONT_DIR) {            // offline recording: map Google Fonts to local files
    await ctx.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", body: fs.readFileSync(path.join(FONT_DIR, "fonts.css"), "utf8") }));
    await ctx.route(/\/__fonts\//, (r) => r.fulfill({ body: fs.readFileSync(path.join(FONT_DIR, path.basename(new URL(r.request().url()).pathname))) }));
  }
  const fontCss = FONT_DIR ? `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=x">` : `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@800&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500&display=swap">`;

  const page = await ctx.newPage();
  const T0 = Date.now();
  const mark = (s) => console.log(((Date.now() - T0) / 1000).toFixed(1).padStart(6), s);

  // 1. Title card
  await page.goto(`${BASE}/api/cpi-feed`);           // same origin so font routes apply
  await page.setContent(card("Air<span>Index</span> India",
    "Smart India Hackathon 2026 · PS 26056 · Team ERROR502",
    `<p>A real-time airfare price index for India, built by scraping airline and travel-portal fares, ready to feed the Consumer Price Index.</p>`).replace("<style>", fontCss + "<style>"));
  await wait(5200); mark("title");

  // 2. Dashboard
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.evaluate(OVERLAY);
  await page.mouse.move(700, 400);
  await wait(400);
  await cap(page, "LIVE BOARD", "The header reads like a departures board: headline index, this month's CPI value, fares captured, clean pass rate and the dynamic-pricing spread.");
  await moveTo(page, ".flap:nth-child(1)", .5, .5, 30); await wait(1500);
  await moveTo(page, ".flap:nth-child(2)", .5, .5, 20); await wait(1200);
  await moveTo(page, ".flap:nth-child(5)", .5, .5, 30); await wait(1800); mark("board");

  // 3. Headline chart
  await smoothScrollTo(page, "#sec-headline", 20);
  await cap(page, "INDEX", "Headline index, April 2026 = 100. Hover any day: summer peak, monsoon lull and the 1 Aug fuel-surcharge step all show up.");
  const hb = await moveTo(page, "#headChart svg", 0.03, 0.55, 20);
  for (let i = 0; i <= 60; i++) { await page.mouse.move(hb.x + hb.width * (0.03 + 0.95 * i / 60), hb.y + hb.height * 0.55); await wait(95); }
  await wait(600);
  await clickOn(page, "#r90"); await wait(1500);
  await clickOn(page, "#rAll"); await wait(1100); mark("headline");

  // 4. Routes + booking curve
  await smoothScrollTo(page, "#sec-routes", 20);
  await cap(page, "ROUTES", "Ten pilot routes with traffic weights. Click a route and its booking-window curve updates.");
  await wait(900);
  await clickOn(page, '#routeRows tr[data-route="BLR-MAA"]'); await wait(2000);
  await clickOn(page, '#routeRows tr[data-route="DEL-BLR"]'); await wait(1500);
  await cap(page, "DYNAMIC PRICING", "Fares bought one day out cost about 2.2× the 60-day fare. Each window is indexed separately, so the comparison stays like-for-like.");
  await moveTo(page, "#curveChart svg", 0.14, 0.6, 20); await wait(1200);
  await moveTo(page, "#curveChart svg", 0.88, 0.5, 30); await wait(2600); mark("routes");

  // 5. CPI feed + window index
  await smoothScrollTo(page, "#sec-cpi", 20);
  await cap(page, "CPI FEED", "Monthly airfare sub-index for the Transport & Communication group, in the format MoSPI would ingest.");
  await moveTo(page, "#feedRows tr:nth-child(4)", .4, .5, 25); await wait(1400);
  await clickOn(page, "#copyFeed"); await wait(2600);
  await cap(page, "LIKE-FOR-LIKE", "Index by booking window: last-minute fares are up, planned bookings are flat. A shift in buying habits cannot fake inflation.");
  await moveTo(page, "#windowRows tr:nth-child(1)", .5, .5, 30); await wait(3400); mark("cpi");

  // 6. Run a live cycle
  await smoothScrollTo(page, "body", 0, 800);
  await cap(page, "LIVE CYCLE", "Run a scrape cycle: 6 portals × 10 routes × 5 booking windows, cleaned and indexed in a few seconds.");
  await wait(700);
  await clickOn(page, "#runCycle");
  await page.waitForSelector("#toast:not([hidden])", { timeout: 60000 });
  await cap(page, "", "");                               // make room for the result toast
  await moveTo(page, "#flaps", .3, .5, 30);
  await wait(3600);
  await cap(page, "LIVE CYCLE", "A new day of fares is in: the board, charts and CPI feed were all recomputed from the fresh data.");
  await wait(2600); mark("cycle");

  // 7. Pipeline
  await smoothScrollTo(page, "#sec-pipeline", 20, 1100);
  await cap(page, "PIPELINE", "Scraper health per portal: blocked pages are retried with a rotated browser profile. The cleaning log shows what was repaired or removed.");
  await moveTo(page, "#health .hbar:nth-child(6)", .5, .5, 30); await wait(2200);
  await moveTo(page, "#cleanLog .hbar:nth-child(1)", .5, .5, 30); await wait(1600);
  await moveTo(page, "#cleanLog .hbar:nth-child(5)", .5, .5, 20); await wait(2200); mark("pipeline");

  // 8. Latest observations
  await smoothScrollTo(page, "#sec-fares", 20);
  await cap(page, "RAW EVIDENCE", "Every fare behind the index is traceable: portal, airline, flight and total fare incl. taxes. Tags mark rebuilt taxes.");
  await wait(1500);
  await moveTo(page, "#fareWindow", .5, .5, 25);
  await page.selectOption("#fareWindow", "60"); await wait(2200);
  await page.selectOption("#fareWindow", "1"); await wait(1500); mark("fares");

  // 9. API
  await smoothScrollTo(page, "#sec-api", 20);
  await cap(page, "OPEN API", "Everything on screen is available over a REST API for MoSPI, RBI and researchers.");
  await moveTo(page, "#sec-api li:nth-child(1)", .3, .5, 25); await wait(2400);
  await page.goto(BASE + "/api/cpi-feed");
  await page.evaluate(OVERLAY);
  await page.evaluate(() => { document.body.style.cssText = "font:16px/1.5 'IBM Plex Mono',monospace;padding:30px 40px;background:#fff;color:#152030"; });
  await cap(page, "GET /api/cpi-feed", "The monthly series with base period and method metadata.");
  await wait(4200); mark("api");

  // 10. End card
  await page.setContent(card("Air<span>Index</span> India",
    "Team ERROR502 · SIH 2026 · PS 26056",
    `<ul><li>Scrapy + Playwright scraper fleet</li><li>Self-healing selectors, polite rate limits</li>
     <li>Cleaning + robust outlier filter</li><li>Jevons index, route & window weights</li>
     <li>Monthly CPI feed for MoSPI</li><li>FastAPI + live dashboard</li></ul>`).replace("<style>", fontCss + "<style>"));
  await wait(5000); mark("end");

  await ctx.close();
  await browser.close();
  console.log("video saved in", OUT);
})();
