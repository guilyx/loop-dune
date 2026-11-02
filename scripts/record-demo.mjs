// Records the dashboard demo video embedded in the docs site.
//
//   cd dashboard && npm run build && npm start          # any data source works
//   node scripts/record-demo.mjs [out.mp4]               # needs Playwright + ffmpeg
//
// Env: DEMO_URL (default http://localhost:3000). Output: docs/assets/demo.mp4 and a
// poster image next to it.
//
// The video is assembled from screenshots rather than screen-recorded, so text stays
// sharp and the timing is the same on every run. A caption bar and a cursor are drawn
// into the page; scrolls, clicks and slider moves are rendered frame by frame.
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = (process.env.DEMO_URL ?? "http://localhost:3000").replace(/\/$/, "");
const OUT = resolve(process.argv[2] ?? "docs/assets/demo.mp4");
const POSTER = join(dirname(OUT), "demo-poster.jpg");
const FPS = 25;
const STEP = 1 / FPS;

const work = mkdtempSync(join(tmpdir(), "loop-demo-"));
const frames = [];
let cursor = { x: 640, y: 420 };

async function frame(page, seconds = STEP) {
  const file = join(work, `f${String(frames.length).padStart(5, "0")}.png`);
  await page.screenshot({ path: file });
  frames.push({ file, seconds });
}

const hold = (page, seconds) => frame(page, seconds);
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

async function chrome(page) {
  await page.evaluate(({ x, y }) => {
    if (!document.getElementById("demo-style")) {
      const style = document.createElement("style");
      style.id = "demo-style";
      style.textContent = `
        #demo-caption{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:82%;
          padding:12px 22px;border-radius:12px;background:rgba(15,23,42,.9);color:#f8fafc;
          font:500 19px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
          box-shadow:0 10px 30px rgba(0,0,0,.28);z-index:2147483646;text-align:center}
        #demo-caption code{background:none;color:#bfdbfe;padding:0;font-size:.92em}
        #demo-caption:empty{display:none}
        #demo-caption b{color:#93c5fd;font-weight:650}
        #demo-cursor{position:fixed;left:0;top:0;width:24px;height:24px;z-index:2147483647;
          pointer-events:none;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))}
        #demo-ripple{position:fixed;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;
          border:3px solid rgba(59,130,246,.85);background:rgba(59,130,246,.15);
          z-index:2147483644;pointer-events:none;display:none}
        #demo-card{position:fixed;inset:0;z-index:2147483645;display:flex;flex-direction:column;
          align-items:center;justify-content:center;gap:16px;background:#0b1220;color:#f8fafc;
          font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;text-align:center}
        #demo-card h1{margin:0;font-size:54px;letter-spacing:-.02em}
        #demo-card p{margin:0;font-size:22px;color:#cbd5e1;max-width:900px;line-height:1.5}
        #demo-card code{font-size:19px;color:#93c5fd;background:none;border:0;padding:0}
        html{scroll-behavior:auto!important}`;
      document.head.appendChild(style);
    }
    if (!document.getElementById("demo-cursor")) {
      const caption = document.createElement("div");
      caption.id = "demo-caption";
      const ripple = document.createElement("div");
      ripple.id = "demo-ripple";
      const pointer = document.createElement("div");
      pointer.id = "demo-cursor";
      pointer.innerHTML =
        '<svg viewBox="0 0 24 24" width="24" height="24"><path d="M3 2l7.5 19 2.6-7.4L20.5 11z" ' +
        'fill="#0f172a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
      document.body.append(caption, ripple, pointer);
    }
    const p = document.getElementById("demo-cursor");
    p.style.transform = `translate(${x - 3}px, ${y - 2}px)`;
  }, cursor);
}

async function caption(page, html) {
  await page.evaluate((h) => {
    document.getElementById("demo-caption").innerHTML = h;
  }, html);
}

async function card(page, html) {
  await page.evaluate((h) => {
    let el = document.getElementById("demo-card");
    const pointer = document.getElementById("demo-cursor");
    if (pointer) pointer.style.display = h ? "none" : "";
    if (!h) return el?.remove();
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-card";
      document.body.appendChild(el);
    }
    el.innerHTML = h;
  }, html);
}

async function go(page, path) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  await chrome(page);
}

async function moveTo(page, target, seconds = 0.7) {
  let to = target;
  if (typeof target !== "object" || !("x" in target)) {
    const box = await target.boundingBox();
    if (!box) throw new Error("target not visible");
    to = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }
  const from = { ...cursor };
  const steps = Math.max(1, Math.round(seconds * FPS));
  for (let i = 1; i <= steps; i++) {
    const t = ease(i / steps);
    cursor = { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
    await page.mouse.move(cursor.x, cursor.y);
    await chrome(page);
    await frame(page);
  }
}

async function click(page, locator, { settle = 600 } = {}) {
  await locator.scrollIntoViewIfNeeded();
  await moveTo(page, locator);
  await page.evaluate(({ x, y }) => {
    const r = document.getElementById("demo-ripple");
    r.style.left = `${x}px`;
    r.style.top = `${y}px`;
    r.style.display = "block";
  }, cursor);
  await frame(page, 0.15);
  await page.evaluate(() => (document.getElementById("demo-ripple").style.display = "none"));
  await locator.click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(settle);
  await chrome(page);
}

async function scroll(page, dy, seconds = 1.2) {
  const steps = Math.max(1, Math.round(seconds * FPS));
  const start = await page.evaluate(() => window.scrollY);
  for (let i = 1; i <= steps; i++) {
    await page.evaluate((y) => window.scrollTo(0, y), start + dy * ease(i / steps));
    await frame(page);
  }
}

async function scrollTo(page, locator, offset = 90, seconds = 1.2) {
  const box = await locator.boundingBox();
  await scroll(page, box.y - offset, seconds);
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1.5, // 1920x1080 frames
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  // 1. Title
  await go(page, "/");
  await card(
    page,
    "<h1>Loop Dune</h1><p>On-chain analytics for Loop Protocol's lending markets: every pool and " +
      "CDP vault, read from contract state every hour since deployment.</p>",
  );
  await hold(page, 3.2);
  await card(page, null);

  // 2. Overview
  await caption(page, "<b>Overview</b> · TVL, borrows and utilization for all four markets");
  await hold(page, 3);
  await scroll(page, 520, 1.6);
  await caption(page, "Cross-market charts, all on one hourly UTC grid across Ethereum and BNB Chain");
  await hold(page, 3);
  await scroll(page, -520, 1);

  // 3. Market page
  await caption(page, "Open a market");
  await click(page, page.locator('a.market-card[href="/markets/eth"]'));
  await caption(page, "<b>lpETH</b> · five analysis tabs, one date-range filter");
  await hold(page, 2.6);
  await click(page, page.getByRole("button", { name: "1Y", exact: true }), { settle: 300 });
  await caption(page, "The date range scopes every chart and tab");
  await hold(page, 1.6);
  await scroll(page, 420, 1.4);
  await caption(page, "<b>Overview tab</b> · TVL, borrowed, utilization, rates, collateral vs debt, share price");
  await hold(page, 3);
  await scroll(page, -420, 0.8);

  // 4. Yield
  await click(page, page.getByRole("tab", { name: "Yield" }));
  await caption(page, "<b>Yield</b> · what lenders actually earned (from the share price) vs the quoted APR");
  await hold(page, 3.2);
  await scroll(page, 380, 1.2);
  await hold(page, 1.6);
  await scroll(page, -380, 0.8);

  // 5. Flows
  await click(page, page.getByRole("tab", { name: "Flows" }));
  await caption(page, "<b>Flows</b> · each day's TVL change split exactly into interest and net deposits");
  await hold(page, 3.2);
  await scroll(page, 380, 1.2);
  await hold(page, 1.4);
  await scroll(page, -380, 0.8);

  // 6. Risk: stress test
  await click(page, page.getByRole("tab", { name: "Risk" }));
  await caption(page, "<b>Risk</b> · stress test: shock every collateral price at once");
  const slider = page.locator("#shock");
  await scrollTo(page, slider, 200, 1);
  await moveTo(page, slider);
  await slider.focus();
  for (let pct = 0; pct < 60; pct += 2) {
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await frame(page, 0.06);
  }
  await caption(page, "Vaults past their liquidation ratio, debt at risk and uncovered debt update live");
  await hold(page, 3.2);
  const heatmap = page.locator("h3", { hasText: "Liquidation proximity" }).first();
  if (await heatmap.count()) {
    await scrollTo(page, heatmap, 120, 1.2);
    await caption(page, "Liquidation-proximity heatmap, debt concentration and oracle events");
    await hold(page, 3);
  }
  await page.evaluate(() => window.scrollTo(0, 0));

  // 7. Rate model
  await click(page, page.getByRole("tab", { name: "Rate model" }));
  await caption(page, "<b>Rate model</b> · utilization vs borrow APR for every day: the empirical rate curve");
  await hold(page, 3.4);
  await scroll(page, 300, 1);
  await hold(page, 1.6);
  await page.evaluate(() => window.scrollTo(0, 0));

  // 8. Dark theme
  const theme = page.locator("button.theme-toggle");
  await click(page, theme, { settle: 200 });
  if ((await page.evaluate(() => document.documentElement.dataset.theme)) !== "dark") {
    await click(page, theme, { settle: 200 });
  }
  await caption(page, "Light and dark themes, following the system setting by default");
  await hold(page, 2.4);
  await page.evaluate(() => {
    localStorage.removeItem("loop-theme");
    document.documentElement.removeAttribute("data-theme");
  });

  // 9. Data page and API
  await go(page, "/data");
  await caption(page, "<b>Data</b> · every Postgres view documented; the same data on Dune");
  await hold(page, 3);
  await scroll(page, 360, 1.2);
  await hold(page, 1.6);
  await caption(page, "Coverage and data health per chain: reverting calls are recorded, never zero-filled");
  await scroll(page, 360, 1.2);
  await hold(page, 2.6);

  // The CSV endpoint downloads in a browser, so show it the way it is used: from curl.
  await page.evaluate(async () => {
    const csv = await (await fetch("/api/markets/eth?format=csv")).text();
    const lines = csv.trim().split("\n");
    const cut = (l) => (l.length > 118 ? `${l.slice(0, 117)}…` : l);
    const shown = [lines[0], ...lines.slice(-9)].map(cut).join("\n");
    const term = document.createElement("div");
    term.id = "demo-card";
    term.style.background = "rgba(11,18,32,.96)";
    const pre = document.createElement("pre");
    pre.style.cssText =
      "margin:0;padding:22px 26px;border-radius:12px;background:#0f172a;color:#e2e8f0;" +
      "font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:92%;overflow:hidden;" +
      "box-shadow:0 20px 50px rgba(0,0,0,.45);text-align:left";
    pre.textContent = `$ curl -s https://<dashboard>/api/markets/eth?format=csv\n${shown}`;
    term.appendChild(pre);
    document.body.appendChild(term);
  });
  await caption(page, "<b>HTTP API</b> · <code>/api/markets</code>, <code>/api/markets/eth</code> as JSON or CSV");
  await hold(page, 3.4);
  await card(page, null);

  // 10. End card
  await go(page, "/");
  await card(
    page,
    "<h1>Loop Dune</h1><p>Indexer · Postgres views · public Dune tables · dashboard · API</p>" +
      "<p><code>guilyx.github.io/loop-dune</code> &nbsp;·&nbsp; <code>github.com/guilyx/loop-dune</code></p>",
  );
  await hold(page, 3.5);

  await browser.close();
  if (errors.length) console.warn("page errors:", errors);

  // Assemble: concat demuxer with per-frame durations (the last frame is listed twice,
  // as the format requires), then H.264 for universal playback.
  const list = frames.map((f) => `file '${f.file}'\nduration ${f.seconds.toFixed(3)}`).join("\n");
  writeFileSync(join(work, "frames.txt"), `${list}\nfile '${frames.at(-1).file}'\n`);
  execFileSync("ffmpeg", [
    "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", join(work, "frames.txt"),
    "-vf", `fps=${FPS},format=yuv420p`, "-c:v", "libx264", "-preset", "slow", "-crf", "24",
    "-tune", "stillimage", "-movflags", "+faststart", "-an", OUT,
  ]);
  // poster: the overview page right after the title card
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", frames[1].file, "-q:v", "3", POSTER]);
  const seconds = frames.reduce((s, f) => s + f.seconds, 0);
  console.log(`${OUT}: ${frames.length} frames, ${seconds.toFixed(1)}s`);
  rmSync(work, { recursive: true, force: true });
}

main().catch((e) => {
  console.error(e);
  rmSync(work, { recursive: true, force: true });
  process.exit(1);
});
