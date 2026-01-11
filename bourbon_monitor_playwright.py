#!/usr/bin/env python3
"""
FWGS Whiskey Release Monitor - Playwright + JS extraction version
Fast and efficient like Bot #1, but for the Whiskey Release page
"""

import time
import logging
import requests
import signal
import sys
import random
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =============================================================================
# CONFIGURATION - Bot #2 specific settings
# =============================================================================

CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 30,  # seconds
    'discord_webhook_url': 'YOUR_DISCORD_WEBHOOK_URL',
}

# =============================================================================
# STEALTH SCRIPTS
# =============================================================================

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
"""

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# BROWSER MANAGER
# =============================================================================

class BrowserManager:
    """Manages Playwright browser with stealth"""

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
        """Launch browser with stealth"""
        logger.info("Starting Playwright browser...")
        self.playwright = sync_playwright().start()

        viewport_width = 1920 + random.randint(-100, 100)
        viewport_height = 1080 + random.randint(-50, 50)

        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
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
        """Clean shutdown"""
        for resource in [self.page, self.context, self.browser, self.playwright]:
            if resource:
                try:
                    if hasattr(resource, 'close'):
                        resource.close()
                    elif hasattr(resource, 'stop'):
                        resource.stop()
                except Exception:
                    pass
        logger.info("Browser stopped")

    def close_popups(self):
        """Close popups including age gate"""
        try:
            js_close = """
            () => {
                let closed = [];
                // Age gate - YES button
                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    const text = (btn.textContent || '').toUpperCase().trim();
                    if ((text === 'YES' || text.includes('I AM 21')) && btn.offsetParent !== null) {
                        btn.click();
                        closed.push('age-gate');
                    }
                });
                // Close buttons
                document.querySelectorAll('[aria-label*="close" i], [aria-label*="dismiss" i]').forEach(btn => {
                    if (btn.offsetParent !== null) {
                        btn.click();
                        closed.push('close-btn');
                    }
                });
                return closed.length > 0 ? closed.join(', ') : 'none';
            }
            """
            result = self.page.evaluate(js_close)
            if result != 'none':
                logger.info(f"Closed popups: {result}")

            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"Popup close: {e}")

    def load_all_products(self):
        """Click Load More until all products loaded"""
        clicks = 0
        consecutive_failures = 0

        while clicks < 15:
            try:
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(500)

                # Try to find and click Load More
                load_more_clicked = False
                try:
                    load_more = self.page.get_by_role("button", name="Load More")
                    if load_more.is_visible(timeout=2000):
                        load_more.click()
                        load_more_clicked = True
                        clicks += 1
                        logger.info(f"Clicked Load More (#{clicks})")
                        self.page.wait_for_timeout(2000)
                except Exception:
                    pass

                if not load_more_clicked:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        break
                else:
                    consecutive_failures = 0

            except Exception as e:
                logger.debug(f"Load more error: {e}")
                break

        logger.info(f"Loaded products ({clicks} Load More clicks)")
        return clicks

    def navigate(self, url):
        """Navigate and prepare page"""
        logger.info(f"Navigating to {url}")
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("Network didn't fully settle")

        self.close_popups()
        self.page.wait_for_timeout(1000)
        self.close_popups()
        self.load_all_products()


# =============================================================================
# PRODUCT SCRAPER - Fast JS extraction
# =============================================================================

class ProductScraper:
    """Scrapes whiskey products using Playwright + JS"""

    def __init__(self, target_url, headless=True):
        self.target_url = target_url
        self.headless = headless

    def scrape(self):
        """Scrape products using fast JS extraction"""
        with BrowserManager(self.headless) as browser:
            browser.navigate(self.target_url)
            products = self._extract_products_js(browser)
            filtered = self._filter_whiskey(products)

            if len(filtered) < 5:
                logger.warning(f"Only found {len(filtered)} products - retrying...")
                browser.page.wait_for_timeout(5000)
                browser.page.reload()
                browser.close_popups()
                browser.load_all_products()
                products = self._extract_products_js(browser)
                filtered = self._filter_whiskey(products)

            logger.info(f"Scrape complete: {len(filtered)} whiskey products")
            return filtered

    def fetch_product_urls(self, products):
        """Fetch URLs by clicking products"""
        if not products:
            return products

        logger.info(f"Fetching URLs for {len(products)} product(s)...")

        with BrowserManager(self.headless) as browser:
            browser.navigate(self.target_url)

            for product in products:
                try:
                    name = product.get("name", "")

                    # Escape quotes for JS
                    escaped_name = name.replace("'", "\\'").replace('"', '\\"')

                    js_click = f"""
                    () => {{
                        const cards = document.querySelectorAll(".card");
                        for (const card of cards) {{
                            const heading = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                            if (heading && heading.textContent.trim() === '{escaped_name}') {{
                                const clickTarget = card.querySelector("img, .card__image") || card;
                                clickTarget.click();
                                return true;
                            }}
                        }}
                        return false;
                    }}
                    """

                    clicked = browser.page.evaluate(js_click)

                    if clicked:
                        browser.page.wait_for_timeout(2000)
                        url = browser.page.url
                        if "/product/" in url:
                            product["url"] = url
                            logger.info(f"Got URL for {name[:40]}: {url}")
                        browser.page.go_back()
                        browser.page.wait_for_timeout(1000)
                        browser.close_popups()
                except Exception as e:
                    logger.warning(f"Error getting URL for {product.get('name', '?')}: {e}")

        return products

    def _extract_products_js(self, browser):
        """Extract products with single JS call"""
        logger.info("Extracting products via JS...")

        js_extract = """
        () => {
            const products = [];
            const cards = document.querySelectorAll(".card");

            cards.forEach(card => {
                try {
                    const cardText = card.textContent || '';
                    const cardLower = cardText.toLowerCase();

                    // Get name
                    let name = null;
                    const heading = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                    if (heading) {
                        name = heading.textContent.trim();
                    }

                    // Get price
                    let price = null;
                    const priceEl = card.querySelector("[class*=price]");
                    if (priceEl) {
                        const priceMatch = priceEl.textContent.match(/[\\d,]+\\.?\\d*/);
                        if (priceMatch) {
                            price = parseFloat(priceMatch[0].replace(",", ""));
                        }
                    }

                    // Get availability
                    let availability = 0;
                    const stockMatch = cardLower.match(/(\\d+)\\s*(?:available|in stock)/);
                    if (stockMatch) {
                        availability = parseInt(stockMatch[1]);
                    } else if (cardLower.includes("in stock") || cardLower.includes("available")) {
                        availability = 1;
                    }

                    // Determine status
                    let status = "available";
                    if (cardLower.includes("coming soon")) {
                        status = "coming_soon";
                    } else if (cardLower.includes("lottery")) {
                        status = "lottery";
                    } else if (cardLower.includes("out of stock") || cardLower.includes("sold out")) {
                        status = "out_of_stock";
                    }

                    if (name && price) {
                        products.push({
                            name: name,
                            price: price,
                            availability: availability,
                            status: status,
                            url: null
                        });
                    }
                } catch (e) {}
            });

            return products;
        }
        """

        try:
            products = browser.page.evaluate(js_extract)
            logger.info(f"Extracted {len(products)} products via JS")
            return products
        except Exception as e:
            logger.error(f"JS extraction failed: {e}")
            return []

    def _filter_whiskey(self, products):
        """Filter to whiskey/bourbon products"""
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


# =============================================================================
# DISCORD NOTIFIER
# =============================================================================

class DiscordNotifier:
    """Send Discord notifications"""

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def _send(self, message, mention_everyone=False):
        """Send webhook message"""
        try:
            if mention_everyone:
                message = "@everyone\n\n" + message

            data = {"content": message}
            if mention_everyone:
                data["allowed_mentions"] = {"parse": ["everyone"]}

            response = requests.post(self.webhook_url, json=data, timeout=10)
            if response.status_code == 204:
                logger.info("Discord notification sent")
                return True
            logger.warning(f"Discord failed: {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"Discord error: {e}")
            return False

    def send_startup(self, products):
        """Send startup notification"""
        available = sum(1 for p in products if p.get('status') == 'available')
        coming_soon = sum(1 for p in products if p.get('status') == 'coming_soon')
        lottery = sum(1 for p in products if p.get('status') == 'lottery')

        msg = f"**Whiskey Release Monitor Started!**\n\n"
        msg += f"Currently tracking **{len(products)}** products"
        if coming_soon or lottery:
            msg += f"\n  Available: {available}"
            if coming_soon:
                msg += f" | Coming Soon: {coming_soon}"
            if lottery:
                msg += f" | Lottery: {lottery}"
        msg += f"\n\nMonitoring every {CONFIG['check_interval']}s\n"
        msg += f"{CONFIG['url']}\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg)

    def send_new_available(self, products):
        """Send alert for available products"""
        if not products:
            return True
        msg = "**NEW WHISKEY RELEASE!**\n\n"
        for p in products:
            msg += f"**{p['name']}**\n  ${p['price']:.2f}"
            if p['availability'] > 1:
                msg += f" | {p['availability']} in stock"
            if p.get('url'):
                msg += f"\n  {p['url']}"
            msg += "\n\n"
        msg += f"{CONFIG['url']}\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg, mention_everyone=True)

    def send_coming_soon(self, products):
        """Send alert for coming soon products"""
        if not products:
            return True
        msg = "**NEW BUT COMING SOON!**\n\nThese just appeared but aren't available yet:\n\n"
        for p in products:
            msg += f"**{p['name']}**\n  ${p['price']:.2f}"
            if p.get('url'):
                msg += f"\n  {p['url']}"
            msg += "\n\n"
        msg += "I'll alert you when they become available!\n\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg)

    def send_lottery(self, products):
        """Send alert for lottery products"""
        if not products:
            return True
        msg = "**NEW BUT LOTTERY!**\n\nThese require lottery entry:\n\n"
        for p in products:
            msg += f"**{p['name']}**\n  ${p['price']:.2f}"
            if p.get('url'):
                msg += f"\n  {p['url']}"
            msg += "\n\n"
        msg += "I'll alert you if they become available for regular purchase!\n\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg)

    def send_now_available(self, products):
        """Send alert when coming soon/lottery becomes available"""
        if not products:
            return True
        msg = "**NOW AVAILABLE FOR PURCHASE!**\n\nThese were coming soon/lottery and just went live:\n\n"
        for p in products:
            msg += f"**{p['name']}**\n  ${p['price']:.2f}"
            if p['availability'] > 1:
                msg += f" | {p['availability']} in stock"
            if p.get('url'):
                msg += f"\n  {p['url']}"
            msg += "\n\n"
        msg += f"GO GO GO! {CONFIG['url']}\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg, mention_everyone=True)

    def send_hot_items(self, products):
        """Send alert for hot items going fast"""
        if not products:
            return True
        msg = "**HOT ITEMS GOING FAST!**\n\n"
        for p in products:
            msg += f"**{p['name']}**\n  ${p['price']:.2f} | Only {p['availability']} left!"
            if p.get('url'):
                msg += f"\n  {p['url']}"
            msg += "\n\n"
        msg += datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return self._send(msg, mention_everyone=True)


# =============================================================================
# MONITOR
# =============================================================================

class WhiskeyMonitor:
    """Main monitoring class"""

    def __init__(self):
        self.scraper = ProductScraper(CONFIG['url'])
        self.notifier = DiscordNotifier(CONFIG['discord_webhook_url'])
        self.last_products = {}  # name -> product
        self.stock_history = {}  # name -> [stock counts]
        self.hot_items = set()
        self.hot_notified = set()
        self.running = True

    def check(self, is_first_run=False):
        """Run a single check"""
        logger.info("=" * 50)
        logger.info(f"Check at {datetime.now().strftime('%I:%M %p')}")

        try:
            products = self.scraper.scrape()

            if not products:
                logger.error("No products found - skipping check")
                return False

            # Safety check
            if self.last_products and len(products) < len(self.last_products) * 0.5:
                logger.error(f"Found {len(products)} but was tracking {len(self.last_products)} - skipping")
                return False

            current = {p['name']: p for p in products}

            if is_first_run:
                self.last_products = current
                logger.info(f"Baseline established: {len(products)} products")
                return True

            # Detect new products
            new_names = set(current.keys()) - set(self.last_products.keys())
            new_available = []
            new_coming_soon = []
            new_lottery = []

            for name in new_names:
                p = current[name]
                status = p.get('status', 'available')
                if status == 'coming_soon':
                    new_coming_soon.append(p)
                elif status == 'lottery':
                    new_lottery.append(p)
                else:
                    new_available.append(p)

            # Detect status changes
            now_available = []
            for name, p in current.items():
                if name in self.last_products:
                    old_status = self.last_products[name].get('status', 'available')
                    new_status = p.get('status', 'available')
                    if old_status in ('coming_soon', 'lottery') and new_status == 'available':
                        now_available.append(p)
                        logger.info(f"STATUS CHANGE: {name} -> available!")

            # Track stock and detect hot items
            hot_to_notify = []
            for name, p in current.items():
                stock = p.get('availability', 0)
                name_lower = name.lower()

                if name_lower not in self.stock_history:
                    self.stock_history[name_lower] = []
                self.stock_history[name_lower].append(stock)
                if len(self.stock_history[name_lower]) > 5:
                    self.stock_history[name_lower].pop(0)

                if len(self.stock_history[name_lower]) >= 2:
                    initial = self.stock_history[name_lower][0]
                    drop = initial - stock
                    if (drop >= 5 or (initial > 0 and drop / initial >= 0.3)):
                        if name_lower not in self.hot_items:
                            self.hot_items.add(name_lower)
                            logger.info(f"HOT ITEM: {name} ({initial} -> {stock})")
                            # Only notify if stock > 0
                            if stock > 0 and name_lower not in self.hot_notified:
                                self.hot_notified.add(name_lower)
                                hot_to_notify.append(p)

            # Send notifications
            if new_available:
                self.scraper.fetch_product_urls(new_available)
                self.notifier.send_new_available(new_available)
                logger.info(f"NEW AVAILABLE: {len(new_available)}")

            if new_coming_soon:
                self.scraper.fetch_product_urls(new_coming_soon)
                self.notifier.send_coming_soon(new_coming_soon)
                logger.info(f"NEW COMING SOON: {len(new_coming_soon)}")

            if new_lottery:
                self.scraper.fetch_product_urls(new_lottery)
                self.notifier.send_lottery(new_lottery)
                logger.info(f"NEW LOTTERY: {len(new_lottery)}")

            if now_available:
                self.scraper.fetch_product_urls(now_available)
                self.notifier.send_now_available(now_available)
                logger.info(f"NOW AVAILABLE: {len(now_available)}")

            if hot_to_notify:
                self.notifier.send_hot_items(hot_to_notify)
                logger.info(f"HOT ITEMS: {len(hot_to_notify)}")

            if not any([new_available, new_coming_soon, new_lottery, now_available, hot_to_notify]):
                logger.info("No changes detected")

            self.last_products = current
            return True

        except Exception as e:
            logger.error(f"Check failed: {e}")
            return False

    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 50)
        logger.info("WHISKEY RELEASE MONITOR (Playwright)")
        logger.info(f"URL: {CONFIG['url']}")
        logger.info(f"Interval: {CONFIG['check_interval']}s")
        logger.info("=" * 50)

        # Signal handlers
        def shutdown(signum, frame):
            logger.info("Shutdown signal received")
            self.running = False

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # First check
        logger.info("Running initial check...")
        self.check(is_first_run=True)

        # Send startup notification
        if self.last_products:
            self.notifier.send_startup(list(self.last_products.values()))

        # Main loop
        while self.running:
            logger.info(f"Next check in {CONFIG['check_interval']}s...")

            for _ in range(CONFIG['check_interval']):
                if not self.running:
                    break
                time.sleep(1)

            if self.running:
                self.check()

        logger.info("Monitor stopped")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    monitor = WhiskeyMonitor()
    monitor.run()
