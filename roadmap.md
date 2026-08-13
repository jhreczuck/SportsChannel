# SportsChannel Web Port — Roadmap

## Goal
Take the existing pygame desktop app (retro Sports Plus Network simulation) and make it
viewable as a webpage, while keeping a desktop `.exe` build available too. Content refreshes
on a schedule (every 1–2 hours), not live-per-visitor, so the browser never talks to ESPN or
OpenAI directly.

## Sequencing note (why the web port comes before automation)
Right now, neither of us has a fast way to see the app render — it's a native pygame window,
so Claude can't screenshot or inspect it, and the only feedback loop is "run it manually, then
describe what you see." That's the actual bottleneck, and it's what a web port fixes: once the
UI is a page in a browser, Claude can open it directly, screenshot it, and iterate live.

So the plan front-loads a **minimal local web skeleton** (reusing the JSON already sitting in
`data/` today, no cron/server automation yet) ahead of the backend/deployment phases. Look-and-
feel work happens against that live skeleton, in-browser, before any automation is built —
no point automating hourly refreshes of a design that's still moving.

## Architecture decisions (locked in)
- **Renderer:** Rewrite the frontend in HTML5 Canvas + JS. Reuses the same layout/timing logic
  as `main.py` (header, text-reveal panel with word-wrap-around-logo, scrolling ticker) but as
  native web code — small footprint, fast load, no WASM/pygame runtime shipped to visitors.
- **Data refresh:** Server-side cron/systemd timer runs the existing `refresh_stories.py` +
  ticker fetch on a schedule (target: every 1–2 hours), writing static JSON files. The webpage
  only ever reads those static files from the same origin. This kills the CORS problem (ESPN's
  API doesn't need to be reachable from the browser) and keeps the OpenAI key server-side only.
- **No database.** Content is rotating slideshow state, not something that needs querying or
  history. Flat JSON stays sufficient. (Revisit only if we later want a searchable headline
  archive — that's a real use case for the existing Postgres instance, just not this one.)
- **Hosting target:** the Linux server (same box as the boston311 project). Static files served
  by nginx, refresh job runs via cron/systemd timer, deployed via the same push-then-pull
  workflow already used for boston311. GitHub Pages is an optional later mirror, not the
  primary target, since it can't run the refresh job itself.
- **Desktop build:** Parallel deliverable — package the current pygame app as a standalone
  `.exe` via PyInstaller for local/offline use. Independent of the web work.

---

## Phase 1 — Minimal local web skeleton ✅ done
- [x] Static page shell: 960×720 canvas, loads fonts via `@font-face`
      (`media/fonts/PxPlus_IBM_VGA8.ttf`).
- [x] Port `draw_header` → header bar + logo + live clock.
- [x] Port text wrapping — simplified from the original wrap-around-logo behavior to a single
      consistent width, since the logo now sits in its own fixed column (see Phase 2 notes).
- [x] Port slide rotation/reveal timing (`SLIDE_DURATION`, `LINE_DELAY`) using
      `requestAnimationFrame` + timestamps.
- [x] Port `draw_ticker` scroll/pause cycle logic.
- [x] Logo loading via canvas `drawImage` (no colorkey hacks needed, unlike pygame).
- [x] Background music: `<audio>` element, shuffled queue, `ended` event to advance. Autoplays
      on load; falls back to starting on first click/keypress if the browser blocks autoplay.
- [x] Page reads `data/stories_cleaned.json` / `data/ticker.json` directly via a local dev
      server (`.claude/launch.json` → `python -m http.server`), viewable by Claude via the
      Browser tool and by you at `http://localhost:8420/web/index.html`.

## Phase 2 — Look-and-feel iteration (live, in-browser) — in progress
- [x] Body + ticker font size bumped 24px → 32px to better fill the panel.
- [x] Removed the narrow-band wrap-around-logo behavior; logo now has its own fixed column,
      text uses one consistent width throughout.
- [x] Raised content-length targets (`news_feed.py` sentence cap, `refresh_stories.py`
      MAX_LEN/trim targets) to match the panel's real ~550-char capacity at the new font size,
      so slides use more of the available space instead of averaging half-full.
- [x] Header logo clipping fixed (was overflowing the 64px header bar).
- [ ] Further visual passes as they come up (colors, spacing, borders — open-ended).
- [ ] Reference screenshot from the original 1988–93 broadcast is on file for comparison
      (not actioned yet — user said not to match it automatically, just wanted a basis).

## Phase 3 — Backend refresh pipeline hardening
- [x] `refresh_stories.py` and `refresh_ticker.py` exist as separate manual-run scripts (not
      yet on a schedule — see Phase 5).
- [x] Fixed the silent LUFS-normalization failure (`ffmpeg` was missing locally — now installed
      via winget). Not yet re-verified that `normalize_track_lufs()` produces cached files.
- [ ] Since normalization only needs to run once per source file (not every refresh), split it
      out as a one-time/batch preprocessing step rather than something the runtime path depends on.
- [x] Ticker expanded beyond NFL-only — `refresh_ticker.py` fetches all four leagues
      (nfl/nba/mlb/nhl) by default via `ticker.py`.
- [x] Stories expanded beyond NFL-only — `news_feed.py`/`refresh_stories.py` now also pull MLB
      (46 slides total: 21 NFL + 25 MLB as of last refresh).
- [x] News-quality filtering: photo captions/datelines (3 distinct wire-service styles), inline
      "Mandatory Credit:" / Reuters wire-photo tags, and Yahoo's in-article fantasy-football
      promo ad are now stripped in `news_feed.py` before GPT cleaning ever sees them.
- [x] Fixed a real bug where a Windows console encoding error in a debug `print()` was silently
      swallowing every GPT-cleaning call and falling back to uncleaned text.
- [x] Fixed a UTF-8/cp1252 mojibake bug in `_fetch_rss` that was corrupting curly
      quotes/dashes into "�".
- [ ] Add basic error/staleness handling: if a refresh cycle fails, don't overwrite good JSON
      with an empty/broken one — write to a temp file and swap on success.

## Feature: MLB Probables Board (new)
A screen showing each day's probable starting pitchers, grouped by league, styled after the
original broadcast's "Monday's AL Games" boards (team @ team, pitcher name + W-L record per
matchup). Appears **before** the MLB news slides in rotation. Updated full rotation order becomes:
NFL stories → **AL probables → NL probables** → MLB stories → AL East → AL Central → AL West →
NL East → NL Central → NL West → (loop).

**Decisions:**
- **Data source: ESPN's MLB scoreboard endpoint** — the same one `ticker.py` already hits for
  scores. Verified each event's `competitions[0].competitors[].probables[0]` includes the
  pitcher's name and a `statistics` array with `wins`/`losses`, e.g. "Cleveland T. Bibee 4-11 at
  Detroit D. Anderson 4-4". No separate API needed.
- **Split into two screens by league** (AL / NL), matching the reference image's "Monday's AL
  Games" title format — not one combined list.
- **Team → league mapping**: ESPN's scoreboard doesn't label each game AL/NL directly, so this
  needs a small static lookup table (30 teams, doesn't change) to sort games into the right
  screen.
- **Pagination**: the reference shows 3 games per screen. If a league has more games than fit
  one screen, split into multiple screens (e.g. "Monday's AL Games (1/2)") rather than shrinking
  text to cram them in.
- **Seasonal gating**: shares the same MLB-season-only gate as the Standings Board feature below
  — no point fetching probables in the off-season.
- **Games with no announced probable**: show "TBD" for that pitcher rather than dropping the
  game (matches ESPN's own fallback behavior).

**Sub-tasks:**
- [x] `src/refresh_probables.py` — fetches the scoreboard, extracts each game's probables + W-L,
      groups by league via `src/mlb_divisions.py` (static team→league table), writes
      `data/probables.json`.
- [x] `web/app.js`: "probables board" slide type — title line, paired away/home rows per
      matchup, placeholder baseball-icon graphic (procedural, via `drawPlaceholderBaseball`)
      until real art is supplied.
- [x] Pagination logic (`buildProbablesPages`, `PROBABLES_GAMES_PER_SCREEN = 3`) — verified
      live data actually needs it (6 AL games → 2 screens, 8 NL games → 3 screens).
- [x] Rotation logic: AL/NL probables screens inserted before the MLB story slides
      (`src/mlb_season.py` shared seasonal gate via each script's `in_season` flag).

## Feature: MLB Standings Board (new)
A new screen type showing division standings (team, W, L, PCT, GB), styled after the original
broadcast's standings tables. Runs in the same rotation as the news slides, appearing after all
MLB story slides finish, cycling through all 6 divisions in order, then looping back to the
start of the whole rotation.

**Decisions locked in:**
- **Data source: ESPN's standings API**, not scraping baseball-reference.com — same reasoning
  as the ticker (already-JSON, no HTML-parsing fragility, no scraping ToS concerns). Verified
  working: `https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings?level=3` returns
  all 6 MLB divisions (AL/NL × East/Central/West) each with a `standings.entries` list of teams
  and their `wins`/`losses`/`winPercent`/`gamesBehind` stats.
- **Scope: all 6 divisions**, not just one.
- **Rotation placement: sequential, after the MLB news slides** — not interleaved randomly
  between individual stories. Combined with the Probables Board above, full order becomes:
  NFL stories → AL probables → NL probables → MLB stories → AL East → AL Central → AL West →
  NL East → NL Central → NL West → (loop).
- **Seasonal gating**: standings should only appear during the actual MLB season (roughly
  April–October). Off-season, they're skipped entirely rather than showing stale/empty tables.
- **Graphic**: placeholder only for now (e.g. the existing `media/logos/mlb.png`) — user will
  supply the real artwork later, matching the retro baseball-icon style in their reference
  screenshot.

**Sub-tasks:**
- [x] `src/refresh_standings.py` — fetches the ESPN `level=3` standings endpoint, writes
      `data/standings.json`.
- [x] Seasonal gate: `src/mlb_season.py` (shared with Probables), `MLB_SEASON_OVERRIDE=1/0` env
      var for testing off-season without waiting on the calendar.
- [x] `web/app.js`: "standings board" slide type — table renderer (division header, W/L/PCT/GB
      columns, team rows), `media/logos/mlb.png` as the logo-column graphic.
- [x] Rotation logic: standings boards appended after the MLB story slides, respecting the
      seasonal gate.
- [ ] Once the user supplies final artwork, swap the placeholder and refine table styling to
      match the retro look.

**Follow-up tweaks (post-build feedback):**
- [x] Probables board now uses the full panel width (no reserved logo column) and shows up to
      5 games per screen (was 3) — live data needs it (6 AL / 8 NL games → 2 pages each).
- [x] Probables board's placeholder graphic is now the actual `mlb.png` logo (small badge next
      to the title) instead of a procedurally-drawn baseball icon.
- [x] Board titles (probables date/league line, standings division name) now render in the same
      `PxPlusIBMVGA8` body font as the rest of the panel, instead of the Consolas header font.
- [x] Left/Right arrow keys manually step through the rotation (`goToItem` in `app.js`),
      overriding the auto-advance timer.
- [x] Reintroduced two-zone text wrapping for story slides with a logo: narrow width for lines
      beside the image, full panel width for lines below its bottom edge (previously flattened
      to one width throughout, wasting the space under shorter logos).
- [x] Probables board updated: full panel width (no reserved logo column), up to 5 games per
      screen, badge swapped to `media/logos/probable.png`.
- [x] Follow-up: probables board reverted to a reserved right-hand logo column (rows use
      `leftRect.w`, not full width) so the `probable.png` badge can render at full standard
      logo-box size instead of a small 56px corner icon.
- [x] Follow-up: `probable.png` is tall/narrow art (605×1533) that only filled ~79×200 in the
      standard square logo box. Since rows only occupy the left column, the badge now uses a
      tall box spanning the full right-column height (`inner.y` to `inner.bottom`, not just the
      top 200px) — renders at 200×507, filling the column properly instead of a small square.
- [x] Follow-up: `media/logos/AL.png` and `media/logos/NL.png` now used as the standings badge
      for American/National League divisions respectively, instead of the generic `mlb.png` for
      all 6. All 6 division badges are now league-specific.
- [x] Fixed team-logo inference for digit-prefixed nicknames (e.g. "49ers" has no uppercase
      letter at all -- `infer_logo_from_text` only matched capitalized words, so it always fell
      back to the generic `nfl.png`).
- [x] Added `src/fetch_team_logos.py`: downloads every NFL/MLB team logo from ESPN's team-list
      API (same naming convention `infer_logo_from_text` expects, e.g. `cowboys.png`,
      `redsox.png`) so hand-collecting 62 team logos isn't manual work. Won't overwrite existing
      files. Confirmed the downloaded PNGs are true RGBA with alpha (not a solid-background box).
- [x] Body font bumped again 32px → 36px (still room at the bottom of the panel). This *lowers*
      character capacity per slide (~546 → ~482 chars, fewer/narrower lines fit), so
      `refresh_stories.py`'s MAX_LEN and `pick_trim_length` targets were dropped 550 → 480 to
      match — verified zero of 51 slides overflow the 13-line panel limit after refresh.
- [x] Fixed a second logo-inference bug: `infer_logo_from_text` ran two separate regex passes
      (capitalized words, then digit-prefixed) and concatenated the results, so a later-appearing
      capitalized team name could win over an earlier digit-prefixed one (e.g. "49ers") purely
      because of regex ordering, not actual text position. Matches are now merged and sorted by
      position so the first team name that actually appears wins.
- [x] Checked the RSS feed for team-specific metadata to use instead of text-scanning — there
      isn't any (`<category>` is generic: "sports", "nfl"; `<source>` is just the publisher, e.g.
      "SB Nation"). The best available signal turned out to be the article title, which reliably
      names the subject team explicitly while the body can mention several teams in passing
      (opponents, comparisons) and pick the wrong one. Added `infer_logo(title, body)`, which
      checks the title first and only falls back to the body if the title has no match.
      Confirmed: a body mentioning "Eagles" before "Cowboys" now correctly resolves to
      `cowboys.png` (from the title) instead of `eagles.png` (old body-only behavior).
- [x] Clarified: logo lookup is local-file-only, no live ESPN fallback — reasonable now that
      `fetch_team_logos.py` pre-downloads all 62 team logos locally ahead of time.
- [x] Header title ("SportsChannel") and clock font bumped 26px/18px → 32px/22px.
- [x] Fixed a real cross-league logo bug: "Giants" and "Cardinals" are nicknames shared by both
      NFL and MLB teams, but logo filenames weren't namespaced by league, so a bare
      `giants.png`/`cardinals.png` silently meant whichever league's download happened to win --
      an MLB Giants story was showing the NFL Giants logo, and same for Cardinals.
      `fetch_team_logos.py` now detects nickname collisions across leagues automatically and
      saves those specific teams as `{league}_{nickname}.png` (e.g. `mlb_giants.png`,
      `nfl_giants.png`); `infer_logo()` checks the league-prefixed filename first, falling back
      to the bare one for everything else. Verified against live data: NFL Cardinals story →
      `nfl_cardinals.png`, MLB Giants/Cardinals stories → `mlb_giants.png`/`mlb_cardinals.png`.
- [x] Replaced a low-quality hand-picked `yankees.png` with a fresh ESPN download.

## Feature: Latest Line + NFL Standings (new)
- [x] **Latest Line**: NFL betting lines (favorite/spread/underdog), shown at the start of the
      NFL section, before NFL stories — mirrors the original broadcast's board. Sourced from
      ESPN's scoreboard `odds` field (favorite team, spread, moneyline provider), grouped by game
      day, paginated at 4 games/screen (was 5 — overflowed the panel once the title got bigger).
      No byline/copyright line, per request. `src/refresh_latest_line.py` → `data/latest_line.json`;
      `buildLatestLinePages` / `drawLatestLineBoard` in `app.js`.
- [x] Follow-up: rows now start below the logo's bottom edge and use the full panel width there
      (same two-zone pattern as story-slide wrapping), instead of staying narrow the whole board
      and cramping longer team names. "LATEST LINE" title switched from Consolas to the same
      pixel font as everything else (`PxPlusIBMVGA8`) and bumped to a dedicated 44px
      `BOARD_TITLE_FONT`. "POINTS" column header abbreviated to "Pts".
- [x] **NFL Standings**: replicates the MLB standings board for NFL's 8 divisions (AFC/NFC ×
      East/North/South/West), including a Ties column MLB doesn't have. Defaults to the generic
      `nfl.png` badge (no AFC/NFC-specific art yet, unlike MLB's AL/NL split).
      `src/refresh_nfl_standings.py` → `data/nfl_standings.json`. `drawStandingsBoard` reworked
      to take a single `logos` object (`{mlb, al, nl, nfl}`) instead of positional args, and
      switches its column layout/badge based on `page.sport`.
- [x] Follow-up: NFL standings columns changed to W, L, T, PCT — GB dropped (MLB keeps it).
- [x] Retro pixelation for logos: `drawLogoInBox` downscales each logo to a tiny offscreen
      canvas once (`PIXELATE_RESOLUTION`, started at 40px, backed off to 80px after initial
      pass looked too blocky), cached per image, then draws that upscaled with
      `imageSmoothingEnabled = false` — genuine blocky pixels, not a blur filter. Applies
      everywhere team/league logos render via `drawLogoInBox` (story slides, standings,
      probables). The header wordmark (`sportschannel.png`) is drawn through its own separate
      `drawImage` call in `drawHeader`, not `drawLogoInBox`, so it stays smooth (it's network
      branding, not a team logo). `probable.png` explicitly opted out (`pixelate: false` param)
      — stays smooth per request.
- [x] Rotation updated to a full NFL block mirroring the MLB block: title card → headlines →
      [MLB: probables → stories → standings] → [NFL: latest line → stories → standings] → loop.
      Both NFL board types share the existing `"nfl"` seasonal gate from `league_seasons.py`.

## Feature: On This Day (sports history fact) (new)
- [x] Real sourced facts, not GPT-generated — scrapes `onthisday.com/sport/events/{month}/{day}`
      for today's date. That page has two content tiers: "highlighted" entries (site-curated,
      each with a photo — a real notability signal) and plain list entries. Both are parsed via
      regex (`src/refresh_history.py`).
- [x] Pick logic: score = +1 if highlighted, +5 if the text names an unmistakably famous athlete
      (`FAMOUS_ATHLETES` — Ruth, Ali, Jordan, etc., a deliberately short tie-breaker list, not a
      full database), highest score wins, ties broken randomly. Filtered to `year >= 1929`
      (`MIN_YEAR`) — pre-1929 trivia (Victorian cricket records, etc.) doesn't fit the vibe.
      Verified: for a date with a Babe Ruth 600th-home-run entry available, that's exactly what
      both signals converge on.
- [x] `data/history.json` → `{"date_label", "fact": {"year", "text"}}`. Not MLB/NFL-specific, so
      it sits outside those blocks: title card → headlines → **On This Day** → **Birthdays** →
      MLB block → NFL block → loop. `buildHistoryPage` / `drawHistoryBoard` in `app.js`; badge is
      `media/logos/history.png`.
- [x] Follow-up: reworked layout to a tall logo in the **left** column, flush with the panel's
      bottom edge (was the standard right-side square box). Factored into shared
      `drawLeftColumnLogo` / `leftColumnTextStartX` helpers (`LEFT_LOGO_BOX`, 260×320) since the
      Birthdays board (below) reuses the exact same treatment. Pixelation dialed down for this
      one specifically (`HISTORY_LOGO_PIXELATE_RESOLUTION = 200` vs the default 80) — "only
      slightly" blocky per request, since `drawLogoInBox`/`getPixelatedLogo` now accept a
      resolution override.

## Feature: Today's Sports Birthdays (new)
- [x] Same source and approach as On This Day — `onthisday.com/sport/birthdays/{month}/{day}`
      (`src/refresh_birthdays.py`). Critical filter: the source list includes people regardless
      of whether they're alive (deceased entries are marked "(d. YYYY)"); those are excluded
      entirely, since a birthday board can't say a dead person "turns 56".
- [x] Filtered to `year >= 1980` (`MIN_BIRTH_YEAR`) — keeps it to current-ish athletes. Picks up
      to 2 people (`MAX_PEOPLE`), scored toward the major US sports this app already covers
      (NFL/MLB/NBA/NHL keywords) over more obscure ones (cricket, rugby) the source site also
      carries.
- [x] `data/birthdays.json` → `{"date_label", "people": [{"name", "desc", "age"}]}`.
      `buildBirthdaysPage` / `drawBirthdaysBoard` in `app.js`; badge is `media/logos/birthday.png`.
      Uses the same left-column-logo, flush-bottom, wrapped-text treatment as On This Day.
- [x] Follow-up: `LEFT_LOGO_BOX` bumped ~30% bigger (260×320 → 338×416, shared by On This Day and
      Birthdays), and Birthday's pixelation cut ~50% (`BIRTHDAY_LOGO_PIXELATE_RESOLUTION = 160`
      vs the default 80) — verified no text overflow or overlap with the title after either change.

## Feature: Sports Trivia (new)
- [x] Real curated Q&A, not GPT-generated — [Open Trivia DB](https://opentdb.com)'s Sports
      category (id 21), a free public API, no key needed. `src/refresh_trivia.py` →
      `data/trivia.json` (`{"question", "answer", "type"}`).
- [x] Presentation: question shows first, answer reveals after `TRIVIA_REVEAL_DELAY` (7s), card
      stays up `TRIVIA_DURATION` (16s) total — matches the retro feel better than showing both at
      once or listing all multiple-choice options.
- [x] Same left-column-logo/flush-bottom/wrapped-text treatment as On This Day and Birthdays, but
      with two badges that swap on reveal: `media/logos/question.png` while the question is up,
      `media/logos/answer.png` once the answer appears.
- [x] Sits with the other general (non-league-specific) cards: title card → headlines → On This
      Day → Birthdays → **Sports Trivia** → MLB block → NFL block → loop.
- [x] Follow-up: trivia/question/answer badge pixelation matched to Birthdays
      (`BIRTHDAY_LOGO_PIXELATE_RESOLUTION` instead of the sharper default).

## Feature: League Quote (new)
- [x] Shown once **after each league's block** (after MLB standings, after NFL standings) — not
      a general card like the others above, since it's tied to a specific league.
- [x] Real athlete/coach quotes, not GPT-generated — scrapes Goodreads' quote-tag pages
      (`goodreads.com/quotes/tag/baseball`, `.../football`; "football" there is dominated by
      American football, not soccer). `src/refresh_quotes.py` → `data/quotes.json`
      (`{"quotes": {"mlb": {...}, "nfl": {...}}}`).
- [x] Pick logic: the tag pages mix genuine athlete quotes (Babe Ruth, Vince Lombardi) with
      loosely-tagged literary/commentary quotes that just happen to share the tag (a humor
      columnist riffing on football, etc.) — a "sports" co-tag turned out **not** to correlate
      with quote quality (checked: Lombardi/Manning/Rice entries had no "sports" co-tag, a noisy
      Dave Barry one did). Instead uses a curated per-league famous-name list
      (`FAMOUS_BY_LEAGUE`, same pattern as `refresh_history.py`'s `FAMOUS_ATHLETES`) to prefer a
      real sports-figure quote when one's in the fetched batch; falls back to random pick
      otherwise — "related to the league if possible," not guaranteed. Verified live: MLB → Babe
      Ruth, NFL → Lou Holtz, both real famous-name matches.
- [x] Same left-column-logo/flush-bottom treatment as the other general cards; badge is
      `media/logos/quote.png`. `buildQuotePage` / `drawQuoteBoard` in `app.js`.

## Feature: Section Intro ("FOOTBALL / COMING UP:") (new)
- [x] One shown right before each league's block starts — before MLB probables, before NFL
      Latest Line. No new data source needed: headlines are pulled straight from that league's
      own `mlbSlides`/`nflSlides` (already in memory), using the same `title` field the Headlines
      board reads — a live preview of what's actually coming up in this pass through the
      rotation, not a separately-fetched/curated list. Up to 4 headlines
      (`SECTION_INTRO_MAX_HEADLINES`), de-duplicated.
- [x] Centered big title (sport name) + "COMING UP:" subtitle, then a left-aligned "- headline"
      bullet list reusing `wrapHeadline`'s prefix/continuation-indent wrapping (same mechanism as
      the Headlines board's ".. headline" bullets, different prefix). No side logo — full-width
      layout, distinct from the other general cards' left-column-logo treatment.
      `buildSectionIntroPage` / `drawSectionIntroBoard` in `app.js`.
- [x] Follow-up: added a horizontal separator rule above and below the sport-name title.

## Feature: Consistent line-by-line reveal across all board types
- [x] Story slides always had a "typewriter" reveal (one line every `LINE_DELAY`); every other
      board type (probables, standings, latest line, on this day, birthdays, trivia, quote,
      section intro, headlines) drew its full content immediately every frame. Made consistent
      throughout the app.
- [x] Added `makeWriter(linesToShow)` — a shared `write(text, x, y)` closure that only actually
      calls `ctx.fillText` for the first `linesToShow` calls made against it, used wherever one
      `fillText` call == one visual line. Added `makeLineGate(linesToShow)` as a variant for rows
      that span several `fillText` calls on one line (e.g. a standings row's Name/W/L/PCT
      columns) — caller checks `shouldShow()` once per row and draws all of that row's columns
      itself, so the row reveals as a single step instead of its columns revealing one at a time.
- [x] Trivia's answer reveal now has its **own** independent line-by-line pace, timed from the
      reveal moment (not overall elapsed) — the question fully reveals first, then a fresh
      typewriter effect plays for the answer once it appears.
- [x] Decorative/structural elements (table row background highlights, logos, the section intro's
      separator rules, the headlines box border) stay immediately visible — only the *text*
      reveals progressively, keeping the layout's shape visible right away while content types in.
- [x] Verified via direct pixel-count checks (not just "no errors"): probables/standings/trivia
      all show a strictly increasing amount of rendered text as `linesToShow` increases from 0 to
      full, confirming the reveal actually works rather than silently no-op'ing.

## Fix: MLB Probables showing yesterday's finished games
- [x] Root cause: `refresh_probables.py` called ESPN's scoreboard with no `dates` param, relying
      on ESPN's own ambiguous "current day" rollover, which lags behind the real calendar date for
      a while after midnight. Confirmed live: ESPN's default response was still serving Aug 11's
      `STATUS_FINAL` games well into Aug 12, and those exact matchups matched what was stuck in
      `probables.json`.
- [x] Fixed by requesting today's date explicitly (`dates=YYYYMMDD`) and filtering to
      `STATUS_SCHEDULED` games only (a second latent bug — there was no status filter at all
      before, so even a correctly-dated response could include already-finished games).
      `refresh_latest_line.py` already pinned an explicit date range and was unaffected;
      `ticker.py` doesn't pin one either but that's reasonable for a ticker (recent scores are
      still relevant content), so left as-is.

## Fix: Story logo inferred from text GPT later trimmed away
- [x] Found via a live screenshot: a Derek Carr/UCLA story showed the NHL **Boston Bruins** logo.
      Root cause: `infer_logo()` ran on the raw pre-GPT article text in `build_slides_from_news()`,
      but the raw article's closing sentence mentioned "the Bruins' offensive staff" — **UCLA's**
      own nickname, not the NHL team — and that sentence never survived GPT's cleaning into the
      actual displayed body. The bug is a pre-existing pipeline-ordering issue (logo inferred
      before cleaning, not after), only newly *visible* now that `bruins.png` exists as a real
      logo file from the NHL team-logo download above.
- [x] Fixed by re-inferring the logo in `clean_slides_with_gpt()` from each slide's final cleaned
      body (the text actually shown), not the raw pre-GPT text — title-based matching (checked
      first, unaffected) still takes priority. Continuation slides (empty title, "(cont)" body)
      inherit their parent slide's logo rather than being independently re-inferred from their own
      fragment, avoiding a two-part story's logo flipping between its own two cards.
      Verified: re-running inference against the existing cleaned dataset changed 24 of ~108
      slides' logos (mostly cases where a body mentioned an opponent/other team in passing that
      GPT's trim had already dropped); the Derek Carr slide now correctly falls back to no
      team-specific logo (generic `nfl.png`) since no real team is named in what's displayed.

## Fix: Web music volume normalization never actually applied
- [x] The pygame desktop app already had two-pass ffmpeg loudnorm normalization
      (`normalize_track_lufs` in `main.py`), but the web player was just playing the raw
      `media/music/` files directly — never wired up.
- [x] While building the fix, found the normalization code had **always been silently broken**,
      even in the desktop app: it read `stats['measured_I']`/`measured_TP`/etc. from ffmpeg's
      loudnorm measure-pass JSON, but this ffmpeg build (9.0) actually reports
      `input_i`/`input_tp`/`input_lra`/`input_thresh`/`target_offset` — the wrong keys raised a
      `KeyError` caught by a bare `except`, which silently fell back to the un-normalized file
      every time. Fixed in both `main.py` and the new batch script below.
- [x] Added `src/normalize_music.py` — batch-normalizes every track in `media/music/` into
      `media/music_normalized/` (content-hash-keyed filenames, skips already-normalized files on
      re-run) and writes `web/music_manifest.json` pointing at the normalized names.
      `app.js`'s `playCurrentTrack()` updated to load from `music_normalized/`. Ran successfully:
      21/21 tracks normalized, 0 failures. Verified a normalized track actually loads and plays
      in-browser (175.7s duration).

## Feature: Score Results ("Monday's NFL Result") (new)
- [x] One card per league, showing the most recent completed day's final scores, inserted right
      after that league's Section Intro (before Probables/Latest Line). Multiple finals stack on
      one card (paginated at 4 games/screen, same density as Latest Line), rather than one card
      per game.
- [x] `src/refresh_score_results.py` walks backward day-by-day (up to 10 days) from today looking
      for the most recent date with at least one `STATUS_FINAL` game — "yesterday" isn't always
      right, confirmed live during this preseason gap: NFL's most recent finals were a full week
      back, while MLB had 15 the very next day. `data/score_results.json` →
      `{"results": {"nfl": {"day_label", "games": [...]}, "mlb": {...}}}`.
- [x] Reuses the standard right-side logo column (generic `nfl.png`/`mlb.png`, not the tall
      left-column treatment) and the row-highlight pattern from Probables/Latest Line — two
      highlighted rows per game (away name + score, home name + score, score right-aligned).
      `buildScoreResultsPages` / `drawScoreResultsBoard` in `app.js`.

## Fix: Off-season content reduction
- [x] News stories: `refresh_stories.py` now caps each league at `OFFSEASON_MAX_PER_SPORT` (10)
      instead of the normal `MAX_PER_SPORT` (default 40) when that league is outside its
      `league_seasons.py` `ACTIVE_MONTHS` window, rather than fetching the same volume year-round.
- [x] Latest Line: previously had no seasonal gate at all (unlike Standings/Probables, which
      already checked `is_mlb_season()`/`active_leagues()`) — it happened to render nothing
      off-season anyway since ESPN naturally returns no scheduled+odds games, but still made the
      live fetch every refresh. `refresh_latest_line.py` now checks `"nfl" in active_leagues()`
      first, matching the Standings/Probables pattern, and records an explicit `in_season` flag.
- [x] Confirmed Standings (`refresh_standings.py`, `refresh_nfl_standings.py`) and Probables
      (`refresh_probables.py`) already had correct seasonal gates from when those features were
      first built — no changes needed there.

## Feature: Game-recap prioritization (news_feed.py)
- [x] Bubble game-recap-style stories ("X beat Y 5-2") to the front of each league's feed before
      truncating to `max_per_sport`, so recaps aren't crowded out by analysis/opinion/preview
      pieces that happened to publish more recently.
- [x] First pass checked the full article body and was far too loose — nearly every baseball
      article mentions *some* score/W-L record in passing, so ~everything matched (verified: 10/10
      sampled MLB items flagged true, including "White Sox stats you probably haven't thought
      about"). Tightened to require **both** the score-shaped number ("4-1") and a recap keyword
      to appear specifically in the **title**, not the body — real recap headlines put them right
      next to each other ("...to 4-1 victory over Astros", "A's Blown Out By Rays 12-4"), while a
      preview like "Tigers seek series-clinching win over Guardians" has the keyword but no score
      digits and now correctly excludes.
      Verified against live data: MLB recaps (SF Giants 4-1 victory, Astros 4-1 Loss, Brewers
      hammered 11-2, A's Blown Out 12-4) correctly lead the order; NFL had zero recaps available
      (preseason games just starting this week) and zero false positives — heuristic leaves order
      unchanged when nothing qualifies, doesn't force a match.

## Feature: Title Card + Headlines Board (new)
- [x] **Title card**: `media/logos/titlecard.png` shown full-canvas (covers header/panel/ticker
      entirely) as the very first item every time the rotation loops, for `TITLECARD_DURATION`
      (6s). `drawTitleCard` in `app.js`.
- [x] **Headlines board**: card two, right after the title card. Sourced for free from data
      already being parsed — `news_feed.NewsItem` now captures each RSS item's `<title>`
      (previously only used for the fantasy-football filter, then discarded), which
      `refresh_stories.py`'s `build_headlines()` collects into `data/headlines.json`
      (de-duplicated, ordered by `LEAGUE_PRIORITY`). Rendered as a bordered box of
      `".. <headline>"` lines with wrapped continuations indented to align.
- [x] Follow-up: capped to exactly 2 headline cards (`HEADLINES_MAX_PAGES`), fitting up to 7
      headlines per card (`HEADLINES_MAX_PER_PAGE`) based on actual wrapped-line height rather
      than a flat count — remaining headlines beyond what fits in 2 cards are simply not shown,
      not paginated through in full.
- [x] **League priority reorder**: MLB is now the priority league. Full rotation order is
      title card → headlines → AL probables → NL probables → MLB stories → 6 division
      standings → NFL stories → (loop). `LEAGUE_PRIORITY = ["mlb", "nfl"]` in
      `refresh_stories.py` drives the headlines ordering; `app.js`'s `items` array construction
      mirrors the same MLB-block-then-NFL-block order.

## Phases 4–7 — Deployment ✅ done (superseded this plan)
The original plan below assumed a `public/` build directory and a bare cron job. What actually
shipped (2026-08-12) differs in the details but accomplishes the same goal — full step-by-step
instructions live in `deploy/DEPLOY.md`, not repeated here:
- No `public/` directory — the repo root deploys directly to `/opt/sportschannel` on the server
  (Rocky Linux 9.8, `192.168.0.219`), with `web/`/`data/`/`media/` served in place by nginx
  (port 8080, no domain yet) rather than being copied into a separate build output folder.
- Two systemd timers instead of one cron job: `sportschannel-refresh.timer` (daily 8am — git
  pull, dependency install, all refresh scripts) and `sportschannel-ticker-refresh.timer` (every
  15 minutes, ticker only — see the Ticker feature entry below).
- `OPENAI_API_KEY`/`SPORTSDATAIO_API_KEY` live in a server-side `.env` (not in git), loaded via
  each systemd service's `EnvironmentFile=`.
- Refresh runs are inspectable via `journalctl -u sportschannel-refresh.service` /
  `journalctl -u sportschannel-ticker-refresh.service`, rather than a custom log file.
- Same push-then-pull workflow as boston311, confirmed working end-to-end.
- Real deployment-specific bugs hit and fixed along the way: Python 3.10+ syntax breaking on the
  server's older Python (missing `from __future__ import annotations` in `ticker.py`), a missing
  `openai` dependency, Rocky/RHEL's `conf.d` nginx layout differing from Debian's
  `sites-available`, root-owned files from `scp` landing unreadable by nginx's worker process,
  and an SELinux mislabel that blocked `venv/bin/python` from executing after a too-broad
  `httpd_sys_content_t` fix for nginx. All documented in `deploy/DEPLOY.md`.

## Idea: GitHub Pages mirror (not started)
If wanted later, publish the same static output to a `gh-pages` branch via a GitHub Action. Lower
priority than the Linux server target since Pages can't run the refresh job itself — it would
need to pull already-generated JSON from somewhere.

## Minor: Ticker separator fix
- [x] Ticker text now leads with a `"   |   "` separator before the "LIVE SCORES BROUGHT TO YOU
      BY ESPN" credits line, so the loop (the ticker draws the same text twice back-to-back for a
      seamless scroll) has proper spacing where the last item wraps back around to the credits.

## Feature: Ticker refetches every 2nd lap through the rotation
- [x] Previously `data/ticker.json` was loaded once at page load and never again for the lifetime
      of the browser tab — on a long-running display, the ticker would show the same scores
      forever even after the server-side data refreshed. `app.js` now counts full laps through the
      `items` rotation (`lapCount`, incremented when `currentIndex` wraps back to 0) and refetches
      ticker.json every `TICKER_REFRESH_EVERY_N_LAPS` (2) laps via a `loadTicker()` helper shared
      with the initial load. Async, non-blocking — the ticker keeps scrolling its current text
      until the refetch resolves.
- [x] That client-side refetch only surfaces genuinely new data if the *server-side* copy has also
      changed — which it wasn't doing more than once a day (the full `refresh_all.sh` timer). Added
      a second, separate systemd timer (`deploy/sportschannel-ticker-refresh.service`/`.timer`)
      that runs *only* `refresh_ticker.py` every 15 minutes — no `git pull`, no dependency install,
      no GPT calls, just an unauthenticated ESPN scoreboard fetch, so it's cheap enough to run that
      often without piling onto the daily job. See DEPLOY.md step 6b.

## Phase 9 — Desktop executable
- [ ] Package `main.py` + deps with PyInstaller into a standalone Windows `.exe`.
- [ ] Bundle fonts/logos; decide whether music ships in the executable or is pulled from a
      `media/` folder alongside it (keeps `.exe` size down).
- [ ] Attach as a GitHub Release artifact.

## Idea: Reduce OpenAI API cost for article cleaning (not started)
Currently `gpt_cleaner.py` calls the OpenAI chat completions API (`gpt-4.1-mini`) once per
article, every time `refresh_stories.py` runs — now daily via the 8am systemd timer (see
`deploy/refresh_all.sh`), so cost is bounded today, but would scale linearly if refresh cadence
is ever increased (Phase 5's "1-2 hours" idea) or more leagues/articles are added. Flagged by the
user as worth addressing before that happens, not urgent yet.

- [ ] Investigate whether a subscription-based ChatGPT CLI/tool (flat monthly cost) could replace
      pay-per-token API calls for this specific use case — needs research into what's actually
      available/supported for programmatic use (most consumer ChatGPT subscriptions don't offer
      a sanctioned CLI/API path; may end up ruled out).
- [ ] Cache cleaned output keyed by article content hash, so unchanged articles aren't re-sent to
      GPT on every refresh — likely the highest-value, lowest-risk fix regardless of the above,
      since most articles are probably unchanged between consecutive refreshes.
- [ ] Consider a cheaper/smaller model tier if quality holds up (`gpt-4.1-mini` is already the
      "mini" tier — check if `gpt-4.1-nano` or similar is viable).
- [ ] Consider batching multiple articles into one API call instead of one call per article, to
      cut fixed per-request overhead.
- [x] Source-pull char cap (done as part of the text-fitting revamp below): raw article text is
      now trimmed to at most two cards' worth of characters before ever being sent to GPT, instead
      of sending up to 6000 raw chars for output that could never exceed ~950 anyway. Doesn't
      reduce call *count*, but cuts input-token cost on longer articles.

## Feature: Text fitting revamp — capacity, `(cont)` placement, drop `<<<INDENT>>>` markers ✅ done
Triggered by two live screenshots: one showing a card using only 9 of the panel's ~13 lines
(obvious wasted space), another showing a literal `<<<INDENT>>>` token leaked into the displayed
text ("series.<<<INDENT>>>My Mariners vs. Yankees predictions...") — the fragile hand-encoding
scheme finally breaking in practice, not just in theory, exactly as an earlier roadmap note
predicted ("already happened once with the `\n\n` → `\n` rule").

**Root cause of the wasted space:** the old pipeline pre-split raw article text at a fixed
480-char threshold *before* GPT ever cleaned it, then told GPT to clean each already-shrunk
fragment while staying at-or-under its own (already small) length — GPT was structurally never
given room to use the panel's real capacity, and a hard "2 paragraphs / 2 sentences" cap in the
system prompt throttled output further regardless of the character limit passed in.

- [x] Measured the panel's true capacity empirically in-browser (not guessed from pixel math):
      ~477 chars for realistic article prose at the current 36px font (13 lines: ~5 narrow lines
      beside the logo, the rest full-width). `PANEL_CHAR_CAPACITY = 460` in `refresh_stories.py`
      (small safety margin under the measured max).
- [x] Reordered the pipeline: `build_slides_from_news` no longer pre-splits raw text at all (one
      slide per fetched item, raw body kept whole). `clean_slides_with_gpt` now cleans the *full*
      article with a generous `CLEAN_MAX_CHARS` budget (2x `PANEL_CHAR_CAPACITY`) so GPT compresses
      to how much substance the source actually has, then splits the *cleaned* result into a
      primary card (≤`PANEL_CHAR_CAPACITY`) plus an optional "(cont)" card only if the leftover is
      substantial (`MIN_CONTINUATION_LEN = 200`, raised from an initial 40 after the user flagged
      that a `(cont)` card shouldn't exist just because a *little* text was left over — small
      leftovers are dropped, not spun into a near-empty second card).
      Verified live: primary cards now land mostly in the 400-460 range (vs. previously being
      capped well below capacity by construction), continuations only appear with 280-500+ chars
      of real leftover content, and small excess (45-198 chars) is correctly dropped rather than
      creating a sparse `(cont)` card.
- [x] Found and fixed a related bug during this work: the continuation card's length wasn't itself
      bounded by `PANEL_CHAR_CAPACITY` (only the primary card's split was capped), so a
      continuation could in rare cases overflow its own panel. Now re-split to fit if needed.
      Also hardened `split_at_natural_break`'s fallback (no punctuation found before the cap) to a
      bounded forward search instead of an unbounded one, closing a latent edge case inherited
      from the original splitting logic.
- [x] Dropped the `<<<INDENT>>>` marker scheme entirely, per the user's follow-up ("those indents
      need to go too") once the leak was visible. `gpt_cleaner.py`'s system prompt no longer asks
      GPT to hand-encode indentation or cap paragraphs at a fixed count — it separates paragraphs
      with a plain `\n` at natural topic shifts and is told to use the full character budget the
      source supports. `app.js`'s `wrapTextAroundOverlay` now derives indentation purely from real
      paragraph boundaries (every paragraph's first rendered line is indented, no marker needed)
      and returns `{text, indent}` objects instead of marker-prefixed strings; `drawSlideText`
      updated to match. Verified across all 55 slides in a live test refresh: zero indent-marker
      leaks, max line count 12 (within the 13-line panel), zero overflow.
- [x] Removed now-dead code as part of the rewrite: `pick_trim_length`, `mark_first_line`,
      `_maybe_merge_or_append`, `MERGE_CONTINUATION_MAX_LEN`, and three pre-existing no-op
      functions (`indent_paragraphs`, `add_paragraph_breaks`,
      `linefeed_and_indent_after_first_sentence`) that were leftover cruft from an earlier version
      of the formatting scheme.

## Feature: Player headshots for player-focused stories ✅ done
For stories about a specific individual rather than a team (feature pieces, injury updates,
transactions), use the player's real ESPN headshot instead of a generic league logo. Scoped
deliberately small per the user's request ("only need this for a few cards each section").

- [x] `find_player_headshot()` in `refresh_stories.py` queries ESPN's public search API
      (`site.web.api.espn.com/apis/search/v2?type=player`), which returns a direct headshot image
      URL for a confirmed player match — verified live it correctly excludes non-players (a real
      coach name, "Bob Chesney", returns no player result) and cross-sport false positives (a
      search for "New York" alone matched an unrelated MMA fighter with no league tag, filtered
      out by requiring `defaultLeagueSlug` to match the story's own league).
- [x] Candidate names are extracted from the title/body using the same overlapping-pair regex
      technique as the two-word team-nickname fix above, reused for "Firstname Lastname" person
      names instead. Downloaded headshots cache locally under `media/logos/players/{athlete_id}.png`
      (gitignored like all other media) so repeat mentions of the same player don't re-download.
- [x] Capped at `MAX_PLAYER_PHOTOS_PER_LEAGUE = 2` per refresh — resets each run, not persisted,
      naturally keeping this to "a few cards per section" and bounding live API calls.
- [x] **Priority ordering fix found via a live screenshot**: an article titled "Remembering Don
      Nelson" showed the Celtics team logo instead, because the body's opening photo caption
      mentioned "Boston Celtics" and the original logic only tried a player photo when *no* team
      matched anywhere (title or body). Reordered to: team-in-title → player-in-title →
      team-in-body → player-in-body, so a title that clearly names a person as the subject wins
      over a team only mentioned in passing in the body. Verified live with a case where a
      headshot was actually available (title names a current player, body opens with an unrelated
      team mention) that the reordering does change the outcome correctly.
- [x] That specific Don Nelson example still can't show his actual face even with the fix, though
      — checked ESPN's data directly: his player record exists (NBA, Milwaukee Bucks) but has no
      headshot image at all, since he played in the 1960s-70s, before ESPN's photo coverage. Falls
      back to the team logo in that case, which is the correct graceful degradation for a missing
      photo, just not literally his face.
- [x] No `app.js` changes needed at all -- `getLogo()` already loads whatever relative path is in
      the `logo` field, so `"players/<id>.png"` just works like any other logo.
- [x] **Cropped to a head close-up per the user's follow-up request** ("any way to get only a head
      shot?"). ESPN's headshots are consistently framed as head-and-shoulders portraits with the
      face centered in the upper-middle of the image, so a fixed-ratio crop gets a genuine
      close-up of just the head/face without needing real face detection. `_crop_to_head()` in
      `refresh_stories.py`, applied once at download time (cached cropped, not re-cropped on every
      run). Added `Pillow` to both `requirements.txt` (was already commented out as "optional,
      enable later") and `requirements-server.txt`.
- [x] First-pass ratios (top 62% of height, 12% side trim) cut off the chin on some photos and
      left too much empty space around the face. Tuned per direct feedback ("should be full head a
      little shoulders is ok, and zoom in a bit") to top 78% / 20% side trim -- verified visually
      against two different real photos (football, hockey), both showing the full head plus a
      little cap/shoulder, noticeably more zoomed in than the first pass.
- [x] Investigated one screenshot that looked like a mismatched cartoon avatar on a multi-player
      betting-picks story -- turned out to be a real, correctly-matched photo of the actual named
      player (a distinctive mustache read as "cartoonish" at the small pixelated display size, not
      an actual matching bug). No fix needed; confirms the matching logic was already working
      correctly here.
- [x] **Real bug found via a third screenshot**: a jersey-number-history story titled "The History
      Of Jersey #49" showed the On This Day board's `history.png` badge as its "team logo" --
      several non-team badge/UI files (`history.png`, `birthday.png`, `answer.png`,
      `question.png`, `probable.png`, `quote.png`, etc.) live in the same `media/logos/` directory
      as real team logos and are also plain English words, so a story whose title/body happened to
      contain one of those words would get that board's badge purely by vocabulary coincidence.
      Added `NON_TEAM_LOGO_FILES` to `_logo_for_word()` to exclude them from word-match lookups.
      Verified live: the jersey-history story now correctly resolves to `bluejackets.png` (the
      actual team it's about) instead of the coincidental `history.png` match.
- [x] **Dedup across stories**: two separate NFL preseason roundup articles both mentioned the same
      rookie QB, so his photo ended up on two unrelated card sets instead of spotlighting two
      different people. `find_player_headshot()` now takes a `used_athlete_ids` set threaded
      through the whole `clean_slides_with_gpt` refresh run -- an already-claimed athlete is
      skipped (falls through to the next name candidate, or ultimately a generic logo) rather than
      reused. Verified live: every player photo now maps to exactly one story.
- [x] **Mid-word hyphen cuts fixed**: `split_at_natural_break` treated a bare "-" as a valid clause
      break, which also matched a hyphen glued inside a compound word like "hardest-throwing" or
      "two-time" (no space on either side, not a real boundary). Spotted live: a card ended
      "...one of the hardest-" mid-word. Break patterns now require a trailing space (". ", ", ",
      " - "), so only a genuine standalone dash used as punctuation counts, not a compound-word
      hyphen. Verified against the exact failing text (splits at the next comma instead) and
      confirmed zero mid-word hyphen cuts across a full fresh 58-slide dataset.

## Feature: Full data auto-refresh every lap (not just the ticker)
Previously only the ticker refreshed periodically (every 2 laps, see below) -- everything else
(stories, standings, quotes, headlines) was loaded once at page load and held for the life of the
browser tab, requiring a manual reload to see anything new. Requested so a long-running display
doesn't need a manual reload at all.

- [x] Considered swapping the rotation array at the exact title-card boundary, but the user
      suggested a simpler, safer alternative: a short blank card at the very end of every lap,
      used as a fixed point to kick off the refresh. Implemented that way instead.
- [x] `buildRotation()` -- the full data-loading + rotation-array-construction logic, extracted out
      of `main()` into its own reusable async function -- gets called again each time the rotation
      reaches a new `{ type: "refresh" }` card appended at the end of every built rotation.
      `prepareItem()` kicks off the rebuild in the background (and reloads the ticker in the same
      pass, which supersedes the ticker's old separate every-2-laps cadence -- removed the
      now-redundant `lapCount`/`TICKER_REFRESH_EVERY_N_LAPS` logic). `frame()` applies the result
      only when actually leaving the refresh card, so the live `items` array is never swapped
      mid-frame -- if the fetch somehow isn't done by then, it just tries again next lap rather
      than blocking.
- [x] No re-fetching of logos/images -- those are cached by filename and rarely change, so only
      the JSON data files reload, keeping each cycle cheap (small local fetches).
- [x] Verified live: cycled through 250+ auto-advances and confirmed `stories_cleaned.json` (and
      the rest of the data set) fetched well beyond the two initial page-load calls, with zero new
      console errors introduced.

## Follow-up: text-fitting refinements (same session)
- [x] **Quote board character art bumped ~15% bigger** (`drawLeftColumnLogo` gained an optional
      `boost` param, same overscale-past-the-box pattern `drawLogoInBox` already used elsewhere) —
      scoped to just the Quote board's call, not the shared `LEFT_LOGO_BOX` used by History/
      Birthdays/Trivia too.
- [x] **Split logic was leaving a whole sentence on the table**: spotted via a live screenshot
      where the primary card stopped at "...against the Bears." even though "Shedeur Sanders is
      set to..." was right there in the `(cont)` card. Root cause: `split_at_natural_break` only
      looked *backward* for a break at-or-before the cap, so if the very next sentence crossed the
      cap by even a few characters, it fell back to a much earlier (and shorter) break instead.
      Now also looks forward within `FORWARD_TOLERANCE` (60 chars) from wherever it landed and
      prefers that if found — fits a whole extra sentence instead of leaving ~100+ unused
      characters over a few-character overrun. `PANEL_CHAR_CAPACITY` nudged 460 → 475 (closer to
      the true ~477 measured max) since the forward-tolerance mechanism needed the extra headroom
      to be worth using. Re-verified line-wrap safety after this change: 51/51 slides still fit
      within 13 lines, max observed exactly 13 (using full capacity, zero overflow).
- [x] **Source-pull char cap**: raw article text is now trimmed to at most `CLEAN_MAX_CHARS` (two
      cards' worth, ~950) immediately after fetching, before it's ever sent to GPT — previously raw
      articles up to `MAX_EXCLUDE_LEN` (6000 chars) were sent to GPT in full even though the output
      could never exceed ~950 chars regardless, burning extra input tokens on content guaranteed to
      be discarded. Trimmed at a natural sentence break (reuses `split_at_natural_break`), not a
      hard cut. Verified live: raw lengths that were previously up to 2313 chars now cap out
      around 950-1006.

## Fix: Standings board GB/PTS value overflowing the row highlight
- [x] Spotted via a live screenshot: NL Central's Pirates row showed "16.5" (games behind) with
      its last digit rendered past the blue row-highlight background, onto the plain panel
      background. Root cause: the GB/PTS column sat at a fixed 0.90 fraction of the row width,
      leaving only ~57px before the row rectangle's right edge -- too little for a 4-character
      value like "16.5" (measured 72px at this font).
- [x] Rebuilt all `drawStandingsBoard` column positions from actual measured glyph widths
      (monospace, 18px/char at 36px font) instead of the original eyeballed fractions -- name
      column narrowed (0.50 → 0.44), remaining columns shifted to give the last column real
      breathing room (0.90 → 0.79). Verified the longest realistic team name ("Golden Knights",
      NHL) still clears the name column with margin, and the widest real values (".612", "16.5")
      now render with 50+ px of clearance inside the row highlight.

## Idea: Better news source than Yahoo RSS (not started)
`news_feed.py` currently pulls from Yahoo Sports RSS feeds. User reports a lot of junk still
getting through despite the existing filters (dateline/caption regexes, fantasy-promo stripping,
game-recap heuristics — see Phase 3 and the Game-recap prioritization feature above), suggesting
the feed itself is noisy at the source rather than just needing more filtering downstream.

- [ ] Research alternative sports news sources/APIs (ESPN's own news endpoints? another sports
      RSS feed? a dedicated news API?) and compare actual junk rate against Yahoo's before
      committing to a switch — same "verify against live data" approach used for every other
      data source in this project, not a guess.
- [ ] Decide whether to replace Yahoo outright or add a second source and merge, once a
      candidate is identified.

## Feature: Full NBA/NHL board treatment ✅ done
Mirrors the full MLB/NFL treatment, not just bare story slides. Rotation order is now: title card
→ headlines → On This Day → Birthdays → Sports Trivia → MLB block → NFL block → **NBA block →
NHL block** → loop, each league block being Section Intro → (Score Results/Latest Line/Probables)
→ stories → standings → quote.

- [x] Enabled NBA/NHL feeds in `news_feed.py`'s `SPORT_FEEDS`; added both to `refresh_stories.py`'s
      `per_sport_order` and `LEAGUE_PRIORITY` (`["mlb", "nfl", "nba", "nhl"]`) — this also put them
      on the Headlines board for free, since `build_headlines()` already iterates `LEAGUE_PRIORITY`
      generically. Verified live: both feeds parse correctly (3/3 items each on a spot check).
- [x] Standings: `refresh_nba_standings.py` (W/L/PCT/GB, same shape as MLB — verified live: ESPN's
      NBA standings endpoint returns the identical conference→division→entries structure with
      `wins`/`losses`/`winPercent`/`gamesBehind` stat names) and `refresh_nhl_standings.py` (NHL
      uses a genuinely different column set — verified live the real stat names are
      `wins`/`losses`/`otLosses`/`points`, i.e. the standard W/L/OTL/PTS hockey table, not
      W/L/PCT/GB). `drawStandingsBoard` in `app.js` now branches on `page.sport` for NHL's column
      layout in addition to NFL's existing T-column branch.
- [x] Probables-equivalent: NBA and NHL both use point-spread betting lines like NFL (not MLB's
      pitcher-matchup format), so `refresh_nba_line.py` / `refresh_nhl_line.py` mirror
      `refresh_latest_line.py`'s odds-parsing exactly. `buildLatestLinePages`/`drawLatestLineBoard`
      in `app.js` generalized to take a `sport` tag (title reads "NBA GAMES"/"NHL GAMES", correct
      league badge) instead of being NFL-hardcoded. Not yet spot-checked against a live
      scheduled+odds NBA/NHL game (both leagues are off-season as of this build) — re-verify once
      the season starts, same odds-shape assumption as NFL's working implementation.
- [x] Section Intro and League Quote needed **no app.js changes at all** — both were already
      fully generic (`buildSectionIntroPage`/`drawSectionIntroBoard` take no league-specific logo;
      `buildQuotePage`/`drawQuoteBoard` use one fixed `quote.png` badge for every league), so
      passing `"nba"`/`"nhl"` and new slide data was enough.
- [x] Quotes: added `nba`→"basketball", `nhl`→"hockey" Goodreads tags and `FAMOUS_BY_LEAGUE`
      entries to `refresh_quotes.py`. Checked quote quality live like MLB/NFL originally were:
      basketball's tag is reasonably clean (Jordan, Wooden, Chamberlain mixed with some unrelated
      authors); hockey's tag turned out **dominated by hockey-themed romance novels** (Rachel
      Gibson, Sarina Bowen, Hannah Grace), making the famous-name-first pick logic load-bearing
      there, not just a nice-to-have. Verified live picks: NBA → Michael Jordan, NHL → Herb Brooks
      (added to the famous list after this check — he's the real 1980 "Miracle on Ice" coach, not
      fiction).
- [x] Team logos: added NBA/NHL endpoints to `fetch_team_logos.py` and ran it. Found real new
      cross-league nickname collisions beyond the existing Giants/Cardinals: **Jets** (NFL/NHL),
      **Panthers** (NFL/NHL), **Kings** (NBA/NHL), **Rangers** (MLB/NHL) — all auto-detected and
      saved as league-prefixed files (`nhl_jets.png`, `nfl_jets.png`, etc.) by the existing
      collision-detection logic, no code changes needed. Left over stale bare `jets.png`/
      `panthers.png`/`rangers.png` files from before NHL existed are harmless (unused, since
      `infer_logo()` always knows the story's league and checks the prefixed file first) but could
      be deleted for tidiness later.
- [x] Verified end-to-end in-browser: stepped through 190+ rotation advances with zero console
      errors, confirmed every new data file and team logo (NBA: 76ers/Lakers/Nuggets/Wizards, NHL:
      Sabres/Penguins/Kraken/Canadiens, etc.) loaded 200 OK over the network.

## Feature: MLB score results — winning/losing/save pitcher ✅ done
- [x] ESPN's scoreboard endpoint has no pitcher-decision data; it only exists on the per-event
      summary endpoint (`summary?event=<id>`), one extra request per MLB game. Verified live the
      exact path: `boxscore.players[team].statistics[pitching group].athletes[i].notes` carries
      `{"type": "pitchingDecision", "text": "W, 6-8"}` style entries (also "L, ..." and "S, ...";
      "H, ..." for holds, not used here). `refresh_score_results.py`'s `_fetch_pitching_decisions`
      extracts win/loss/save, skipped entirely for NFL (no equivalent concept, no extra requests).
- [x] `drawScoreResultsBoard` in `app.js` adds a compact "W: ... L: ... SV: ..." line per MLB game
      (wrapped to the column width via `wrapTextToWidth` rather than assumed to fit one line, since
      names/records vary), correctly omitting the save part when a game had none (e.g. a
      complete-game-adjacent finish with no separate closer). Reduced MLB's games-per-screen from
      4 to 3 (`SCORE_RESULTS_GAMES_PER_SCREEN_MLB`) to leave room for the extra line; NFL keeps 4.
      Verified live: real decisions rendered correctly for two same-day MLB finals.

---

## Open questions
- Refresh cadence: 1 hour vs 2 hours — any preference, or start at 1 hour and tune later?
- Ticker leagues: stay NFL-only or expand to NBA/MLB/NHL for the web version?
- Domain/subdomain for the SportsChannel page on the Linux server?
- Should the desktop `.exe` and the web version share one `refresh_stories.py` output, or diverge?
