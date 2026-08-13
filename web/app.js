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
const TITLECARD_DURATION = 6.0; // seconds the title card shows at the start of each loop
const TRIVIA_DURATION = 16.0;   // seconds the trivia card shows total
const TRIVIA_REVEAL_DELAY = 7.0; // seconds before the answer appears
const REFRESH_CARD_DURATION = 2.5; // seconds the blank end-of-lap refresh card shows

const PROBABLES_GAMES_PER_SCREEN = 5; // full-width rows, no reserved logo column
const BOARD_ROW_BG = "rgba(25,25,112,0.55)"; // navy row highlight, matches ticker separator color

const TICKER_SCROLL_PX_PER_SEC = 240; // == 4px/frame @ 60fps in the pygame version
const TICKER_SCROLL_ON_SECONDS = 10.0;
const TICKER_SCROLL_PAUSE_SECONDS = 3.0;

const BODY_FONT_PX = 36;
const HEADER_FONT_PX = 32;
const SMALL_FONT_PX = 22;
const TICKER_FONT_PX = 32;
const BOARD_TITLE_FONT_PX = 44; // board titles like "LATEST LINE" -- same pixel font, bigger

const BODY_FONT = `${BODY_FONT_PX}px PxPlusIBMVGA8, monospace`;
const HEADER_FONT = `bold ${HEADER_FONT_PX}px Consolas, monospace`;
const SMALL_FONT = `${SMALL_FONT_PX}px PxPlusIBMVGA8, monospace`;
const TICKER_FONT = `${TICKER_FONT_PX}px PxPlusIBMVGA8, monospace`;
const BOARD_TITLE_FONT = `${BOARD_TITLE_FONT_PX}px PxPlusIBMVGA8, monospace`;

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

// Simple greedy word-wrap to a fixed width -- no logo-zone awareness, for
// boards with their own custom layout (e.g. drawHistoryBoard's left column).
function wrapTextToWidth(text, maxWidth, ctxRef) {
  ctxRef.font = BODY_FONT;
  const lines = [];
  const words = text.split(/\s+/);
  let line = [];
  while (words.length) {
    const test = [...line, words[0]].join(" ");
    if (ctxRef.measureText(test).width <= maxWidth) {
      line.push(words.shift());
    } else {
      if (line.length === 0) line.push(words.shift());
      else {
        lines.push(line.join(" "));
        line = [];
      }
    }
  }
  if (line.length) lines.push(line.join(" "));
  return lines;
}

// ---------------------------
// Text wrapping
// ---------------------------
// Lines that fall beside the logo (rightRect) use the narrower leftRect
// width; once a line is below the logo's bottom edge, it widens to use the
// full inner content width, since nothing occupies that space anymore.
//
// Paragraph indentation is derived purely from real "\n" boundaries in the
// source text (paragraph breaks) -- every paragraph's first rendered line is
// indented, no special marker needed. GPT previously had to hand-encode this
// with a literal "<<<INDENT>>>" token, which occasionally leaked into the
// displayed text verbatim when GPT's output didn't come back exactly as
// instructed (a real, observed failure, not just a theoretical risk).
// Returns an array of {text, indent} objects rather than plain strings.
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
    const text = para.trim();
    if (!text) {
      lines.push({ text: "", indent: false });
      continue;
    }

    const words = text.split(/\s+/);
    let firstLine = true;

    while (words.length) {
      const lineIdx = lines.length;
      const fullWidth = (lineIdx >= logoStartLine && lineIdx < logoEndLine) ? narrowWidth : wideWidth;
      const availableWidth = firstLine ? fullWidth - FIRST_LINE_INDENT : fullWidth;

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

      lines.push({ text: line.join(" "), indent: firstLine });
      firstLine = false;
    }
  }

  return lines;
}

// ---------------------------
// On This Day (sports history fact) builder
// ---------------------------
function buildHistoryPage(historyData) {
  if (!historyData || !historyData.fact) return [];
  return [{ type: "history_fact", dateLabel: historyData.date_label || "", fact: historyData.fact }];
}

// ---------------------------
// Today's Sports Birthdays builder
// ---------------------------
function buildBirthdaysPage(birthdaysData) {
  if (!birthdaysData || !birthdaysData.people || !birthdaysData.people.length) return [];
  return [{ type: "birthdays", dateLabel: birthdaysData.date_label || "", people: birthdaysData.people }];
}

// ---------------------------
// Sports Trivia builder
// ---------------------------
function buildTriviaPage(triviaData) {
  if (!triviaData || !triviaData.trivia) return [];
  return [{ type: "trivia", trivia: triviaData.trivia }];
}

// ---------------------------
// League Quote builder
// ---------------------------
function buildQuotePage(quotesData, league) {
  const quote = quotesData && quotesData.quotes && quotesData.quotes[league];
  if (!quote) return [];
  return [{ type: "quote", league, quote: quote.quote, author: quote.author }];
}

// ---------------------------
// Section Intro builder ("FOOTBALL / COMING UP: ...")
// ---------------------------
const SECTION_INTRO_MAX_HEADLINES = 4;

// Pulls headlines straight from that league's own story slides -- no
// separate data source needed, and it's a live preview of what's actually
// coming up in this pass through the rotation.
function buildSectionIntroPage(sportName, leagueStoryItems) {
  const titles = [];
  const seen = new Set();
  for (const item of leagueStoryItems) {
    const title = (item.slide && item.slide.title || "").trim();
    if (!title || seen.has(title)) continue;
    seen.add(title);
    titles.push(title);
    if (titles.length >= SECTION_INTRO_MAX_HEADLINES) break;
  }
  if (!titles.length) return [];
  return [{ type: "section_intro", sportName, headlines: titles }];
}

// ---------------------------
// Headlines board builder
// ---------------------------
const HEADLINES_MAX_PAGES = 2;
const HEADLINES_MAX_PER_PAGE = 7;

// Fits as many headlines as actually fit vertically (up to
// HEADLINES_MAX_PER_PAGE), across at most HEADLINES_MAX_PAGES screens --
// remaining headlines beyond that are simply not shown, rather than
// paginating through the full list.
function buildHeadlinesPages(headlinesData, ctxRef) {
  const items = (headlinesData && headlinesData.headlines) || [];
  if (!items.length) return [];

  ctxRef.font = BODY_FONT;
  const titleY = inner.y + TEXT_PADDING;
  const boxY = titleY + BODY_FONT_PX + 20;
  const boxW = inner.w - TEXT_PADDING * 2;
  const boxH = inner.bottom - TEXT_PADDING - boxY;
  const textMaxWidth = boxW - 28;
  const lineHeight = BODY_FONT_PX + 4;

  const pages = [];
  let idx = 0;
  for (let p = 0; p < HEADLINES_MAX_PAGES && idx < items.length; p++) {
    const pageHeadlines = [];
    let usedHeight = 14; // matches drawHeadlinesBoard's top inset inside the box
    while (idx < items.length && pageHeadlines.length < HEADLINES_MAX_PER_PAGE) {
      const lines = wrapHeadline(items[idx].title, "..", "  ", textMaxWidth, ctxRef);
      const entryHeight = lines.length * lineHeight + 10;
      if (pageHeadlines.length > 0 && usedHeight + entryHeight > boxH) break;
      pageHeadlines.push(items[idx]);
      usedHeight += entryHeight;
      idx++;
    }
    if (!pageHeadlines.length) break;
    pages.push({ type: "headlines", headlines: pageHeadlines, page: p + 1 });
  }

  for (const page of pages) page.totalPages = pages.length;
  return pages;
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

// One screen per division, in the order ESPN returns them (e.g. AL East, AL
// Central, AL West, NL East, NL Central, NL West for MLB; AFC/NFC x
// East/North/South/West for NFL).
function buildStandingsPages(standingsData) {
  if (!standingsData || !standingsData.in_season) return [];
  const sport = standingsData.sport || "mlb";
  return (standingsData.divisions || [])
    .filter((d) => d.teams && d.teams.length)
    .map((d) => ({ type: "standings", division: d, sport }));
}

// ---------------------------
// Latest Line board builder (NFL betting lines)
// ---------------------------
const LATEST_LINE_GAMES_PER_SCREEN = 4; // 5 overflowed past the panel with the taller title/logo layout

function buildLatestLinePages(latestLineData, sport = "nfl") {
  const pages = [];
  for (const day of (latestLineData && latestLineData.days) || []) {
    const games = day.games || [];
    if (!games.length) continue;
    const totalPages = Math.ceil(games.length / LATEST_LINE_GAMES_PER_SCREEN);
    for (let p = 0; p < totalPages; p++) {
      pages.push({
        type: "latest_line",
        sport,
        day: day.day,
        games: games.slice(p * LATEST_LINE_GAMES_PER_SCREEN, (p + 1) * LATEST_LINE_GAMES_PER_SCREEN),
        page: p + 1,
        totalPages,
      });
    }
  }
  return pages;
}

// ---------------------------
// Score Results builder ("Monday's NFL Result(s)")
// ---------------------------
const SCORE_RESULTS_GAMES_PER_SCREEN = 4;
// MLB games get an extra pitcher-decision line each (see drawScoreResultsBoard),
// so fewer fit per screen than NFL's plain score rows.
const SCORE_RESULTS_GAMES_PER_SCREEN_MLB = 3;

function buildScoreResultsPages(scoreResultsData, league) {
  const result = scoreResultsData && scoreResultsData.results && scoreResultsData.results[league];
  if (!result || !result.games || !result.games.length) return [];
  const games = result.games;
  const perScreen = league === "mlb" ? SCORE_RESULTS_GAMES_PER_SCREEN_MLB : SCORE_RESULTS_GAMES_PER_SCREEN;
  const totalPages = Math.ceil(games.length / perScreen);
  const pages = [];
  for (let p = 0; p < totalPages; p++) {
    pages.push({
      type: "score_results",
      league,
      dayLabel: result.day_label,
      games: games.slice(p * perScreen, (p + 1) * perScreen),
      page: p + 1,
      totalPages,
    });
  }
  return pages;
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

// Shared line-by-line reveal: every board type uses this so the "typewriter"
// pacing is consistent throughout the app, not just on story slides.
// Returns a `write(text, x, y)` function -- draws (using whatever ctx.font/
// fillStyle is currently set) only if this is one of the first `linesToShow`
// calls made against it; returns whether it actually drew, so callers can
// gate a line's associated background (e.g. a table row highlight) on the
// same reveal step.
function makeWriter(linesToShow) {
  let i = 0;
  return function write(text, x, y) {
    const shouldDraw = i < linesToShow;
    i += 1;
    if (shouldDraw) ctx.fillText(text, x, y);
    return shouldDraw;
  };
}

// Same reveal counter as makeWriter, but for a "line" that's actually
// several draw calls (e.g. a table row's Name/W/L/PCT columns) -- caller
// checks shouldShow() once per row and draws all of that row's columns
// itself if it returns true, so the whole row reveals as a single step.
function makeLineGate(linesToShow) {
  let i = 0;
  return function shouldShow() {
    const result = i < linesToShow;
    i += 1;
    return result;
  };
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
    if (!line.text.trim()) {
      lineY += lineHeight;
      continue;
    }
    const xPos = inner.x + TEXT_PADDING + (line.indent ? FIRST_LINE_INDENT : 0);
    ctx.fillText(line.text, xPos, lineY);
    lineY += lineHeight;
  }

  if (logo) drawLogoInBox(logo, rightRect);
}

// Retro pixelation: downscale a logo to a tiny offscreen canvas, then it
// gets drawn back up with smoothing off, producing genuine blocky pixels
// (not just a blur) -- matches the CRT/pixel-font look everywhere else.
// Cached per source image since the downscale target doesn't depend on
// final display size, and this is way cheaper to do once than per frame.
const PIXELATE_RESOLUTION = 80; // "logical pixels" along the longer edge -- higher = less blocky
const pixelateCache = new WeakMap(); // Image -> Map<resolution, canvas>

function getPixelatedLogo(logo, resolution = PIXELATE_RESOLUTION) {
  let byResolution = pixelateCache.get(logo);
  if (!byResolution) {
    byResolution = new Map();
    pixelateCache.set(logo, byResolution);
  }
  if (byResolution.has(resolution)) return byResolution.get(resolution);

  const scale = resolution / Math.max(logo.width, logo.height);
  const w = Math.max(1, Math.round(logo.width * scale));
  const h = Math.max(1, Math.round(logo.height * scale));

  const small = document.createElement("canvas");
  small.width = w;
  small.height = h;
  const smallCtx = small.getContext("2d");
  smallCtx.drawImage(logo, 0, 0, w, h);

  byResolution.set(resolution, small);
  return small;
}

// Scales an image to fit `box` (preserving aspect ratio) and centers it.
// `boost` overscales beyond a strict fit (e.g. for art with a lot of
// transparent padding baked into the file) -- the image can extend past the
// box's edges when boost > 1, which is fine since it's still centered on it.
// `pixelate` (default true) applies the retro blocky treatment; pass false
// for art that should stay smooth (e.g. the probables board's pitcher art).
// `resolution` overrides how blocky it is (higher = finer/less blocky) --
// e.g. a higher value than PIXELATE_RESOLUTION for an "only slightly" effect.
function drawLogoInBox(logo, box, boost = 1, pixelate = true, resolution = PIXELATE_RESOLUTION) {
  const source = pixelate ? getPixelatedLogo(logo, resolution) : logo;
  const scale = Math.min(box.w / logo.width, box.h / logo.height) * boost;
  const w = logo.width * scale;
  const h = logo.height * scale;
  const x = box.x + (box.w - w) / 2;
  const y = box.y + (box.h - h) / 2;

  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = !pixelate; // blocky when pixelating, smooth otherwise
  ctx.drawImage(source, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;
}

// ---------------------------
// Headlines board
// ---------------------------
// Greedy word-wrap for a single headline: first line gets `prefix` ("..  "),
// any wrapped continuation lines get `contIndent` instead, so long headlines
// visually align under the first line rather than restarting at the margin.
function wrapHeadline(text, prefix, contIndent, maxWidth, ctxRef) {
  const words = text.split(/\s+/);
  const lines = [];
  let first = true;
  while (words.length) {
    const label = first ? prefix : contIndent;
    const avail = maxWidth - ctxRef.measureText(label).width;
    const line = [];
    while (words.length) {
      const test = [...line, words[0]].join(" ");
      if (ctxRef.measureText(test).width <= avail) {
        line.push(words.shift());
      } else {
        if (line.length === 0) line.push(words.shift());
        break;
      }
    }
    lines.push(label + line.join(" "));
    first = false;
  }
  return lines;
}

function drawHeadlinesBoard(page, linesToShow) {
  const write = makeWriter(linesToShow);
  const titleY = inner.y + TEXT_PADDING;

  ctx.font = BODY_FONT;
  ctx.fillStyle = "rgb(235,150,60)"; // warm accent for the headlines title
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  let title = "TODAY'S HEADLINES";
  if (page.totalPages > 1) title += ` (${page.page}/${page.totalPages})`;
  write(title, inner.x + TEXT_PADDING, titleY);

  const boxX = inner.x + TEXT_PADDING;
  const boxY = titleY + BODY_FONT_PX + 20;
  const boxW = inner.w - TEXT_PADDING * 2;
  const boxH = inner.bottom - TEXT_PADDING - boxY;
  ctx.strokeStyle = "rgb(200,180,80)";
  ctx.lineWidth = 2;
  ctx.strokeRect(boxX, boxY, boxW, boxH);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  const lineHeight = BODY_FONT_PX + 4;
  const textMaxWidth = boxW - 28;
  let y = boxY + 14;

  for (const headline of page.headlines) {
    const lines = wrapHeadline(headline.title, "..", "  ", textMaxWidth, ctx);
    for (const line of lines) {
      write(line, boxX + 14, y);
      y += lineHeight;
    }
    y += 10; // gap between headlines
  }
}

// ---------------------------
// Probables board
// ---------------------------
function drawProbablesBoard(page, probableLogo, linesToShow) {
  const write = makeWriter(linesToShow);
  const titleY = inner.y + TEXT_PADDING;
  const rowHeight = BODY_FONT_PX + 4;
  const rowBlockHeight = rowHeight * 2 + 18; // two lines per game + gap

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  let title = `${page.dateLabel} ${page.league} Games`;
  if (page.totalPages > 1) title += ` (${page.page}/${page.totalPages})`;
  write(title, inner.x + TEXT_PADDING, titleY);

  // Full-size badge in the standard logo column, same as story slides.
  // Rows only occupy the left column, so the pitcher badge can use the full
  // right-column height (not just the standard 200px logo box) -- it's tall
  // art, so this lets it render much larger without overflowing the panel.
  if (probableLogo) {
    const tallBox = { x: rightRect.x, y: inner.y, w: rightRect.w, h: inner.bottom - inner.y };
    drawLogoInBox(probableLogo, tallBox, 1, false); // keep this one smooth, not pixelated
  }

  ctx.font = BODY_FONT;
  let rowY = titleY + BODY_FONT_PX + 24;
  const rowX = inner.x + TEXT_PADDING;
  const rowW = leftRect.w - TEXT_PADDING * 2; // leave the logo column clear

  for (const game of page.games) {
    ctx.fillStyle = BOARD_ROW_BG;
    ctx.fillRect(rowX - 8, rowY - 4, rowW, rowBlockHeight - 10);

    ctx.fillStyle = TEXT_COLOR;
    write(`${game.away}  (${game.away_pitcher})`, rowX, rowY);
    write(`at ${game.home}  (${game.home_pitcher})`, rowX, rowY + rowHeight);

    rowY += rowBlockHeight;
  }
}

// ---------------------------
// Title card
// ---------------------------
// Full-canvas image, covering the header/panel/ticker entirely -- a bumper
// shown once at the start of every rotation loop.
function drawTitleCard(image) {
  if (!image) return;
  const scale = Math.max(WIDTH / image.width, HEIGHT / image.height);
  const w = image.width * scale;
  const h = image.height * scale;
  const x = (WIDTH - w) / 2;
  const y = (HEIGHT - h) / 2;
  ctx.drawImage(image, x, y, w, h);
}

// ---------------------------
// Standings board
// ---------------------------
function drawStandingsBoard(page, logos, linesToShow) {
  const shouldShow = makeLineGate(linesToShow);
  const division = page.division;
  const isNFL = page.sport === "nfl";
  const isNHL = page.sport === "nhl";
  const titleY = inner.y + TEXT_PADDING;

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  if (shouldShow()) ctx.fillText(division.name, inner.x + TEXT_PADDING, titleY);

  ctx.font = BODY_FONT;
  const rowHeight = BODY_FONT_PX + 12;
  let rowY = titleY + BODY_FONT_PX + 30;
  const nameX = inner.x + TEXT_PADDING;
  const colW = Math.max(100, leftRect.w - TEXT_PADDING * 2);
  // Column positions sized from actual measured glyph widths at this font
  // (monospace, 18px/char), not eyeballed fractions -- the previous 0.90
  // GB/PTS position left only ~57px of room before the row highlight's
  // right edge, too little for a 4-char value like "16.5" (72px), so it
  // rendered past the blue background. Name column narrowed to free up
  // that room; still comfortably fits the longest real team name ("Golden
  // Knights", ~252px) with margin to spare.
  const colWX = nameX + colW * 0.44;
  const colLX = nameX + colW * 0.55;
  const colTX = nameX + colW * 0.65; // NFL only (ties)
  const col4X = nameX + colW * (isNFL ? 0.69 : 0.65); // NHL: OTL, others: PCT
  const col5X = nameX + colW * 0.79; // NHL: PTS, MLB/NBA: GB -- NFL has neither

  // Column headers
  if (shouldShow()) {
    ctx.fillStyle = "rgb(200,180,120)";
    ctx.fillText("W", colWX, rowY);
    ctx.fillText("L", colLX, rowY);
    if (isNFL) ctx.fillText("T", colTX, rowY);
    if (isNHL) {
      ctx.fillText("OTL", col4X, rowY);
      ctx.fillText("PTS", col5X, rowY);
    } else {
      ctx.fillText("PCT", col4X, rowY);
      if (!isNFL) ctx.fillText("GB", col5X, rowY);
    }
  }
  rowY += rowHeight;

  for (const team of division.teams) {
    if (shouldShow()) {
      ctx.fillStyle = BOARD_ROW_BG;
      ctx.fillRect(nameX - 8, rowY - 4, colW, rowHeight - 6);
      ctx.fillStyle = TEXT_COLOR;
      ctx.fillText(team.name, nameX, rowY);
      ctx.fillText(team.w, colWX, rowY);
      ctx.fillText(team.l, colLX, rowY);
      if (isNFL) ctx.fillText(team.t || "0", colTX, rowY);
      if (isNHL) {
        ctx.fillText(team.otl || "0", col4X, rowY);
        ctx.fillText(team.pts || "0", col5X, rowY);
      } else {
        ctx.fillText(team.pct, col4X, rowY);
        if (!isNFL) ctx.fillText(team.gb || "--", col5X, rowY);
      }
    }
    rowY += rowHeight;
  }

  // AL/NL divisions get their league badge; everything else falls back to
  // its sport's generic logo (no conference-specific art for NFL/NBA/NHL).
  let badgeLogo = logos[page.sport] || logos.mlb;
  if (division.name.startsWith("American League") && logos.al) badgeLogo = logos.al;
  else if (division.name.startsWith("National League") && logos.nl) badgeLogo = logos.nl;
  if (badgeLogo) drawLogoInBox(badgeLogo, rightRect);
}

// ---------------------------
// Latest Line board (NFL betting lines)
// ---------------------------
function drawLatestLineBoard(page, sportLogo, linesToShow) {
  const shouldShow = makeLineGate(linesToShow);
  const titleY = inner.y + TEXT_PADDING;
  const sportLabel = `${(page.sport || "nfl").toUpperCase()} GAMES`;

  ctx.font = BOARD_TITLE_FONT;
  ctx.fillStyle = "rgb(235,150,60)"; // same warm accent as the headlines title
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  if (shouldShow()) ctx.fillText("LATEST LINE", inner.x + TEXT_PADDING, titleY);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  if (shouldShow()) ctx.fillText(sportLabel, inner.x + TEXT_PADDING, titleY + BOARD_TITLE_FONT_PX + 16);

  // Everything below here (headers, day label, rows) starts below the
  // logo's bottom edge and uses the full panel width -- no need to stay
  // narrow once past the image, same as story-slide wrapping.
  let subY = Math.max(rightRect.y + rightRect.h + 20, titleY + BOARD_TITLE_FONT_PX + 16 + BODY_FONT_PX + 20);

  let dayLabel = `(${page.day})`;
  if (page.totalPages > 1) dayLabel += ` ${page.page}/${page.totalPages}`;

  const nameX = inner.x + TEXT_PADDING;
  const colW = inner.w - TEXT_PADDING * 2; // full panel width
  const colPointsX = nameX + colW * 0.5;
  const colUnderdogX = nameX + colW * 0.65;

  // Column headers
  if (shouldShow()) {
    ctx.fillStyle = "rgb(200,180,120)";
    ctx.fillText("FAVORITE", nameX, subY);
    ctx.fillText("Pts", colPointsX, subY);
    ctx.fillText("UNDERDOG", colUnderdogX, subY);
  }
  subY += BODY_FONT_PX + 8;

  if (shouldShow()) {
    ctx.fillStyle = TEXT_COLOR;
    ctx.fillText(dayLabel, nameX, subY);
  }
  subY += BODY_FONT_PX + 12;

  const rowHeight = BODY_FONT_PX + 12;
  for (const game of page.games) {
    const favoriteIsHome = game.favorite === "home";
    const favoriteLabel = favoriteIsHome ? game.home.toUpperCase() : game.away;
    const underdogLabel = favoriteIsHome ? game.away : game.home.toUpperCase();

    if (shouldShow()) {
      ctx.fillStyle = BOARD_ROW_BG;
      ctx.fillRect(nameX - 8, subY - 4, colW, rowHeight - 6);
      ctx.fillStyle = TEXT_COLOR;
      ctx.fillText(favoriteLabel, nameX, subY);
      ctx.fillText(String(game.points), colPointsX, subY);
      ctx.fillText(underdogLabel, colUnderdogX, subY);
    }
    subY += rowHeight;
  }

  subY += 10;
  ctx.font = SMALL_FONT;
  ctx.fillStyle = "rgb(180,180,200)";
  if (shouldShow()) ctx.fillText("Home Team in CAPS", nameX, subY);

  if (sportLogo) drawLogoInBox(sportLogo, rightRect);
}

// ---------------------------
// Shared: tall left-column logo, flush with the panel's bottom edge
// ---------------------------
// Used by boards styled with a big character graphic on the left (On This
// Day, Today's Sports Birthdays) instead of the standard right-side logo
// column. Returns the x where text content should start.
const LEFT_LOGO_BOX = { w: 338, h: 416 }; // bigger than the standard 200x200 logo box (~30% bigger than the first pass)

// `boost` overscales beyond a strict fit to LEFT_LOGO_BOX (same pattern as
// drawLogoInBox) -- the image can extend past the box's nominal edges when
// boost > 1, staying centered/flush-bottom, without widening the reserved
// text column (leftColumnTextStartX still uses the base LEFT_LOGO_BOX.w).
function drawLeftColumnLogo(logo, resolution = PIXELATE_RESOLUTION, boost = 1) {
  if (!logo) return;
  const x0 = inner.x;
  const y0 = inner.bottom - LEFT_LOGO_BOX.h;

  const scale = Math.min(LEFT_LOGO_BOX.w / logo.width, LEFT_LOGO_BOX.h / logo.height) * boost;
  const w = logo.width * scale;
  const h = logo.height * scale;
  const x = x0 + (LEFT_LOGO_BOX.w - w) / 2; // centered horizontally in its column
  const y = y0 + LEFT_LOGO_BOX.h - h;       // flush with the bottom

  const source = getPixelatedLogo(logo, resolution);
  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;
}

function leftColumnTextStartX(hasLogo) {
  return hasLogo ? inner.x + LEFT_LOGO_BOX.w + 24 : inner.x + TEXT_PADDING;
}

// ---------------------------
// On This Day (sports history fact)
// ---------------------------
const HISTORY_LOGO_PIXELATE_RESOLUTION = 200; // higher than PIXELATE_RESOLUTION -- only slightly blocky
const BIRTHDAY_LOGO_PIXELATE_RESOLUTION = 160; // double the default -- ~50% less blocky

function drawHistoryBoard(page, historyLogo, linesToShow) {
  const write = makeWriter(linesToShow);
  const titleY = inner.y + TEXT_PADDING;
  const textStartX = leftColumnTextStartX(!!historyLogo);
  const textWidth = Math.max(40, inner.right - TEXT_PADDING - textStartX);

  ctx.font = BOARD_TITLE_FONT;
  ctx.fillStyle = "rgb(180,210,120)"; // yellow-green accent, distinct from the other board titles
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  write(page.dateLabel, textStartX, titleY);

  const bodyY = titleY + BOARD_TITLE_FONT_PX + 20;
  const yearPrefix = page.fact.year ? `In ${page.fact.year}, ` : "";
  const wrapped = wrapTextToWidth(yearPrefix + page.fact.text, textWidth, ctx);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  const lineHeight = BODY_FONT_PX + 4;
  let lineY = bodyY;
  for (const line of wrapped) {
    write(line, textStartX, lineY);
    lineY += lineHeight;
  }

  drawLeftColumnLogo(historyLogo, HISTORY_LOGO_PIXELATE_RESOLUTION);
}

// ---------------------------
// Today's Sports Birthdays
// ---------------------------
function drawBirthdaysBoard(page, birthdayLogo, linesToShow) {
  const write = makeWriter(linesToShow);
  const titleY = inner.y + TEXT_PADDING;
  const textStartX = leftColumnTextStartX(!!birthdayLogo);
  const textWidth = Math.max(40, inner.right - TEXT_PADDING - textStartX);

  ctx.font = BOARD_TITLE_FONT;
  ctx.fillStyle = "rgb(235,150,60)"; // same warm accent as headlines/latest line
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  write("TODAY'S SPORTS", textStartX, titleY);
  write("BIRTHDAYS", textStartX, titleY + BOARD_TITLE_FONT_PX + 4);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  let y = titleY + (BOARD_TITLE_FONT_PX + 4) * 2 + 16;
  write(page.dateLabel, textStartX, y);
  y += BODY_FONT_PX + 24;

  const lineHeight = BODY_FONT_PX + 4;
  for (const person of page.people) {
    if (person.desc) {
      for (const line of wrapTextToWidth(person.desc, textWidth, ctx)) {
        write(line, textStartX, y);
        y += lineHeight;
      }
    }
    for (const line of wrapTextToWidth(`${person.name} turns ${person.age}.`, textWidth, ctx)) {
      write(line, textStartX, y);
      y += lineHeight;
    }
    y += 20;
  }

  drawLeftColumnLogo(birthdayLogo, BIRTHDAY_LOGO_PIXELATE_RESOLUTION);
}

// ---------------------------
// Sports Trivia
// ---------------------------
// questionLinesToShow paces the question's own reveal; answerLinesToShow
// (computed from time since the reveal moment, not overall elapsed) paces
// the answer's reveal starting fresh once it appears.
function drawTriviaBoard(page, questionLogo, answerLogo, revealed, questionLinesToShow, answerLinesToShow) {
  const write = makeWriter(questionLinesToShow);
  const logo = revealed ? answerLogo : questionLogo;
  const titleY = inner.y + TEXT_PADDING;
  const textStartX = leftColumnTextStartX(!!logo);
  const textWidth = Math.max(40, inner.right - TEXT_PADDING - textStartX);

  ctx.font = BOARD_TITLE_FONT;
  ctx.fillStyle = "rgb(235,150,60)"; // same warm accent as headlines/latest line/birthdays
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  write("SPORTS TRIVIA", textStartX, titleY);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  const lineHeight = BODY_FONT_PX + 4;
  let y = titleY + BOARD_TITLE_FONT_PX + 20;
  for (const line of wrapTextToWidth(page.trivia.question, textWidth, ctx)) {
    write(line, textStartX, y);
    y += lineHeight;
  }

  if (revealed) {
    const writeAnswer = makeWriter(answerLinesToShow);
    y += 20;
    ctx.fillStyle = "rgb(200,180,120)";
    writeAnswer("ANSWER:", textStartX, y);
    y += lineHeight;
    ctx.fillStyle = TEXT_COLOR;
    for (const line of wrapTextToWidth(page.trivia.answer, textWidth, ctx)) {
      writeAnswer(line, textStartX, y);
      y += lineHeight;
    }
  }

  drawLeftColumnLogo(logo, BIRTHDAY_LOGO_PIXELATE_RESOLUTION);
}

// ---------------------------
// League Quote (shown once after each league's block)
// ---------------------------
function drawQuoteBoard(page, quoteLogo, linesToShow) {
  const write = makeWriter(linesToShow);
  const titleY = inner.y + TEXT_PADDING;
  const textStartX = leftColumnTextStartX(!!quoteLogo);
  const textWidth = Math.max(40, inner.right - TEXT_PADDING - textStartX);

  ctx.font = BOARD_TITLE_FONT;
  ctx.fillStyle = "rgb(180,210,120)"; // same yellow-green accent as On This Day
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  write(`${page.league.toUpperCase()} QUOTE`, textStartX, titleY);
  write("OF THE DAY", textStartX, titleY + BOARD_TITLE_FONT_PX + 4);

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  const lineHeight = BODY_FONT_PX + 4;
  let y = titleY + (BOARD_TITLE_FONT_PX + 4) * 2 + 20;
  for (const line of wrapTextToWidth(`"${page.quote}"`, textWidth, ctx)) {
    write(line, textStartX, y);
    y += lineHeight;
  }

  y += 16;
  ctx.fillStyle = "rgb(200,180,120)";
  write(`- ${page.author.toUpperCase()}`, textStartX, y);

  drawLeftColumnLogo(quoteLogo, BIRTHDAY_LOGO_PIXELATE_RESOLUTION, 1.15);
}

// ---------------------------
// Section Intro ("FOOTBALL" / "COMING UP: ...")
// ---------------------------
function drawSectionIntroBoard(page, linesToShow) {
  const write = makeWriter(linesToShow);
  const centerX = inner.x + inner.w / 2;
  const ruleX = inner.x + TEXT_PADDING;
  const ruleW = inner.w - TEXT_PADDING * 2;
  let y = inner.y + TEXT_PADDING + 10;

  ctx.fillStyle = "rgba(235,150,60,0.55)"; // matches the title's warm accent
  ctx.fillRect(ruleX, y, ruleW, 3);
  y += 3 + 12;

  ctx.font = `${BOARD_TITLE_FONT_PX + 12}px PxPlusIBMVGA8, monospace`;
  ctx.fillStyle = "rgb(235,150,60)"; // same warm accent as the other board titles
  ctx.textBaseline = "top";
  ctx.textAlign = "center";
  write(page.sportName, centerX, y);
  y += BOARD_TITLE_FONT_PX + 12 + 12;

  ctx.fillStyle = "rgba(235,150,60,0.55)";
  ctx.fillRect(ruleX, y, ruleW, 3);
  y += 3 + 20;

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  write("COMING UP:", centerX, y);
  y += BODY_FONT_PX + 30;

  ctx.textAlign = "left";
  const listX = inner.x + TEXT_PADDING + 20;
  const listWidth = Math.max(40, inner.w - TEXT_PADDING * 2 - 40);
  const lineHeight = BODY_FONT_PX + 4;
  for (const headline of page.headlines) {
    for (const line of wrapHeadline(headline, "- ", "  ", listWidth, ctx)) {
      write(line, listX, y);
      y += lineHeight;
    }
    y += 10;
  }
}

// ---------------------------
// Score Results ("Monday's NFL Result")
// ---------------------------
function drawScoreResultsBoard(page, leagueLogo, linesToShow) {
  const shouldShow = makeLineGate(linesToShow);
  const titleY = inner.y + TEXT_PADDING;

  ctx.font = BODY_FONT;
  ctx.fillStyle = TEXT_COLOR;
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  let title = `${page.dayLabel} ${page.league.toUpperCase()} Result`;
  if (page.totalPages > 1) title += ` (${page.page}/${page.totalPages})`;
  if (shouldShow()) ctx.fillText(title, inner.x + TEXT_PADDING, titleY);

  const nameX = inner.x + TEXT_PADDING;
  const colW = leftRect.w - TEXT_PADDING * 2; // leave the logo column clear
  const scoreX = nameX + colW - 10;
  const rowHeight = BODY_FONT_PX + 12;
  let rowY = titleY + BODY_FONT_PX + 30;

  for (const game of page.games) {
    if (shouldShow()) {
      ctx.fillStyle = BOARD_ROW_BG;
      ctx.fillRect(nameX - 8, rowY - 4, colW, rowHeight - 6);
      ctx.fillStyle = TEXT_COLOR;
      ctx.textAlign = "left";
      ctx.fillText(game.away, nameX, rowY);
      ctx.textAlign = "right";
      ctx.fillText(String(game.away_score), scoreX, rowY);
      ctx.textAlign = "left";
    }
    rowY += rowHeight;

    if (shouldShow()) {
      ctx.fillStyle = BOARD_ROW_BG;
      ctx.fillRect(nameX - 8, rowY - 4, colW, rowHeight - 6);
      ctx.fillStyle = TEXT_COLOR;
      ctx.textAlign = "left";
      ctx.fillText(game.home, nameX, rowY);
      ctx.textAlign = "right";
      ctx.fillText(String(game.home_score), scoreX, rowY);
      ctx.textAlign = "left";
    }
    rowY += rowHeight;

    // MLB only -- winning/losing/save pitcher, wrapped to fit the column
    // rather than assumed to fit on one line (names/records vary in length).
    if (game.winning_pitcher || game.losing_pitcher) {
      const parts = [];
      if (game.winning_pitcher) parts.push(`W: ${game.winning_pitcher}`);
      if (game.losing_pitcher) parts.push(`L: ${game.losing_pitcher}`);
      if (game.save_pitcher) parts.push(`SV: ${game.save_pitcher}`);
      ctx.font = SMALL_FONT;
      const pitcherLines = wrapTextToWidth(parts.join("   "), colW, ctx);
      if (shouldShow()) {
        ctx.fillStyle = "rgb(180,180,200)";
        for (const line of pitcherLines) {
          ctx.fillText(line, nameX, rowY);
          rowY += SMALL_FONT_PX + 4;
        }
      } else {
        rowY += pitcherLines.length * (SMALL_FONT_PX + 4);
      }
      ctx.font = BODY_FONT;
      rowY += 2;
    }

    rowY += 14;
  }

  if (leagueLogo) drawLogoInBox(leagueLogo, rightRect);
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
  audioEl.src = `../media/music_normalized/${encodeURIComponent(track)}`;
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
// Builds the full rotation array from scratch by re-fetching every data/*.json
// file -- used both for the initial load and for the periodic full refresh
// (see the "refresh" card appended at the end, below). Doesn't touch logos/
// images: those are cached separately by filename and rarely change, so
// there's no need to re-fetch them just because the data behind a card did.
async function buildRotation() {
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

  let mlbStandingsPages = [];
  try {
    mlbStandingsPages = buildStandingsPages(await loadJSON("../data/standings.json"));
  } catch (e) {
    console.warn("[standings] load failed:", e);
  }

  let nflStandingsPages = [];
  try {
    nflStandingsPages = buildStandingsPages(await loadJSON("../data/nfl_standings.json"));
  } catch (e) {
    console.warn("[nfl standings] load failed:", e);
  }

  let nbaStandingsPages = [];
  try {
    nbaStandingsPages = buildStandingsPages(await loadJSON("../data/nba_standings.json"));
  } catch (e) {
    console.warn("[nba standings] load failed:", e);
  }

  let nhlStandingsPages = [];
  try {
    nhlStandingsPages = buildStandingsPages(await loadJSON("../data/nhl_standings.json"));
  } catch (e) {
    console.warn("[nhl standings] load failed:", e);
  }

  let latestLinePages = [];
  try {
    latestLinePages = buildLatestLinePages(await loadJSON("../data/latest_line.json"), "nfl");
  } catch (e) {
    console.warn("[latest line] load failed:", e);
  }

  let nbaLinePages = [];
  try {
    nbaLinePages = buildLatestLinePages(await loadJSON("../data/nba_line.json"), "nba");
  } catch (e) {
    console.warn("[nba line] load failed:", e);
  }

  let nhlLinePages = [];
  try {
    nhlLinePages = buildLatestLinePages(await loadJSON("../data/nhl_line.json"), "nhl");
  } catch (e) {
    console.warn("[nhl line] load failed:", e);
  }

  let headlinesPages = [];
  try {
    headlinesPages = buildHeadlinesPages(await loadJSON("../data/headlines.json"), ctx);
  } catch (e) {
    console.warn("[headlines] load failed:", e);
  }

  let historyPages = [];
  try {
    historyPages = buildHistoryPage(await loadJSON("../data/history.json"));
  } catch (e) {
    console.warn("[history] load failed:", e);
  }

  let birthdaysPages = [];
  try {
    birthdaysPages = buildBirthdaysPage(await loadJSON("../data/birthdays.json"));
  } catch (e) {
    console.warn("[birthdays] load failed:", e);
  }

  let triviaPages = [];
  try {
    triviaPages = buildTriviaPage(await loadJSON("../data/trivia.json"));
  } catch (e) {
    console.warn("[trivia] load failed:", e);
  }

  let mlbScoreResultsPages = [], nflScoreResultsPages = [];
  try {
    const scoreResultsData = await loadJSON("../data/score_results.json");
    mlbScoreResultsPages = buildScoreResultsPages(scoreResultsData, "mlb");
    nflScoreResultsPages = buildScoreResultsPages(scoreResultsData, "nfl");
  } catch (e) {
    console.warn("[score results] load failed:", e);
  }

  let mlbQuotePages = [], nflQuotePages = [], nbaQuotePages = [], nhlQuotePages = [];
  try {
    const quotesData = await loadJSON("../data/quotes.json");
    mlbQuotePages = buildQuotePage(quotesData, "mlb");
    nflQuotePages = buildQuotePage(quotesData, "nfl");
    nbaQuotePages = buildQuotePage(quotesData, "nba");
    nhlQuotePages = buildQuotePage(quotesData, "nhl");
  } catch (e) {
    console.warn("[quotes] load failed:", e);
  }

  // Rotation order: title card -> today's headlines -> On This Day (not
  // league-specific) -> MLB block (AL/NL probables -> MLB stories -> 6
  // division standings -> MLB quote) -> NFL block (latest line -> NFL
  // stories -> 8 division standings -> NFL quote) -> NBA block (latest line
  // -> NBA stories -> 6 division standings -> NBA quote) -> NHL block
  // (latest line -> NHL stories -> 4 division standings -> NHL quote) ->
  // loop. MLB is the priority league (shows first); any board type is simply
  // absent if it's that sport's off-season (each builder returns [] then).
  const knownLeagues = ["nfl", "mlb", "nba", "nhl"];
  const nflSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "nfl")
    .map((s) => ({ type: "story", slide: s }));
  const mlbSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "mlb")
    .map((s) => ({ type: "story", slide: s }));
  const nbaSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "nba")
    .map((s) => ({ type: "story", slide: s }));
  const nhlSlides = storySlides.filter((s) => (s.league || "").toLowerCase() === "nhl")
    .map((s) => ({ type: "story", slide: s }));
  const otherSlides = storySlides.filter((s) => !knownLeagues.includes((s.league || "").toLowerCase()))
    .map((s) => ({ type: "story", slide: s }));

  // Section intros preview a few real headlines from that league's own
  // slides, so they need to be built after each league's *Slides exist.
  const mlbIntroPages = buildSectionIntroPage("BASEBALL", mlbSlides);
  const nflIntroPages = buildSectionIntroPage("FOOTBALL", nflSlides);
  const nbaIntroPages = buildSectionIntroPage("BASKETBALL", nbaSlides);
  const nhlIntroPages = buildSectionIntroPage("HOCKEY", nhlSlides);

  const items = [
    { type: "titlecard" },
    ...headlinesPages,
    ...historyPages,
    ...birthdaysPages,
    ...triviaPages,
    ...mlbIntroPages, ...mlbScoreResultsPages, ...probablesPages, ...mlbSlides, ...mlbStandingsPages, ...mlbQuotePages,
    ...nflIntroPages, ...nflScoreResultsPages, ...latestLinePages, ...nflSlides, ...nflStandingsPages, ...nflQuotePages,
    ...nbaIntroPages, ...nbaLinePages, ...nbaSlides, ...nbaStandingsPages, ...nbaQuotePages,
    ...nhlIntroPages, ...nhlLinePages, ...nhlSlides, ...nhlStandingsPages, ...nhlQuotePages,
    ...otherSlides,
  ];
  if (items.length === 1) items.push({ type: "story", slide: { title: "", body: "No content available.", logo: null } });

  // Short blank card at the very end of every lap -- gives a fixed, known
  // point to kick off the next full data refresh in the background (see
  // prepareItem/frame below) without risking a mid-frame swap of the live
  // rotation array. No dedicated render branch needed: nothing in frame()'s
  // dispatch matches "refresh", so the panel just stays on its plain
  // background for the card's short duration.
  items.push({ type: "refresh" });

  return items;
}

async function main() {
  await Promise.all([
    document.fonts.load(BODY_FONT),
    document.fonts.load(HEADER_FONT),
    document.fonts.load(SMALL_FONT),
    document.fonts.load(TICKER_FONT),
    document.fonts.load(BOARD_TITLE_FONT),
  ]);

  let items = await buildRotation();

  let tickerText = "SPORTS PLUS NETWORK • AUTOMATED SPORTS NEWS FEED •";
  let tickerWidth = 0;
  async function loadTicker() {
    try {
      const tickerData = await loadJSON("../data/ticker.json");
      if (tickerData.items && tickerData.items.length) {
        tickerText = "   |   " + tickerData.items.join("   |   ");
      }
    } catch (e) {
      console.warn("[ticker] load failed:", e);
    }
    ctx.font = TICKER_FONT;
    tickerWidth = ctx.measureText(tickerText).width;
  }
  await loadTicker();

  const headerLogo = await loadImage("../media/logos/sportschannel.png");
  const mlbLogo = await getLogo("mlb.png");
  const alLogo = await getLogo("AL.png");
  const nlLogo = await getLogo("NL.png");
  const nflLogo = await getLogo("nfl.png");
  const nbaLogo = await getLogo("nba.png");
  const nhlLogo = await getLogo("nhl.png");
  const probableLogo = await getLogo("probable.png");
  const historyLogo = await getLogo("history.png");
  const birthdayLogo = await getLogo("birthday.png");
  const questionLogo = await getLogo("question.png");
  const answerLogo = await getLogo("answer.png");
  const quoteLogo = await getLogo("quote.png");
  const titleCardImage = await loadImage("../media/logos/titlecard.png");
  const standingsLogos = { mlb: mlbLogo, al: alLogo, nl: nlLogo, nfl: nflLogo, nba: nbaLogo, nhl: nhlLogo };
  const latestLineLogos = { nfl: nflLogo, nba: nbaLogo, nhl: nhlLogo };

  await setupMusic();
  playCurrentTrack();

  let currentIndex = 0;
  let slideStartTime = performance.now() / 1000;
  let wrappedLines = [];
  let currentLogo = null;

  // Set when we land on the end-of-lap "refresh" card; holds the in-flight
  // rebuild so frame() can pick it up once we're ready to leave that card.
  let pendingRefresh = null;

  async function prepareItem(idx) {
    const item = items[idx];
    if (item.type === "refresh") {
      // Kick off in the background -- don't await here, so the blank card
      // still shows immediately and the frame loop keeps running normally
      // while the new data loads (ticker included, so this supersedes the
      // ticker's own separate refresh cadence).
      pendingRefresh = Promise.all([buildRotation(), loadTicker()]).then(([newItems]) => newItems);
      pendingRefresh.catch((e) => console.warn("[refresh] failed:", e));
      return;
    }
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
    const duration = item.type === "story" ? SLIDE_DURATION
      : item.type === "titlecard" ? TITLECARD_DURATION
      : item.type === "trivia" ? TRIVIA_DURATION
      : item.type === "refresh" ? REFRESH_CARD_DURATION
      : BOARD_DURATION;

    if (elapsed >= duration) {
      // Leaving the end-of-lap "refresh" card: apply the rebuilt rotation
      // if it's ready by now (it almost always will be -- these are small
      // local JSON fetches, well within the card's short display time). If
      // it's somehow not ready yet, just keep the current data and try
      // again next lap; nothing breaks either way since index 0 (title
      // card) is valid in both the old and new arrays.
      if (item.type === "refresh" && pendingRefresh) {
        const refreshResult = pendingRefresh;
        pendingRefresh = null;
        refreshResult.then((newItems) => {
          if (newItems && newItems.length) items = newItems;
        });
      }

      const nextIndex = (currentIndex + 1) % items.length;
      currentIndex = nextIndex;
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

    if (item.type === "titlecard") {
      // Full-canvas bumper -- no header/panel/ticker chrome over it.
      drawTitleCard(titleCardImage);
      requestAnimationFrame(frame);
      return;
    }

    drawHeader(headerLogo);

    ctx.fillStyle = PANEL_BG;
    ctx.fillRect(contentRect.x, contentRect.y, contentRect.w, contentRect.h);
    ctx.fillStyle = INNER_FILL;
    ctx.fillRect(inner.x, inner.y, inner.w, inner.h);

    // Shared typewriter pacing for every board type -- consistent
    // line-by-line reveal throughout the app, not just on story slides.
    const boardLinesToShow = Math.floor(elapsed / LINE_DELAY);

    if (item.type === "story") {
      const linesToShow = Math.min(wrappedLines.length, boardLinesToShow);
      drawSlideText(wrappedLines, linesToShow, currentLogo);
    } else if (item.type === "headlines") {
      drawHeadlinesBoard(item, boardLinesToShow);
    } else if (item.type === "probables") {
      drawProbablesBoard(item, probableLogo, boardLinesToShow);
    } else if (item.type === "standings") {
      drawStandingsBoard(item, standingsLogos, boardLinesToShow);
    } else if (item.type === "latest_line") {
      drawLatestLineBoard(item, latestLineLogos[item.sport] || nflLogo, boardLinesToShow);
    } else if (item.type === "history_fact") {
      drawHistoryBoard(item, historyLogo, boardLinesToShow);
    } else if (item.type === "birthdays") {
      drawBirthdaysBoard(item, birthdayLogo, boardLinesToShow);
    } else if (item.type === "trivia") {
      const revealed = elapsed >= TRIVIA_REVEAL_DELAY;
      const answerLinesToShow = Math.floor((elapsed - TRIVIA_REVEAL_DELAY) / LINE_DELAY);
      drawTriviaBoard(item, questionLogo, answerLogo, revealed, boardLinesToShow, answerLinesToShow);
    } else if (item.type === "quote") {
      drawQuoteBoard(item, quoteLogo, boardLinesToShow);
    } else if (item.type === "section_intro") {
      drawSectionIntroBoard(item, boardLinesToShow);
    } else if (item.type === "score_results") {
      drawScoreResultsBoard(item, item.league === "nfl" ? nflLogo : mlbLogo, boardLinesToShow);
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
