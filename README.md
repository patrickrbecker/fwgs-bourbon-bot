# FWGS Bourbon Monitor Bot

Automated monitors for Pennsylvania Fine Wine & Good Spirits (FWGS) bourbon/whiskey pages. Sends Discord alerts for new products, status changes, and hot items.

## Versions

### `bourbon_monitor_playwright.py` (Latest - Recommended)
Fast Playwright + JavaScript extraction version.

**Features:**
- Playwright browser automation (fast, reliable)
- Single JavaScript call extracts all products (~1 second)
- Status tracking: available, coming_soon, lottery, out_of_stock
- Status change alerts (NOW AVAILABLE FOR PURCHASE!)
- Hot item tracking (alerts when stock dropping fast)
- Direct product URL fetching
- Discord webhook notifications
- 30-second check interval

**Requirements:**
```bash
pip install playwright requests
playwright install chromium
```

### Legacy Versions
- `bourbon_monitor_fixed.py` - Selenium version with status tracking
- `fwgs_bourbon_monitor_enhanced-6.py` - Original Selenium + email alerts

## Configuration

Edit the CONFIG section in the script:
```python
CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 30,  # seconds
    'discord_webhook_url': 'YOUR_WEBHOOK_URL',
}
```

## Deployment

### As a systemd service:
```bash
sudo nano /etc/systemd/system/bourbon-bot.service
```

```ini
[Unit]
Description=FWGS Whiskey Release Monitor
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/bot
Environment="HOME=/home/your_user"
ExecStart=/path/to/venv/bin/python3 bourbon_monitor_playwright.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bourbon-bot
sudo systemctl start bourbon-bot
```

## Alert Types

| Alert | Trigger | @everyone |
|-------|---------|-----------|
| NEW WHISKEY RELEASE! | New product, status=available | Yes |
| NEW BUT COMING SOON! | New product, status=coming_soon | No |
| NEW BUT LOTTERY! | New product, status=lottery | No |
| NOW AVAILABLE FOR PURCHASE! | Status changed to available | Yes |
| HOT ITEMS GOING FAST! | Stock dropping rapidly, still > 0 | Yes |

## Status Detection

Products are categorized by parsing the page text:
- `available` - Has "Add to Cart" or no blocking indicators
- `coming_soon` - Contains "coming soon"
- `lottery` - Contains "lottery"
- `out_of_stock` - Contains "out of stock" or "sold out"
