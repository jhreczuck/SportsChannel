# 🏈 Sportschannel
*A modern re-creation of the Sports Plus Network (1988–1993)*

Sportschannel is a Python-based simulation of the **Sports Plus Network**, a non-interactive, automated sports information service that ran on SportsChannel between 1988–1993.  
This project aims to faithfully recreate the **look, feel, and behavior** of the original broadcast — complete with retro CRT-style graphics, automated headlines, scrolling tickers, and background music.

## 🎯 Goals
- **Authentic presentation:** 4:3 layout, CRT-era color palette, bitmap fonts, line-by-line text rendering.
- **Continuous operation:** Automated cycling of stories, scores, and updates.
- **Dynamic content:** Real-time scores and headlines using modern sports APIs.
- **Background music:** Local `.mp3` playback (with future Spotify integration).

## 🖥️ Visual Design
- Header bar: “SportsChannel” (left) + current time/date (right)
- Content pane: Headline and story text (left) + logo or graphic (right)
- Bottom ticker: continuously scrolling sports scores and static credits
- 4:3 window (default 960×720), bordered in orange with dark gray background

## 🎵 Audio
- Loops local `.mp3` tracks from `media/music/`
- Random shuffle between songs
- Optional future integration with **Spotify API (Spotipy)**

## 📰 Data & Automation
### Phase 1 (Offline Mode)
- Local JSON files (`data/stories.json`, `data/ticker.json`)
- Simulated data for headlines, scores, and ticker text

### Phase 2 (Live Mode)
- API-driven real-time updates from Sportsdata.io, TheSportsDB, MLB Stats API, NHL API, and RSS feeds

**Ticker Format Example**
```
MLB: BOS 4 – NYY 5 F •
NBA: LAL 102 – PHX 99 4:32 4Q •
NHL: PIT 3 – NYR 2 OT •
```

## 📂 Project Structure
```
Sportschannel/
├── src/
├── media/
│   ├── logos/
│   └── music/
├── data/
│   ├── stories.json
│   └── ticker.json
├── requirements.txt
└── README.md
```

## 📦 Dependencies
```
pygame>=2.5
requests>=2.32
python-dotenv>=1.0
# Optional (enable later):
# spotipy>=2.24
# Pillow>=10.4
```

## ⚙️ Setup (Windows + VS Code)
```bash
python -m venv Sportschannel
Sportschannel\Scripts\activate
pip install -r requirements.txt
```

Prepare media folders and add MP3s, PNGs, and JSON data.
