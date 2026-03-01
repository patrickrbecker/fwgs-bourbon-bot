# FWGS Whiskey Release Monitor

Monitors the Pennsylvania Fine Wine & Good Spirits whiskey release page and sends Discord alerts when new products appear.

## Structure

```
bourbon_monitor/
  __init__.py      - Package entry point
  config.py        - Configuration, constants, logging setup
  browser.py       - Playwright browser manager with stealth
  scraper.py       - Product extraction from FWGS page
  storage.py       - JSON persistence with flicker protection
  notifier.py      - Discord webhook notifications with retry
  main.py          - Main monitoring loop, signal handling
run.py             - Entry point
requirements.txt
.env               - Discord webhook URL (not committed)
```

## Setup

```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure
cp .env.example .env
# Edit .env with your Discord webhook URL
```

## Run

```bash
python run.py
```

## Deploy as systemd service

```ini
[Unit]
Description=FWGS Whiskey Release Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=patbecker-mac
WorkingDirectory=/opt/bourbon-bot
ExecStart=/opt/bourbon-bot/venv/bin/python3 /opt/bourbon-bot/run.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bourbon-bot

[Install]
WantedBy=multi-user.target
```

## Features

- Playwright headless browser with stealth scripts (anti-detection)
- 30-second check interval
- Flicker protection (2-hour cooldown prevents re-notifications)
- Persistent state survives restarts (products.json + state.json)
- Safety checks: skips if 0 products or >50% count drop
- Graceful shutdown on SIGTERM/SIGINT
- Exits after 5 consecutive failures (systemd restarts)
- Discord retry with exponential backoff + rate limit handling
- Error notification throttling (10-minute cooldown)

## Alerts

| Alert | Trigger | @everyone |
|-------|---------|-----------|
| NEW WHISKEY RELEASE! | New product detected | Yes |
| Monitor Started | Service startup | No |
| Monitor Error | Scrape failure | No |
