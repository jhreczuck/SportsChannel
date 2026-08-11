"use strict";

// ---------------------------
// Layout & Style (ported from src/main.py)
// ---------------------------
const WIDTH = 960, HEIGHT = 720;
const HEADER_H = 64;
const TICKER_H = 56;
const PANEL_MARGIN = 20;
const TEXT_PADDING = 14;
const FIRST_LINE_INDENT = 28;
const SEPARATOR_THICKNESS = 12;
const SEPARATOR_ALPHA = 128 / 255;

const LOGO_BOX = { w: 200, h: 200 };

const BG = "rgb(5,5,10)";
const PANEL_BG = "rgb(50,50,50)";
const INNER_FILL = "rgb(50,50,50)";
const TEXT_COLOR = "rgb(235,220,190)";
const TICKER_BG = "rgb(10,10,16)";
const TICKER_TEXT_COLOR = "rgb(245,230,200)";
const HEADER_SEPARATOR_COLOR = `rgba(255,0,0,${SEPARATOR_ALPHA})`;
const TICKER_SEPARATOR_COLOR = `rgba(25,25,112,${SEPARATOR_ALPHA})`;

const LINE_DELAY = 0.2;       // seconds between each revealed line
const SLIDE_DURATION = 18.0;  // seconds per story slide
const BOARD_DURATION = 12.0;  // seconds per probables/standings board screen

const PROBABLES_GAMES_PER_SCREEN = 5; // full-width rows, no reserved logo column
const BOARD_ROW_BG = "rgba(25,25,112,0.55)"; // navy row highlight, matches ticker separator color

const TICKER_SCROLL_PX_PER_SEC = 240; // == 4px/frame @ 60fps in the pygame version
const TICKER_SCROLL_ON_SECONDS = 10.0;
const TICKER_SCROLL_PAUSE_SECONDS = 3.0;

const BODY_FONT_PX = 32;
const HEADER_FONT_PX = 26;
const SMALL_FONT_PX = 18;
const TICKER_FONT_PX = 32;

const BODY_FONT = `${BODY_FONT_PX}px PxPlusIBMVGA8, monospace`;
const HEADER_FONT = `bold ${HEADER_FONT_PX}px Consolas, monospace`;
const SMALL_FONT = `${SMALL_FONT_PX}px PxPlusIBMVGA8, monospace`;
const TICKER_FONT = `${TICKER_FONT_PX}px PxPlusIBMVGA8, monospace`;

// ---------------------------
// Canvas setup
// ---------------------------
const canvas = document.getElementById("screen");
const ctx = canvas.getContext("2d");

// ---------------------------
// Layout rects (mirrors the rect math in main.py's main())
// ---------------------------
const contentTop = HEADER_H + SEPARATOR_THICKNESS;
const contentBottom = HEIGHT - TICKER_H;
const contentLeft = PANEL_MARGIN;
const contentRight = WIDTH - PANEL_MARGIN;
const contentWidth = contentRight - contentLeft;
const contentRect = { x: contentLeft, y: contentTop, w: contentWidth, h: contentBottom - contentTop };

const margin = TEXT_PADDING;
const inner = {
  x: contentRect.x + margin,
  y: contentRect.y + margin,
  w: contentRect.w - margin * 2,
  h: contentRect.h - margin * 2,
};
inner.right = inner.x + inner.w;
inner.bottom = inner.y + inner.h;

const rightRect = { x: inner.right - LOGO_BOX.w, y: inner.y, w: LOGO_BOX.w, h: LOGO_BOX.h };

const gap = 12;
const textMaxRight = rightRect.x - gap;
const leftWidth = Math.max(80, textMaxRight - inner.x);
const leftRect = { x: inner.x, y: inner.y, w: leftWidth, h: inner.h };

// ---------------------------
// Data loading
// ---------------------------
async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

function loadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

const logoCache = new Map();
async function getLogo(fileName) {
  if (!fileName) return null;
  if (logoCache.has(fileName)) return logoCache.get(fileName);
  const img = await loadImage(`../media/logos/${fileName}`);
  logoCache.set(fileName, img);
  return img;
}

// ---------------------------
// Text wrapping
// ---------------------------
// Lines that fall beside the logo (rightRect) use the narrower leftRect
// width; once a line is below the logo's bottom edge, it widens to use the
// full inner content width, since nothing occupies that space anymore.
function wrapTextAroundOverlay(bodyText, ctxRef, hasLogo) {
  const lines = [];
  ctxRef.font = BODY_FONT;

  const narrowWidth = Math.max(40, leftRect.w - TEXT_PADDING * 2);
  const wideWidth = Math.max(40, inner.w - TEXT_PADDING * 2);
  const lineHeight = BODY_FONT_PX + 4;

  // Which rendered line indices fall within the logo's vertical span.
  const logoStartLine = hasLogo ? Math.floor(Math.max(0, rightRect.y - inner.y) / lineHeight) : Infinity;
  const logoLineCount = hasLogo ? Math.ceil(rightRect.h / lineHeight) : 0;
  const logoEndLine = logoStartLine + logoLineCount;

  for (const para of bodyText.split("\n")) {
    if (!para.trim()) {
      lines.push("");
      continue;
    }

    const hasIndent = para.startsWith("<<<INDENT>>>");
    const text = para.replace("<<<INDENT>>>", "").trim();
    if (!text) continue;

    const words = text.split(/\s+/);
    let firstLine = true;

    while (words.length) {
      const lineIdx = lines.length;
      const fullWidth = (lineIdx >= logoStartLine && lineIdx < logoEndLine) ? narrowWidth : wideWidth;
      const availableWidth = (firstLine && hasIndent) ? fullWidth - FIRST_LINE_INDENT : fullWidth;

      const line = [];
      while (words.length) {
        const test = [...line, words[0]].join(" ");
        if (ctxRef.measureText(test).width <= availableWidth) {
          line.push(words.shift());
        } else {
          if (line.length === 0) line.push(words.shift()); // force overlong word
          break;
        }
      }

      const result = line.join(" ");
      if (firstLine && hasIndent) {
        lines.push("<<<INDENT>>>" + result);
        firstLine = false;
      } else {
        lines.push(result);
      }
    }
  }

  return lines;
}

// ---------------------------
// Probables / standings board builders
// ---------------------------
// Paginate one league's games into screens of PROBABLES_GAMES_PER_SCREEN,
// tagging each with its page number so drawProbablesBoard can show "(1/2)".
function buildProbablesPages(probablesData) {
  const pages = [];
  if (!probablesData || !probablesData.in_season) return pages;

  for (const league of probablesData.leagues || []) {
    const games = league.games || [];
    if (!games.length) continue;
    const totalPages = Math.ceil(games.length / PROBABLES_GAMES_PER_SCREEN);
    for (let p = 0; p < totalPages; p++) {
      pages.push({
        type: "probables",
        league: league.name,
        dateLabel: probablesData.date_label || "Today's",
        games: games.slice(p * PROBABLES_GAMES_PER_SCREEN, (p + 1) * PROBABLES_GAMES_PER_SCREEN),
        page: p + 1,
        totalPages,
      });
    }
  }
  return pages;
}

// One screen per division, in the order ESPN returns them (AL East, AL
// Central, AL West, NL East, NL Central, NL West).
function buildStandingsPages(standingsData) {
  if (!standingsData || !standingsData.in_season) return [];
  return (standingsData.divisions || [])
    .filter((d) => d.teams && d.teams.length)
    .map((d) => ({ type: "standings", division: d }));
}

// ---------------------------
// Drawing helpers
// ---------------------------
function drawHeader(headerLogo) {
  ctx.fillStyle = BG;
  ctx.fillRect(PANEL_MARGIN, 0, contentWidth, HEADER_H);

  ctx.fillStyle = HEADER_SEPARATOR_COLOR;
  ctx.fillRect(PANEL_MARGIN, HEADER_H, contentWidth, SEPARATOR_THICKNESS);

  let labelX = PANEL_MARGIN + TEXT_PADDING;
  if (headerLogo) {
    const maxH = HEADER_H - 12; // keep it inside the header bar, no clipping
    const scale = maxH / headerLogo.height;
    const w = headerLogo.width * scale;
    const h = headerLogo.height * scale;
    const y = HEADER_H / 2 - h / 2;
    ctx.drawImage(headerLogo, PANEL_MARGIN + 6, y, w, h);
    labelX = PANEL_MARGIN + 6 + w + 8;
  }

  ctx.font = HEADER_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.fillText("SportsChannel", labelX, HEADER_H / 2);

  const clockText = new Date()
    .toLocaleString("en-US", { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: true })
    .toUpperCase();
  ctx.font = SMALL_FONT;
  ctx.textAlign = "right";
  ctx.fillText(clockText, PANEL_MARGIN + contentWidth - TEXT_PADDING, HEADER_H / 2);
  ctx.textAlign = "left";
}

function drawTicker(tickerText, tickerWidth, tickerX) {
  ctx.fillStyle = TICKER_BG;
  ctx.fillRect(PANEL_MARGIN, HEIGHT - TICKER_H, contentWidth, TICKER_H);

  ctx.fillStyle = TICKER_SEPARATOR_COLOR;
  ctx.fillRect(PANEL_MARGIN, HEIGHT - TICKER_H, contentWidth, SEPARATOR_THICKNESS);

  ctx.save();
  ctx.beginPath();
  ctx.rect(PANEL_MARGIN, HEIGHT - TICKER_H, contentWidth, TICKER_H);
  ctx.clip();

  ctx.font = TICKER_FONT;
  ctx.fillStyle = TICKER_TEXT_COLOR;
  ctx.textBaseline = "middle";
  const y = HEIGHT - TICKER_H / 2;
  ctx.fillText(tickerText, tickerX, y);
  ctx.fillText(tickerText, tickerX + tickerWidth, y);

  ctx.restore();
}

function drawSlideText(wrappedLines, linesToShow, logo) {
  let lineY = inner.y + TEXT_PADDING;
  const maxY = inner.bottom - TEXT_PADDING;
  const lineHeight = BODY_FONT_PX + 4;

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";

  for (let i = 0; i < linesToShow && i < wrappedLines.length; i++) {
    if (lineY > maxY) break;
    const line = wrappedLines[i];
    if (!line.trim()) {
      lineY += lineHeight;
      continue;
    }
    let text = line, xPos = inner.x + TEXT_PADDING;
    if (line.startsWith("<<<INDENT>>>")) {
      text = line.replace("<<<INDENT>>>", "");
      xPos = inner.x + TEXT_PADDING + FIRST_LINE_INDENT;
    }
    ctx.fillText(text, xPos, lineY);
    lineY += lineHeight;
  }

  if (logo) drawLogoInBox(logo, rightRect);
}

// Scales an image to fit `box` (preserving aspect ratio) and centers it.
function drawLogoInBox(logo, box) {
  const scale = Math.min(box.w / logo.width, box.h / logo.height);
  const w = logo.width * scale;
  const h = logo.height * scale;
  const x = box.x + (box.w - w) / 2;
  const y = box.y + (box.h - h) / 2;
  ctx.drawImage(logo, x, y, w, h);
}

// ---------------------------
// Probables board
// ---------------------------
function drawProbablesBoard(page, mlbLogo) {
  const titleY = inner.y + TEXT_PADDING;
  const rowHeight = BODY_FONT_PX + 4;
  const rowBlockHeight = rowHeight * 2 + 18; // two lines per game + gap

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  let title = `${page.dateLabel} ${page.league} Games`;
  if (page.totalPages > 1) title += ` (${page.page}/${page.totalPages})`;
  ctx.fillText(title, inner.x + TEXT_PADDING, titleY);

  // Small MLB logo beside the title, out of the way of the full-width rows below.
  if (mlbLogo) {
    const badgeSize = 56;
    drawLogoInBox(mlbLogo, { x: inner.right - TEXT_PADDING - badgeSize, y: titleY - 8, w: badgeSize, h: badgeSize });
  }

  ctx.font = BODY_FONT;
  let rowY = titleY + BODY_FONT_PX + 24;
  const rowX = inner.x + TEXT_PADDING;
  const rowW = inner.w - TEXT_PADDING * 2; // full panel width -- no logo column reserved here

  for (const game of page.games) {
    ctx.fillStyle = BOARD_ROW_BG;
    ctx.fillRect(rowX - 8, rowY - 4, rowW, rowBlockHeight - 10);

    ctx.fillStyle = TEXT_COLOR;
    ctx.fillText(`${game.away}  (${game.away_pitcher})`, rowX, rowY);
    ctx.fillText(`at ${game.home}  (${game.home_pitcher})`, rowX, rowY + rowHeight);

    rowY += rowBlockHeight;
  }
}

// ---------------------------
// Standings board
// ---------------------------
function drawStandingsBoard(page, mlbLogo) {
  const division = page.division;
  const titleY = inner.y + TEXT_PADDING;

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  ctx.fillText(division.name, inner.x + TEXT_PADDING, titleY);

  ctx.font = BODY_FONT;
  const rowHeight = BODY_FONT_PX + 12;
  let rowY = titleY + BODY_FONT_PX + 30;
  const nameX = inner.x + TEXT_PADDING;
  const colW = Math.max(100, leftRect.w - TEXT_PADDING * 2);
  const colWX = nameX + colW * 0.50;
  const colLX = nameX + colW * 0.62;
  const colPctX = nameX + colW * 0.74;
  const colGbX = nameX + colW * 0.90;

  // Column headers
  ctx.fillStyle = "rgb(200,180,120)";
  ctx.fillText("W", colWX, rowY);
  ctx.fillText("L", colLX, rowY);
  ctx.fillText("PCT", colPctX, rowY);
  ctx.fillText("GB", colGbX, rowY);
  rowY += rowHeight;

  ctx.fillStyle = TEXT_COLOR;
  for (const team of division.teams) {
    ctx.fillStyle = BOARD_ROW_BG;
    ctx.fillRect(nameX - 8, rowY - 4, colW, rowHeight - 6);
    ctx.fillStyle = TEXT_COLOR;
    ctx.fillText(team.name, nameX, rowY);
    ctx.fillText(team.w, colWX, rowY);
    ctx.fillText(team.l, colLX, rowY);
    ctx.fillText(team.pct, colPctX, rowY);
    ctx.fillText(team.gb || "--", colGbX, rowY);
    rowY += rowHeight;
  }

  if (mlbLogo) drawLogoInBox(mlbLogo, rightRect);
}

// ---------------------------
// Music
// ---------------------------
const audioEl = new Audio();
audioEl.volume = 0.18;
let musicQueue = [];
let musicIndex = 0;

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function playCurrentTrack() {
  if (!musicQueue.length) return;
  const track = musicQueue[musicIndex];
  audioEl.src = `../media/music/${encodeURIComponent(track)}`;
  audioEl.play().catch((e) => console.warn("[music] play blocked:", e.message));
}

audioEl.addEventListener("ended", () => {
  musicIndex += 1;
  if (musicIndex >= musicQueue.length) {
    musicQueue = shuffle(musicQueue);
    musicIndex = 0;
  }
  playCurrentTrack();
});

async function setupMusic() {
  try {
    const manifest = await loadJSON("music_manifest.json");
    musicQueue = shuffle(manifest.files || []);
    musicIndex = 0;
  } catch (e) {
    console.warn("[music] manifest load failed:", e);
  }
}

// ---------------------------
// Main
// ---------------------------
async function main() {
  await Promise.all([
    document.fonts.load(BODY_FONT),
    document.fonts.load(HEADER_FONT),
    document.fonts.load(SMALL_FONT),
    document.fonts.load(TICKER_FONT),
  ]);

  let storySlides = [{ title: "", body: "Loading stories...", logo: null }];
  try {
    const storyData = await loadJSON("../data/stories_cleaned.json");
    if (storyData.slides && storyData.slides.length) storySlides = storyData.slides;
  } catch (e) {
    console.warn("[stories] load failed:", e);
    storySlides = [{ title: "", body: `Failed to load stories_cleaned.json: ${e.message}`, logo: null }];
  }

  let probablesPages = [];
  try {
    probablesPages = buildProbablesPages(await loadJSON("../data/probables.json"));
  } catch (e) {
    console.warn("[probables] load failed:", e);
  }

  let standingsPages = [];
  try {
    standingsPages = buildStandingsPages(await loadJSON("../data/standings.json"));
  } catch (e) {
    console.warn("[standings] load failed:", e);
  }

  // Rotation order: NFL stories -> AL/NL probables -> MLB stories -> 6 division
  // standings boards -> loop. Probables/standings are simply absent if it's
  // the off-season (both builders return [] then).
  const nflSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "nfl")
    .map((s) => ({ type: "story", slide: s }));
  const mlbSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "mlb")
    .map((s) => ({ type: "story", slide: s }));
  const otherSlides = storySlides.filter((s) => !["nfl", "mlb"].includes((s.league || "").toLowerCase()))
    .map((s) => ({ type: "story", slide: s }));

  const items = [...nflSlides, ...otherSlides, ...probablesPages, ...mlbSlides, ...standingsPages];
  if (!items.length) items.push({ type: "story", slide: { title: "", body: "No content available.", logo: null } });

  let tickerText = "SPORTS PLUS NETWORK • AUTOMATED SPORTS NEWS FEED •";
  try {
    const tickerData = await loadJSON("../data/ticker.json");
    if (tickerData.items && tickerData.items.length) {
      tickerText = tickerData.items.join("   |   ");
    }
  } catch (e) {
    console.warn("[ticker] load failed:", e);
  }
  ctx.font = TICKER_FONT;
  const tickerWidth = ctx.measureText(tickerText).width;

  const headerLogo = await loadImage("../media/logos/sportschannel.png");
  const mlbLogo = await getLogo("mlb.png");

  await setupMusic();
  playCurrentTrack();

  let currentIndex = 0;
  let slideStartTime = performance.now() / 1000;
  let wrappedLines = [];
  let currentLogo = null;

  async function prepareItem(idx) {
    const item = items[idx];
    if (item.type !== "story") return; // boards need no async prep
    const slide = item.slide;
    let body = slide.body || "";
    body = body.replace(/\\r\\n/g, "\n").replace(/\\n/g, "\n");
    const logoName = slide.logo || slide.logo_recommended;
    currentLogo = await getLogo(logoName);
    wrappedLines = wrapTextAroundOverlay(body, ctx, !!currentLogo);
  }

  await prepareItem(currentIndex);

  // Left/Right arrow keys manually step through the rotation, overriding the
  // auto-advance timer (which restarts fresh from whichever item you land on).
  function goToItem(newIndex) {
    currentIndex = ((newIndex % items.length) + items.length) % items.length;
    slideStartTime = performance.now() / 1000;
    prepareItem(currentIndex);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") goToItem(currentIndex + 1);
    else if (e.key === "ArrowLeft") goToItem(currentIndex - 1);
  });

  let tickerX = PANEL_MARGIN + contentWidth;
  let tickerCycleStart = performance.now() / 1000;
  let lastFrameTime = performance.now() / 1000;

  function frame() {
    const now = performance.now() / 1000;
    const dt = now - lastFrameTime;
    lastFrameTime = now;
    const elapsed = now - slideStartTime;
    const item = items[currentIndex];
    const duration = item.type === "story" ? SLIDE_DURATION : BOARD_DURATION;

    if (elapsed >= duration) {
      currentIndex = (currentIndex + 1) % items.length;
      slideStartTime = now;
      prepareItem(currentIndex); // async; frame keeps going with previous content until it resolves
    }

    const cycleElapsed = now - tickerCycleStart;
    if (cycleElapsed <= TICKER_SCROLL_ON_SECONDS) {
      tickerX -= TICKER_SCROLL_PX_PER_SEC * dt;
      if (tickerX <= PANEL_MARGIN - tickerWidth) {
        tickerX = PANEL_MARGIN + contentWidth;
      }
    } else if (cycleElapsed <= TICKER_SCROLL_ON_SECONDS + TICKER_SCROLL_PAUSE_SECONDS) {
      // paused
    } else {
      tickerCycleStart = now;
    }

    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    drawHeader(headerLogo);

    ctx.fillStyle = PANEL_BG;
    ctx.fillRect(contentRect.x, contentRect.y, contentRect.w, contentRect.h);
    ctx.fillStyle = INNER_FILL;
    ctx.fillRect(inner.x, inner.y, inner.w, inner.h);

    if (item.type === "story") {
      const linesToShow = Math.min(wrappedLines.length, Math.floor(elapsed / LINE_DELAY));
      drawSlideText(wrappedLines, linesToShow, currentLogo);
    } else if (item.type === "probables") {
      drawProbablesBoard(item, mlbLogo);
    } else if (item.type === "standings") {
      drawStandingsBoard(item, mlbLogo);
    }

    drawTicker(tickerText, tickerWidth, tickerX);

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}

// Browsers block autoplaying audio until a user gesture. We attempt playback
// immediately on load (playCurrentTrack, called from main()); if that's
// blocked, silently retry on the very first interaction anywhere on the
// page -- no visible prompt.
document.addEventListener("pointerdown", () => playCurrentTrack(), { once: true });
document.addEventListener("keydown", () => playCurrentTrack(), { once: true });

main().catch((e) => {
  console.error("[main] fatal error:", e);
  ctx.fillStyle = "#300";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.fillStyle = "#fff";
  ctx.font = "16px monospace";
  ctx.fillText(`Fatal error: ${e.message}`, 20, 40);
});
