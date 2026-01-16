#!/usr/bin/env python3
"""
FWGS Whiskey Release Monitor v4
Using Bot 2's proven architecture - no asyncio manipulation.
"""

import time
import logging
import requests
import signal
import random
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 30,
    'discord_webhook_url': 'REDACTED_DISCORD_WEBHOOK_URL',
}

STEALTH_SCRIPTS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# BROWSER MANAGER - Identical to Bot 2
# =============================================================================

class BrowserManager:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    def start(self):
        logger.info("Starting browser...")
        self.playwright = sync_playwright().start()
        
        viewport_width = 1920 + random.randint(-100, 100)
        viewport_height = 1080 + random.randint(-50, 50)

        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )

        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': viewport_width, 'height': viewport_height},
            locale='en-US',
            timezone_id='America/New_York',
        )
        self.context.add_init_script(STEALTH_SCRIPTS)
        self.page = self.context.new_page()
        logger.info(f"Browser started (viewport: {viewport_width}x{viewport_height})")

    def stop(self):
        errors = []
        for name, obj in [('page', self.page), ('context', self.context), ('browser', self.browser), ('playwright', self.playwright)]:
            if obj:
                try:
                    obj.close() if name != 'playwright' else obj.stop()
                except Exception as e:
                    errors.append(f"{name}: {e}")
        if errors:
            logger.warning(f"Browser cleanup errors: {', '.join(errors)}")
        else:
            logger.info("Browser stopped cleanly")

    def navigate_and_prepare(self, url):
        logger.info(f"Navigating to {url}")
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
        try:
            self.page.wait_for_load_state('networkidle', timeout=3000)
        except PlaywrightTimeoutError:
            pass
        self._close_popups()
        self._scroll_load()
        logger.info("Page ready")

    def _close_popups(self):
        try:
            result = self.page.evaluate("""() => {
                let closed = [];
                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    const text = (btn.textContent || '').toUpperCase().trim();
                    if ((text === 'YES' || text.includes('I AM 21')) && btn.offsetParent !== null) {
                        btn.click(); closed.push('age-gate');
                    }
                });
                document.querySelectorAll('[aria-label*="close" i], [aria-label*="dismiss" i]').forEach(btn => {
                    if (btn.offsetParent !== null) { btn.click(); closed.push('close-btn'); }
                });
                return closed.length > 0 ? closed.join(', ') : 'none';
            }""")
            if result != 'none':
                logger.info(f"Closed popups: {result}")
            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(300)
        except Exception as e:
            logger.debug(f"Popup close: {e}")

    def _scroll_load(self):
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(1500)
            self.page.evaluate("window.scrollTo(0, 0)")
            for i in range(5):
                self.page.wait_for_timeout(1500)
                count = self.page.evaluate("document.querySelectorAll('.card:has([class*=price])').length")
                if count > 0:
                    logger.info(f"Products found: {count} (attempt {i+1})")
                    return
        except Exception as e:
            logger.debug(f"Scroll load: {e}")

# =============================================================================
# SCRAPER - New instance each check, like Bot 2
# =============================================================================

class WhiskeyScraper:
    def __init__(self, url, headless=True):
        self.url = url
        self.headless = headless

    def scrape(self):
        """Scrape and return whiskey products. Browser lifecycle contained here."""
        with BrowserManager(headless=self.headless) as browser:
            browser.navigate_and_prepare(self.url)
            products = self._extract_products(browser)
            filtered = self._filter_whiskey(products)
            
            if len(filtered) < 3:
                logger.warning(f"Only {len(filtered)} products - retrying...")
                browser.page.wait_for_timeout(3000)
                browser.page.reload()
                browser._close_popups()
                browser._scroll_load()
                products = self._extract_products(browser)
                filtered = self._filter_whiskey(products)
            
            return filtered

    def scrape_with_urls(self, product_names):
        """Scrape and get URLs for specific products."""
        urls = {}
        with BrowserManager(headless=self.headless) as browser:
            browser.navigate_and_prepare(self.url)
            for name in product_names:
                url = self._get_product_url(browser, name)
                if url:
                    urls[name] = url
        return urls

    def _extract_products(self, browser):
        logger.info("Extracting products...")
        try:
            products = browser.page.evaluate("""() => {
                const products = [];
                document.querySelectorAll(".card:has([class*=price])").forEach(card => {
                    try {
                        const cardLower = (card.textContent || '').toLowerCase();
                        const heading = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                        const priceEl = card.querySelector("[class*=price]");
                        if (!heading || !priceEl) return;
                        const name = heading.textContent.trim();
                        const priceMatch = priceEl.textContent.match(/[\\d,]+\\.?\\d*/);
                        if (!priceMatch) return;
                        const price = parseFloat(priceMatch[0].replace(",", ""));
                        let availability = 0;
                        const stockMatch = cardLower.match(/(\\d+)\\s*(?:available|in stock)/);
                        if (stockMatch) availability = parseInt(stockMatch[1]);
                        else if (cardLower.includes("in stock") || cardLower.includes("available")) availability = 1;
                        let status = "available";
                        if (cardLower.includes("coming soon")) status = "coming_soon";
                        else if (cardLower.includes("lottery")) status = "lottery";
                        else if (cardLower.includes("out of stock") || cardLower.includes("sold out")) status = "out_of_stock";
                        products.push({ name, price, availability, status });
                    } catch (e) {}
                });
                return products;
            }""")
            logger.info(f"Extracted {len(products)} products")
            return products
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return []

    def _filter_whiskey(self, products):
        filtered = []
        for p in products:
            name_lower = p["name"].lower()
            if any(term in name_lower for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                if 'jack daniel' not in name_lower:
                    status_str = f" [{p['status']}]" if p['status'] != 'available' else ""
                    logger.info(f"  + {p['name']} - ${p['price']}{status_str}")
                    filtered.append(p)
        logger.info(f"Filtered to {len(filtered)} whiskey products")
        return filtered

    def _get_product_url(self, browser, product_name):
        try:
            escaped = product_name.replace("'", "\\'").replace('"', '\\"')
            clicked = browser.page.evaluate(f"""() => {{
                for (const card of document.querySelectorAll(".card:has([class*=price])")) {{
                    const h = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                    if (h && h.textContent.trim() === '{escaped}') {{
                        (card.querySelector("img, .card__image") || card).click();
                        return true;
                    }}
                }}
                return false;
            }}""")
            if clicked:
                browser.page.wait_for_timeout(2000)
                url = browser.page.url
                browser.page.go_back()
                browser.page.wait_for_timeout(1000)
                browser._close_popups()
                if "/product/" in url:
                    return url
        except Exception as e:
            logger.warning(f"Error getting URL for {product_name}: {e}")
        return None

# =============================================================================
# DISCORD NOTIFIER
# =============================================================================

class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def _send(self, message, mention=False):
        try:
            if mention:
                message = "@everyone\n\n" + message
            data = {"content": message}
            if mention:
                data["allowed_mentions"] = {"parse": ["everyone"]}
            r = requests.post(self.webhook_url, json=data, timeout=10)
            if r.status_code == 204:
                logger.info("Discord sent")
                return True
            logger.warning(f"Discord failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Discord error: {e}")
        return False

    def send_startup(self, products):
        msg = f"**Whiskey Release Monitor Started!**\n\nTracking **{len(products)}** products\nInterval: {CONFIG['check_interval']}s\n{CONFIG['url']}\n{datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        return self._send(msg)

    def send_new(self, products, urls=None):
        if not products: return
        msg = "**NEW WHISKEY RELEASE!**\n\n"
        for p in products:
            msg += f"**{p['name']}** - ${p['price']:.2f}"
            if p['availability'] > 1: msg += f" | {p['availability']} in stock"
            if urls and p['name'] in urls: msg += f"\n{urls[p['name']]}"
            msg += "\n\n"
        msg += f"{CONFIG['url']}\n{datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        return self._send(msg, mention=True)

    def send_status_change(self, products, old_status, urls=None):
        if not products: return
        msg = f"**STATUS CHANGE: {old_status} → AVAILABLE!**\n\n"
        for p in products:
            msg += f"**{p['name']}** - ${p['price']:.2f}\n"
            if urls and p['name'] in urls: msg += f"{urls[p['name']]}\n"
        msg += f"\n{CONFIG['url']}\n{datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        return self._send(msg, mention=True)

# =============================================================================
# STORAGE - Persistent state between checks
# =============================================================================

class ProductStorage:
    def __init__(self):
        self.products = {}
        self.stock_history = {}

    def update(self, products):
        old = self.products.copy()
        self.products = {p['name']: p for p in products}
        return old

    def get_new(self, old, current):
        old_names = set(old.keys())
        return [p for p in current if p['name'] not in old_names]

    def get_status_changes(self, old, current):
        changes = []
        for p in current:
            if p['name'] in old:
                old_status = old[p['name']].get('status', 'available')
                if old_status in ('coming_soon', 'lottery') and p.get('status') == 'available':
                    changes.append((p, old_status))
        return changes

# =============================================================================
# MAIN MONITOR
# =============================================================================

running = True

def signal_handler(signum, frame):
    global running
    logger.info("Shutdown signal received")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_check(storage, notifier, is_first_run=False):
    """Single check - creates new scraper each time like Bot 2."""
    logger.info("=" * 50)
    logger.info(f"Check at {datetime.now().strftime('%I:%M %p')}")
    
    try:
        # New scraper each check - key to Bot 2's stability
        scraper = WhiskeyScraper(CONFIG['url'])
        products = scraper.scrape()
        
        if not products:
            logger.error("No products found")
            return False
        
        old = storage.update(products)
        
        if is_first_run:
            logger.info(f"Baseline: {len(products)} products")
            return True
        
        # Detect new products
        new_products = storage.get_new(old, products)
        if new_products:
            # Get URLs for new products (separate browser session)
            urls = scraper.scrape_with_urls([p['name'] for p in new_products])
            notifier.send_new(new_products, urls)
            logger.info(f"NEW: {len(new_products)}")
        
        # Detect status changes
        status_changes = storage.get_status_changes(old, products)
        if status_changes:
            for p, old_status in status_changes:
                urls = scraper.scrape_with_urls([p['name']])
                notifier.send_status_change([p], old_status, urls)
                logger.info(f"STATUS CHANGE: {p['name']} {old_status} → available")
        
        if not new_products and not status_changes:
            logger.info("No changes")
        
        logger.info("Check complete")
        return True
        
    except Exception as e:
        logger.error(f"Check failed: {e}")
        return False


def main():
    logger.info("=" * 50)
    logger.info("WHISKEY RELEASE MONITOR v4")
    logger.info(f"URL: {CONFIG['url']}")
    logger.info(f"Interval: {CONFIG['check_interval']}s")
    logger.info("=" * 50)
    
    storage = ProductStorage()
    notifier = DiscordNotifier(CONFIG['discord_webhook_url'])
    
    # Initial check
    run_check(storage, notifier, is_first_run=True)
    if storage.products:
        notifier.send_startup(list(storage.products.values()))
    
    while running:
        logger.info(f"Next check in {CONFIG['check_interval']}s...")
        for _ in range(CONFIG['check_interval']):
            if not running:
                break
            time.sleep(1)
        if running:
            run_check(storage, notifier)
    
    logger.info("Monitor stopped")


if __name__ == "__main__":
    main()
