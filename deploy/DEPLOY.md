# Deploying SportsChannel to the Linux server

Target: `192.168.0.219`, deployed to `/opt/sportschannel`, served on port
`8080` (no domain yet). Data refreshes once daily at 8am via a systemd
timer. This mirrors the local Windows dev setup exactly — same relative
paths, same scripts, just running on a schedule instead of by hand.

## 1. Clone the repo on the server

```bash
cd /opt
git clone https://github.com/jhreczuck/SportsChannel.git sportschannel
cd sportschannel
```

## 2. Create the Python venv (server-only deps — no pygame needed)

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements-server.txt
```

## 3. Create `.env`

Not in git (secrets). Create `/opt/sportschannel/.env` with the same values
as your Windows `.env` — see `.env.example` in the repo for the expected
keys (`SPORTSDATAIO_API_KEY`, `OPENAI_API_KEY`, `SPORTSDATAIO_LEAGUE`,
`MAX_PER_SPORT`). Copy the actual values over securely yourself (don't paste
secrets into a chat/AI session) — e.g. `scp` the file directly, or type them
in over SSH.

```bash
nano /opt/sportschannel/.env   # paste in real values, save
chmod 600 /opt/sportschannel/.env
```

## 4. Sync media/ from Windows (run this ON THE WINDOWS MACHINE, not the server)

`media/` is intentionally gitignored (217MB of logos/music/fonts — see the
repo's own notes on why). Run this from a terminal on the Windows machine
that has both the source files and network access to the server:

```bash
rsync -avz --progress \
  "/c/Users/Admin/Documents/APIs/SportsChannel/Sportschannel/media/" \
  root@192.168.0.219:/opt/sportschannel/media/
```

(If Git Bash doesn't have `rsync`, install it via a package like `Git for
Windows`' optional components, or use `scp -r` instead — slower, no
resume/delta support, but works with zero extra setup:
`scp -r "/c/Users/Admin/Documents/APIs/SportsChannel/Sportschannel/media" root@192.168.0.219:/opt/sportschannel/`)

Re-run the same `rsync` command any time you add/change logos or music —
it only transfers what's changed.

## 5. Do a manual refresh once, to confirm everything works

```bash
cd /opt/sportschannel
./deploy/refresh_all.sh
```

Check `data/*.json` files got updated timestamps and look sane (e.g.
`cat data/stories_cleaned.json | head -30`).

## 6. Install the systemd service + timer

```bash
cp deploy/sportschannel-refresh.service /etc/systemd/system/
cp deploy/sportschannel-refresh.timer /etc/systemd/system/
chmod +x /opt/sportschannel/deploy/refresh_all.sh

systemctl daemon-reload
systemctl enable --now sportschannel-refresh.timer

# Confirm it's scheduled:
systemctl list-timers sportschannel-refresh.timer

# Trigger a manual run through systemd (not just the raw script) to make
# sure the service unit itself is wired up correctly:
systemctl start sportschannel-refresh.service
journalctl -u sportschannel-refresh.service -n 50 --no-pager
```

## 7. Install the nginx config

```bash
cp deploy/nginx-sportschannel.conf /etc/nginx/sites-available/sportschannel
ln -s /etc/nginx/sites-available/sportschannel /etc/nginx/sites-enabled/sportschannel
nginx -t
systemctl reload nginx
```

If port 8080 is already in use by something else on this box (it may be,
given boston311 is also hosted here), change the `listen 8080;` lines in
`deploy/nginx-sportschannel.conf` to a free port before copying it in.

## 8. Verify

Open `http://192.168.0.219:8080/` in a browser (redirects to
`/web/index.html`). Should look identical to the local dev version.

## Updating later

Code changes: `git pull` in `/opt/sportschannel`, no restart needed (nginx
serves static files directly, no running app process to restart) — the
browser just needs a reload.

Media changes: re-run the rsync command from step 4.

Dependency changes: `./venv/bin/pip install -r requirements-server.txt`
again after a `git pull` that touched `requirements-server.txt`.
