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

## Phase 4 — Static asset pipeline
- [ ] Pre-normalized `.mp3`s committed/synced to the server (not regenerated per request).
- [ ] Logos + fonts copied into a `public/media/` folder served by nginx.
- [ ] Decide on a `public/` (or `web/`) directory convention separate from the pygame `src/`
      tree, so the two builds (desktop vs web) don't collide.

## Phase 5 — Scheduling on the Linux server
- [ ] Cron or systemd timer: run refresh job every 1–2 hours (exact cadence TBD — cheap to
      change later).
- [ ] Store `OPENAI_API_KEY` / `SPORTSDATAIO_API_KEY` as server-side env vars (or a `.env` not
      checked into git, same pattern as today).
- [ ] Log refresh runs somewhere inspectable (even just a rotating log file) so failures are
      visible.

## Phase 6 — Serving
- [ ] nginx serves the static `public/` directory (HTML/JS/CSS/fonts/logos/audio/JSON).
- [ ] No app server needed for the page itself — it's 100% static files regenerated periodically
      by the cron job.
- [ ] Confirm domain/subdomain and whether it sits alongside boston311 on the same box or gets
      its own vhost.

## Phase 7 — Deployment
- [ ] Same push-then-pull workflow as boston311: push to GitHub, pull on the server.
- [ ] `.gitignore` already excludes venv/media/secrets from the repo (done during the initial
      GitHub publish) — extend as needed for any new `public/` build artifacts if they shouldn't
      be committed either.

## Phase 8 — Optional: GitHub Pages mirror
- [ ] If wanted later, publish the same static `public/` output to a `gh-pages` branch via a
      GitHub Action. Lower priority than the Linux server target since Pages can't run the
      refresh job itself — it would need to pull already-generated JSON from somewhere.

## Phase 9 — Desktop executable
- [ ] Package `main.py` + deps with PyInstaller into a standalone Windows `.exe`.
- [ ] Bundle fonts/logos; decide whether music ships in the executable or is pulled from a
      `media/` folder alongside it (keeps `.exe` size down).
- [ ] Attach as a GitHub Release artifact.

---

## Open questions
- Refresh cadence: 1 hour vs 2 hours — any preference, or start at 1 hour and tune later?
- Ticker leagues: stay NFL-only or expand to NBA/MLB/NHL for the web version?
- Domain/subdomain for the SportsChannel page on the Linux server?
- Should the desktop `.exe` and the web version share one `refresh_stories.py` output, or diverge?
