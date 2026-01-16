#!/usr/bin/env python3
"""
FWGS Whiskey Release Monitor v5
Direct port of Bot 2's proven architecture - EXACT same patterns.
Only difference: URL and filter criteria.
"""

import json
import logging
import os
import random
import re
import requests
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =============================================================================
# CONFIGURATION - Matches Bot 2's Config class
# =============================================================================

class Config:
    """Application configuration"""
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR = BASE_DIR / "logs"

    # Ensure directories exist
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    # Bot 1 specific settings
    TARGET_URL = 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release'
    DISCORD_WEBHOOK_URL = 'REDACTED_DISCORD_WEBHOOK_URL'
    CHECK_INTERVAL = 0.5  # minutes (30 seconds)
    HEADLESS = True

    # Data files
    PRODUCTS_FILE = DATA_DIR / "products.json"
    STATE_FILE = DATA_DIR / "state.json"
    LOG_FILE = LOG_DIR / "bourbon_bot.log"


class Constants:
    """Application constants - matches Bot 2"""
    MIN_PRODUCTS_REASONABLE = 3
    MAX_PRODUCTS_REASONABLE = 150
    PRODUCT_DROP_THRESHOLD = 0.5

    DISCORD_TIMEOUT = 10
    DISCORD_MAX_RETRIES = 3
    DISCORD_RETRY_DELAY = 2

    FLICKER_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 hours


# =============================================================================
# LOGGING - Matches Bot 2
# =============================================================================

def setup_logging():
    """Configure logging"""
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)


# =============================================================================
# STEALTH SCRIPTS - Identical to Bot 2
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
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
"""


# =============================================================================
# BROWSER MANAGER - Exact copy of Bot 2
# =============================================================================

class BrowserManager:
    """Manages Playwright browser instance with stealth capabilities"""

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
        return False  # Don't suppress exceptions

    def start(self):
        """Launch browser with stealth and fresh context"""
        logger.info("Starting browser with stealth...")
        self.playwright = sync_playwright().start()

        viewport_width = 1920 + random.randint(-100, 100)
        viewport_height = 1080 + random.randint(-50, 50)

        # EXACT same args as Bot 2
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
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
        """Clean shutdown with proper error handling - EXACT Bot 2 pattern"""
        errors = []

        if self.page:
            try:
                self.page.close()
            except Exception as e:
                errors.append(f"page: {e}")

        if self.context:
            try:
                self.context.close()
            except Exception as e:
                errors.append(f"context: {e}")

        if self.browser:
            try:
                self.browser.close()
            except Exception as e:
                errors.append(f"browser: {e}")

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                errors.append(f"playwright: {e}")

        if errors:
            logger.warning(f"Browser cleanup errors: {', '.join(errors)}")
        else:
            logger.info("Browser stopped cleanly")

    def close_all_popups(self):
        """Close all popups - EXACT Bot 2 pattern with all text patterns"""
        try:
            js_close = """
            () => {
                let clicked = new Set();
                let result = [];

                // Handle age gate FIRST - look for YES/confirm buttons
                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    if (clicked.has(btn)) return;
                    const text = (btn.textContent || '').toUpperCase().trim();
                    if ((text === 'YES' || text.includes('I AM 21') || text === 'CONFIRM' ||
                         text.includes('ENTER')) && btn.offsetParent !== null) {
                        btn.click();
                        clicked.add(btn);
                        result.push('age-gate');
                    }
                });

                // Find close buttons by aria-label
                document.querySelectorAll('[aria-label*="close" i], [aria-label*="dismiss" i]').forEach(btn => {
                    if (clicked.has(btn)) return;
                    if (btn.offsetParent !== null) {
                        btn.click();
                        clicked.add(btn);
                        result.push('aria-close');
                    }
                });

                // Find by role="button" with close-like text
                document.querySelectorAll('[role="button"], button').forEach(btn => {
                    if (clicked.has(btn)) return;
                    const text = (btn.textContent || '').trim();
                    if ((text === 'X' || text === '×' || text === 'x' || text.toLowerCase() === 'close')
                         && btn.offsetParent !== null) {
                        btn.click();
                        clicked.add(btn);
                        result.push('close-btn');
                    }
                });

                return result.length > 0 ? result.join(', ') : 'none';
            }
            """

            result = self.page.evaluate(js_close)
            if result != 'none':
                logger.info(f"Closed popups: {result}")

            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(300)
            return True

        except Exception as e:
            logger.warning(f"Popup close error: {e}")
            return False

    def scroll_to_load_all(self):
        """Scroll page to trigger lazy-loaded content"""
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)
            return True
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
            return False

    def navigate_and_prepare(self, url):
        """Navigate and prepare page - EXACT Bot 2 pattern"""
        logger.info(f"Navigating to {url}")

        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

        logger.info("Waiting for page to stabilize...")
        try:
            self.page.wait_for_load_state('networkidle', timeout=3000)
            logger.info("Page stabilized")
        except PlaywrightTimeoutError:
            pass

        self.close_all_popups()
        self.scroll_to_load_all()
        self.page.wait_for_timeout(500)

        logger.info("Page ready")
        return True

    def load_all_products(self):
        """Ensure all products are loaded - Bot 2 pattern"""
        try:
            logger.info("Loading all products...")

            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)

            # Check product count
            count = self.page.evaluate("document.querySelectorAll('.card:has([class*=price])').length")
            logger.info(f"Product count: {count}")

            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)

            logger.info("All products loaded")
            return count

        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return 0


# =============================================================================
# SCRAPER - Matches Bot 2's ProductScraper
# =============================================================================

class ProductScraper:
    """Scrapes whiskey products from FWGS website"""

    def __init__(self, target_url=None, headless=True):
        self.target_url = target_url or Config.TARGET_URL
        self.headless = headless

    def scrape(self):
        """Scrape the website and return whiskey products"""
        with BrowserManager(headless=self.headless) as browser:
            logger.info("Starting scrape...")

            browser.navigate_and_prepare(self.target_url)
            browser.load_all_products()

            products = self._extract_products_fast(browser)
            filtered = self._filter_whiskey(products)

            # If we found very few products, wait and retry - Bot 2 pattern
            if len(filtered) < Constants.MIN_PRODUCTS_REASONABLE:
                logger.warning(f"Only found {len(filtered)} products - retrying...")
                browser.page.wait_for_timeout(5000)
                products = self._extract_products_fast(browser)
                filtered = self._filter_whiskey(products)
                logger.info(f"After retry: {len(filtered)} whiskey products")

            logger.info(f"Scrape complete: {len(filtered)} whiskey products found")
            return filtered

    def fetch_product_urls(self, products):
        """Fetch URLs for products by clicking on them - Bot 2 pattern"""
        if not products:
            return products

        logger.info(f"Fetching URLs for {len(products)} new product(s)...")

        with BrowserManager(headless=self.headless) as browser:
            browser.navigate_and_prepare(self.target_url)
            browser.load_all_products()

            for product in products:
                try:
                    product_name = product.get("name", "")
                    logger.info(f"Getting URL for: {product_name[:50]}...")

                    js_click = """
                    (productName) => {
                        const cards = document.querySelectorAll(".card:has([class*=price])");
                        for (const card of cards) {
                            const heading = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                            if (heading && heading.textContent.trim() === productName) {
                                const clickTarget = card.querySelector(".card__image, img, .card__container") || card;
                                clickTarget.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    """

                    clicked = browser.page.evaluate(js_click, product_name)

                    if clicked:
                        try:
                            browser.page.wait_for_load_state("domcontentloaded", timeout=10000)
                            browser.page.wait_for_timeout(1000)

                            url = browser.page.url
                            if "/product/" in url or "/p/" in url:
                                product["url"] = url
                                logger.info(f"Got URL: {url}")
                            else:
                                logger.warning(f"Unexpected URL after click: {url}")

                            browser.page.go_back()
                            browser.page.wait_for_load_state("domcontentloaded", timeout=10000)
                            browser.page.wait_for_timeout(500)

                        except Exception as e:
                            logger.warning(f"Navigation error for {product_name}: {e}")
                            browser.navigate_and_prepare(self.target_url)
                            browser.load_all_products()
                    else:
                        logger.warning(f"Could not find card for: {product_name}")

                except Exception as e:
                    logger.error(f"Error fetching URL for product: {e}")
                    continue

        return products

    def _extract_products_fast(self, browser):
        """Extract all products using JavaScript - Bot 2 pattern with fallback"""
        logger.info("Extracting products (fast JS method)...")

        js_extract = """
        () => {
            const products = [];
            const cards = document.querySelectorAll(".card:has([class*=price])");

            cards.forEach(card => {
                try {
                    let name = null;
                    const heading = card.querySelector("h2, h3, h4, [class*=title], [class*=name]");
                    if (heading) {
                        name = heading.textContent.trim();
                    }

                    let price = null;
                    const priceEl = card.querySelector("[class*=price]");
                    if (priceEl) {
                        const priceMatch = priceEl.textContent.match(/[\\d,]+\\.?\\d*/);
                        if (priceMatch) {
                            price = parseFloat(priceMatch[0].replace(",", ""));
                        }
                    }

                    let availability = 0;
                    const cardText = card.textContent.toLowerCase();
                    const stockMatch = cardText.match(/(\\d+)\\s*(?:available|in stock)/);
                    if (stockMatch) {
                        availability = parseInt(stockMatch[1]);
                    } else if (cardText.includes("out of stock") || cardText.includes("sold out")) {
                        availability = 0;
                    } else if (cardText.includes("limited") || cardText.includes("in stock") || cardText.includes("available")) {
                        availability = 1;
                    }

                    let status = "available";
                    const nameLower = name ? name.toLowerCase() : "";

                    if (cardText.includes("coming soon")) {
                        status = "coming_soon";
                    } else if (nameLower.includes("lottery") || cardText.includes("lottery")) {
                        status = "lottery";
                    } else if (cardText.includes("out of stock") || cardText.includes("sold out")) {
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

            for p in products:
                p["scraped_at"] = datetime.now().isoformat()

            return products
        except Exception as e:
            logger.error(f"JS extraction failed: {e}, falling back to slow method")
            return self._extract_products_slow(browser)

    def _extract_products_slow(self, browser):
        """Fallback: Extract products using individual queries"""
        logger.info("Extracting products (slow method)...")
        products = []

        cards = browser.page.query_selector_all(".card:has([class*='price'])")
        logger.info(f"Found {len(cards)} product cards")

        for card in cards:
            try:
                name_el = card.query_selector("h2, h3, h4, [class*='title'], [class*='name']")
                if not name_el:
                    continue
                name = name_el.text_content().strip()

                price_el = card.query_selector("[class*='price']")
                if not price_el:
                    continue
                price_text = price_el.text_content()

                price_match = re.search(r'[\d,]+\.?\d*', price_text)
                if not price_match:
                    continue
                price = float(price_match.group().replace(',', ''))

                card_text = card.text_content().lower()
                availability = 0
                stock_match = re.search(r'(\d+)\s*(?:available|in stock)', card_text)
                if stock_match:
                    availability = int(stock_match.group(1))
                elif "in stock" in card_text or "available" in card_text:
                    availability = 1

                status = "available"
                if "coming soon" in card_text:
                    status = "coming_soon"
                elif "lottery" in name.lower() or "lottery" in card_text:
                    status = "lottery"
                elif "out of stock" in card_text or "sold out" in card_text:
                    status = "out_of_stock"

                products.append({
                    "name": name,
                    "price": price,
                    "availability": availability,
                    "status": status,
                    "url": None,
                    "scraped_at": datetime.now().isoformat()
                })
            except Exception as e:
                logger.debug(f"Error extracting product: {e}")
                continue

        logger.info(f"Extracted {len(products)} products")
        return products

    def _filter_whiskey(self, products):
        """Filter products to whiskey only"""
        logger.info(f"Total products before filtering: {len(products)}")

        filtered = []
        for product in products:
            name_lower = product["name"].lower()

            # Must contain whiskey terms
            if not any(term in name_lower for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                continue

            # Skip Jack Daniels
            if "jack daniel" in name_lower:
                continue

            status = product.get("status", "available")
            status_str = f" [{status}]" if status != "available" else ""
            logger.info(f"  + {product['name']} - ${product['price']} ({product['availability']} in stock){status_str}")
            filtered.append(product)

        logger.info(f"Filtered to {len(filtered)} whiskey products")
        return filtered


# =============================================================================
# STORAGE - Matches Bot 2 with flicker cooldown
# =============================================================================

class ProductStorage:
    """Manages product state with flicker cooldown - Bot 2 pattern"""

    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.state_file = Config.STATE_FILE
        self.recently_seen = {}
        self._load_state()

    def _load_state(self):
        """Load persisted state from disk"""
        try:
            if not self.state_file.exists():
                logger.info("No existing state file, starting fresh")
                return

            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.recently_seen = state.get('recently_seen', {})

            # Clean up old entries (older than 24 hours)
            current_time = time.time()
            cutoff = current_time - (24 * 60 * 60)
            self.recently_seen = {k: v for k, v in self.recently_seen.items() if v > cutoff}

            logger.info(f"Loaded state: {len(self.recently_seen)} recently seen")

        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def _save_state(self):
        """Persist state to disk"""
        try:
            state = {
                'recently_seen': self.recently_seen,
                'saved_at': time.time(),
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

            return True
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            return False

    def load(self):
        """Load products from JSON file"""
        try:
            if not self.file_path.exists():
                return []

            with open(self.file_path, 'r') as f:
                products = json.load(f)
                logger.info(f"Loaded {len(products)} products from storage")
                return products

        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return []

    def save(self, products):
        """Save products to JSON file"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(products, f, indent=2)
            logger.info(f"Saved {len(products)} products to storage")
            self._save_state()
            return True

        except Exception as e:
            logger.error(f"Error saving products: {e}")
            return False

    def get_new_products(self, old_products, new_products):
        """Find new products with flicker cooldown - Bot 2 pattern"""
        old_names = {p['name'].lower() for p in old_products}
        current_time = time.time()
        new = []

        for product in new_products:
            name_lower = product['name'].lower()

            last_seen = self.recently_seen.get(name_lower, 0)
            time_since_seen = current_time - last_seen

            # Update timestamp for all current products
            self.recently_seen[name_lower] = current_time

            if name_lower not in old_names:
                # Only notify if we haven't seen it in the last 2 hours
                if last_seen == 0:
                    new.append(product)
                elif time_since_seen > Constants.FLICKER_COOLDOWN_SECONDS:
                    new.append(product)
                    logger.info(f"Product reappeared after {time_since_seen/3600:.1f} hours: {product['name']}")
                else:
                    logger.info(f"Skipping flicker notification for {product['name']} (seen {time_since_seen/60:.0f} min ago)")

        if new:
            logger.info(f"Found {len(new)} NEW product(s)")

        return new

    def get_status_changes(self, old_products, new_products):
        """Find products that changed from coming_soon/lottery to available"""
        old_by_name = {p["name"].lower(): p for p in old_products}
        changes = []

        for new_p in new_products:
            name_lower = new_p["name"].lower()
            old_p = old_by_name.get(name_lower)
            if old_p:
                old_status = old_p.get("status", "available")
                new_status = new_p.get("status", "available")
                if old_status in ("coming_soon", "lottery") and new_status == "available":
                    changes.append(new_p)
                    logger.info(f"STATUS CHANGE: {new_p['name']} went from {old_status} to available!")

        return changes


# =============================================================================
# DISCORD NOTIFIER - Matches Bot 2 with retry/rate limit
# =============================================================================

class DiscordNotifier:
    """Sends notifications via Discord webhook with retry - Bot 2 pattern"""

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self._last_request_time = 0

    def _format_price(self, price):
        if price is None:
            return "N/A"
        try:
            return f"${float(price):.2f}"
        except (ValueError, TypeError):
            return "N/A"

    def send_new_products(self, products):
        """Send notification for new products"""
        if not products:
            return True

        logger.info(f"Sending notification for {len(products)} new product(s)...")

        message = "**NEW WHISKEY RELEASE!**\n\n"

        for product in products:
            name = product.get("name", "Unknown")
            price = self._format_price(product.get("price"))
            availability = product.get("availability", 0)
            url = product.get("url")
            status = product.get("status", "available")

            message += f"**{name}**\n"
            message += f"  {price}"
            if availability > 1:
                message += f" | {availability} in stock"
            elif availability == 1:
                message += " | In Stock"
            if status != "available":
                message += f" | {status.upper()}"
            message += "\n"

            if url:
                message += f"  {url}\n"
            message += "\n"

        message += f"Browse all: {Config.TARGET_URL}\n"
        message += datetime.now().strftime("%B %d, %Y at %I:%M %p")

        return self._send_webhook(message, mention_everyone=True)

    def send_now_available(self, products):
        """Send alert when coming soon/lottery products become available"""
        if not products:
            return True

        logger.info(f"Sending NOW AVAILABLE notification for {len(products)} product(s)...")

        message = "**NOW AVAILABLE FOR PURCHASE!**\n\n"
        message += "These were coming soon/lottery and just went live:\n\n"

        for product in products:
            name = product.get("name", "Unknown")
            price = self._format_price(product.get("price"))
            availability = product.get("availability", 0)
            url = product.get("url")

            message += f"**{name}**\n"
            message += f"  {price}"
            if availability > 1:
                message += f" | {availability} in stock"
            message += "\n"

            if url:
                message += f"  {url}\n"
            message += "\n"

        message += f"GO GO GO! {Config.TARGET_URL}\n"
        message += datetime.now().strftime("%B %d, %Y at %I:%M %p")

        return self._send_webhook(message, mention_everyone=True)

    def send_startup(self, products):
        """Send startup notification"""
        message = "**Whiskey Release Monitor Started!**\n\n"

        if products:
            available = sum(1 for p in products if p.get("status", "available") == "available")
            coming_soon = sum(1 for p in products if p.get("status") == "coming_soon")
            lottery = sum(1 for p in products if p.get("status") == "lottery")

            message += f"Currently tracking {len(products)} product(s)"
            if coming_soon or lottery:
                message += f"\n  Available: {available}"
                if coming_soon:
                    message += f" | Coming Soon: {coming_soon}"
                if lottery:
                    message += f" | Lottery: {lottery}"
            message += "\n"
        else:
            message += "System online - no products on page yet"

        message += f"\nCheck interval: {Config.CHECK_INTERVAL * 60:.0f} seconds"
        message += "\n" + datetime.now().strftime("%B %d, %Y at %I:%M %p")

        return self._send_webhook(message)

    def send_error(self, error_msg):
        """Send error notification"""
        sanitized = str(error_msg)[:500]
        message = f"**Whiskey Monitor Error**\n\n```{sanitized}```"
        return self._send_webhook(message)

    def _send_webhook(self, message, mention_everyone=False):
        """Send message via Discord webhook with retry - Bot 2 pattern"""
        # Rate limiting
        now = time.time()
        if now - self._last_request_time < 1.0:
            time.sleep(1.0 - (now - self._last_request_time))

        data = {"content": message}
        if mention_everyone:
            data["allowed_mentions"] = {"parse": ["everyone"]}
            data["content"] = "@everyone\n\n" + message

        for attempt in range(Constants.DISCORD_MAX_RETRIES):
            try:
                self._last_request_time = time.time()

                response = requests.post(
                    self.webhook_url,
                    json=data,
                    timeout=Constants.DISCORD_TIMEOUT
                )

                if response.status_code == 204:
                    logger.info("Discord notification sent")
                    return True

                if response.status_code == 429:
                    retry_after = response.json().get("retry_after", 5)
                    logger.warning(f"Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                logger.warning(f"Discord failed (attempt {attempt + 1}): {response.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"Discord timeout (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"Discord connection error (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"Discord error: {e}")

            if attempt < Constants.DISCORD_MAX_RETRIES - 1:
                delay = Constants.DISCORD_RETRY_DELAY * (2 ** attempt)
                time.sleep(delay)

        logger.error(f"Failed to send Discord notification after {Constants.DISCORD_MAX_RETRIES} attempts")
        return False


# =============================================================================
# MAIN - Exact Bot 2 pattern with outer exception handler
# =============================================================================

running = True


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info("Shutdown signal received, stopping...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_check(storage, notifier, is_first_run=False):
    """Execute single monitoring check - Bot 2 pattern with safety checks"""
    logger.info("=" * 60)
    logger.info(f"WHISKEY MONITOR - {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    logger.info("=" * 60)

    try:
        # Initialize scraper (new each time)
        scraper = ProductScraper(Config.TARGET_URL, headless=Config.HEADLESS)

        # Load previous products
        old_products = storage.load()

        # Scrape current products
        new_products = scraper.scrape()

        # SAFETY CHECK: if we found 0 products but had some before, skip
        if old_products and len(old_products) > 0 and len(new_products) == 0:
            logger.error(
                f"Found 0 products but was tracking {len(old_products)} - "
                "skipping check to prevent false alerts"
            )
            return False

        # SAFETY CHECK: if we lost 50%+ of products, scrape likely failed
        if old_products and len(old_products) > 0:
            drop_percentage = (len(old_products) - len(new_products)) / len(old_products)
            if drop_percentage >= Constants.PRODUCT_DROP_THRESHOLD:
                logger.error(
                    f"Found {len(new_products)} products but was tracking "
                    f"{len(old_products)} ({drop_percentage*100:.0f}% drop) - "
                    "skipping check to prevent false alerts"
                )
                return False

        # Detect new products
        new_arrivals = storage.get_new_products(old_products, new_products)

        # Detect status changes
        now_available = []
        if old_products and not is_first_run:
            now_available = storage.get_status_changes(old_products, new_products)

        # Send notifications (but not on first run)
        if new_arrivals and not is_first_run:
            scraper.fetch_product_urls(new_arrivals)
            notifier.send_new_products(new_arrivals)
            logger.info(f"NEW ARRIVALS: {len(new_arrivals)} product(s)")
        elif new_arrivals and is_first_run:
            logger.info(f"Establishing baseline with {len(new_arrivals)} product(s)")
        else:
            logger.info("No new products found")

        # Send notifications for products that became available
        if now_available:
            scraper.fetch_product_urls(now_available)
            notifier.send_now_available(now_available)
            logger.info(f"NOW AVAILABLE: {len(now_available)} product(s) went live!")

        # Save current state
        storage.save(new_products)

        logger.info("Check complete")
        return True

    except KeyboardInterrupt:
        raise

    except Exception as e:
        logger.error(f"Error during check: {e}", exc_info=True)

        error_str = str(e).lower()
        harmless_errors = ["browser has been closed", "target page", "context has been closed"]

        if not any(err in error_str for err in harmless_errors):
            try:
                notifier.send_error(str(e))
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")

        return False


def main():
    """Main monitoring loop - Bot 2 pattern with outer exception handler"""
    setup_logging()

    logger.info("=" * 60)
    logger.info("WHISKEY RELEASE MONITOR v5")
    logger.info("=" * 60)
    logger.info(f"Target URL: {Config.TARGET_URL}")
    logger.info(f"Check Interval: {Config.CHECK_INTERVAL} minutes ({Config.CHECK_INTERVAL * 60:.0f} seconds)")
    logger.info(f"Headless Mode: {Config.HEADLESS}")
    logger.info("=" * 60)

    # Initialize components ONCE and reuse
    storage = ProductStorage(Config.PRODUCTS_FILE)
    notifier = DiscordNotifier(Config.DISCORD_WEBHOOK_URL)

    # Run first check immediately
    logger.info("Running initial check...")
    run_check(storage, notifier, is_first_run=True)

    # Send startup notification
    try:
        current_products = storage.load()
        notifier.send_startup(current_products)
    except Exception as e:
        logger.warning(f"Could not send startup notification: {e}")

    # Main monitoring loop - WITH OUTER EXCEPTION HANDLER (Bot 2 pattern)
    while running:
        try:
            wait_seconds = Config.CHECK_INTERVAL * 60
            logger.info(f"Next check in {Config.CHECK_INTERVAL} minutes...")

            # Sleep in 1-second intervals for responsive shutdown
            for _ in range(int(wait_seconds)):
                if not running:
                    break
                time.sleep(1)

            if not running:
                break

            # Run check
            run_check(storage, notifier)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break

        except Exception as e:
            # CRITICAL: Outer exception handler - Bot 2 has this, v4 didn't
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(60)  # Wait 60 seconds before retrying

    logger.info("Monitor stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
