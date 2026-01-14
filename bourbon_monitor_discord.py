#!/usr/bin/env python3
"""
FWGS Whiskey Release Monitor - OPTIMIZED
With proper asyncio event loop cleanup on crash
"""

import time
import logging
import requests
import signal
import sys
import random
import asyncio
import gc
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 30,  # seconds
    'discord_webhook_url': 'REDACTED_DISCORD_WEBHOOK_URL',
}


# =============================================================================
# EXTRA HTTP HEADERS (Chrome 131 standard headers)
# =============================================================================

EXTRA_HTTP_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}

# =============================================================================
# STEALTH SCRIPTS
# =============================================================================

STEALTH_SCRIPTS = """
// ========== NAVIGATOR PROPERTIES ==========
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
delete navigator.__proto__.webdriver;

// Chrome runtime object
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Realistic plugins array (Chrome PDF plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ];
        plugins.length = 3;
        return plugins;
    }
});

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Hardware concurrency (common value)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// Device memory (common value)
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// ========== WEBGL FINGERPRINT PROTECTION ==========
const getParameterProxyHandler = {
    apply: function(target, thisArg, args) {
        const param = args[0];
        if (param === 37445) {
            return 'Google Inc. (Intel)';
        }
        if (param === 37446) {
            return 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        }
        return target.apply(thisArg, args);
    }
};

const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    const context = originalGetContext.call(this, type, ...args);
    if (context && (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl')) {
        const originalGetParameter = context.getParameter.bind(context);
        context.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
    }
    return context;
};

// ========== CANVAS FINGERPRINT PROTECTION ==========
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    if (this.width > 16 && this.height > 16) {
        const ctx = this.getContext('2d');
        if (ctx) {
            try {
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 20), Math.min(this.height, 20));
                for (let i = 0; i < imageData.data.length; i += 4) {
                    imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + (Math.random() * 2 - 1)));
                }
                ctx.putImageData(imageData, 0, 0);
            } catch(e) {}
        }
    }
    return originalToDataURL.call(this, type);
};

// ========== AUDIO CONTEXT PROTECTION ==========
if (window.AudioContext || window.webkitAudioContext) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
    AudioContext.prototype.createAnalyser = function() {
        const analyser = originalCreateAnalyser.call(this);
        const originalGetFloatFrequencyData = analyser.getFloatFrequencyData.bind(analyser);
        analyser.getFloatFrequencyData = function(array) {
            originalGetFloatFrequencyData(array);
            for (let i = 0; i < array.length; i++) {
                array[i] = array[i] + Math.random() * 0.1;
            }
        };
        return analyser;
    };
}
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
# ASYNCIO EVENT LOOP CLEANUP
# =============================================================================

def cleanup_asyncio_event_loop():
    """
    Properly clean up asyncio event loop after Playwright crash.
    
    This fixes the "Playwright Sync API inside the asyncio loop" error
    by forcibly stopping and replacing the corrupted event loop.
    
    Returns True if cleanup succeeded. If cleanup fails, forces process exit.
    """
    logger.info("Cleaning up asyncio event loop...")
    
    cleanup_failed = False
    
    try:
        # Try to get the current event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop exists, nothing to clean
            logger.info("No event loop to clean")
            return True
        
        # If loop is running, we need to stop it
        if loop.is_running():
            logger.info("Stopping running event loop...")
            loop.stop()
            
            # Give it a moment to stop - multiple attempts
            for i in range(5):
                time.sleep(0.1)
                if not loop.is_running():
                    break
            
            if loop.is_running():
                logger.error("Event loop refused to stop - will force exit")
                cleanup_failed = True
        
        # Cancel all pending tasks (only if loop not running)
        if not cleanup_failed and not loop.is_running():
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.info(f"Cancelling {len(pending)} pending tasks...")
                    for task in pending:
                        task.cancel()
                    time.sleep(0.1)
            except RuntimeError:
                pass
        
        # Close the loop if it's not already closed
        if not loop.is_closed() and not cleanup_failed:
            logger.info("Closing event loop...")
            try:
                loop.close()
            except Exception as e:
                if "running event loop" in str(e).lower():
                    logger.error(f"Cannot close running loop: {e} - will force exit")
                    cleanup_failed = True
                else:
                    logger.warning(f"Error closing loop: {e}")
        
        # If cleanup failed, force exit to let systemd restart us clean
        if cleanup_failed:
            logger.error("Event loop cleanup failed - forcing process exit for clean restart")
            import os
            os._exit(1)
        
        # Create and set a fresh event loop
        logger.info("Creating fresh event loop...")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        # Force garbage collection to clean up any lingering references
        gc.collect()
        
        logger.info("Event loop cleanup complete")
        return True
        
    except Exception as e:
        logger.error(f"Event loop cleanup failed: {e}")
        # Last resort - force exit
        logger.error("Forcing process exit for clean restart")
        import os
        os._exit(1)
# =============================================================================
# BROWSER MANAGER - with proper cleanup
# =============================================================================

class BrowserManager:
    """Manages Playwright browser with proper asyncio cleanup on crash"""

    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._started = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        # If there was an exception, clean up asyncio
        if exc_type is not None:
            cleanup_asyncio_event_loop()
        return False

    def start(self):
        """Launch browser with stealth"""
        logger.info("Starting Playwright browser...")
        
        # Clean up any leftover event loop state before starting
        # This ensures we start fresh even if previous run crashed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                asyncio.set_event_loop(asyncio.new_event_loop())
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        
        self.playwright = sync_playwright().start()
        self._started = True

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
            extra_http_headers=EXTRA_HTTP_HEADERS,
            color_scheme='light',
            device_scale_factor=1,
        )

        self.context.add_init_script(STEALTH_SCRIPTS)
        self.page = self.context.new_page()
        logger.info(f"Browser started (viewport: {viewport_width}x{viewport_height})")

    def stop(self):
        """Clean shutdown with proper error handling for each resource"""
        errors = []

        # Close in reverse order of creation
        if self.page:
            try:
                self.page.close()
            except Exception as e:
                errors.append(f"page: {e}")
            self.page = None

        if self.context:
            try:
                self.context.close()
            except Exception as e:
                errors.append(f"context: {e}")
            self.context = None

        if self.browser:
            try:
                self.browser.close()
            except Exception as e:
                errors.append(f"browser: {e}")
            self.browser = None

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                errors.append(f"playwright: {e}")
            self.playwright = None

        self._started = False

        if errors:
            logger.warning(f"Browser cleanup errors: {', '.join(errors)}")
            # If we had cleanup errors, do asyncio cleanup too
            cleanup_asyncio_event_loop()
        else:
            logger.info("Browser stopped")

    def close_popups(self):
        """Close popups including age gate"""
        try:
            js_close = """
            () => {
                let clicked = new Set();
                let closed = [];

                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    if (clicked.has(btn)) return;
                    const text = (btn.textContent || '').toUpperCase().trim();
                    if ((text === 'YES' || text.includes('I AM 21')) && btn.offsetParent !== null) {
                        btn.click();
                        clicked.add(btn);
                        closed.push('age-gate');
                    }
                });

                document.querySelectorAll('[aria-label*="close" i], [aria-label*="dismiss" i]').forEach(btn => {
                    if (clicked.has(btn)) return;
                    if (btn.offsetParent !== null) {
                        btn.click();
                        clicked.add(btn);
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
            self.page.wait_for_timeout(300)
        except Exception as e:
            logger.debug(f"Popup close: {e}")

    def load_all_products(self):
        """Scroll and wait for products with simple retry"""
        try:
            logger.info("Loading products...")
            
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(2000)
            self.page.evaluate("window.scrollTo(0, 0)")
            
            for i in range(5):
                self.page.wait_for_timeout(2000)
                count = self.page.evaluate("document.querySelectorAll('.card:has([class*=price])').length")
                if count > 0:
                    logger.info(f"Products found: {count} (attempt {i+1})")
                    return 0
                logger.info(f"Waiting... attempt {i+1}")
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(500)
                self.page.evaluate("window.scrollTo(0, 0)")
            
            count = self.page.evaluate("document.querySelectorAll('.card:has([class*=price])').length")
            logger.info(f"Final product count: {count}")
            return 0
        except Exception as e:
            logger.debug(f"Load products error: {e}")
            return 0

    def navigate(self, url):
        """Navigate and prepare page"""
        logger.info(f"Navigating to {url}")
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

        try:
            self.page.wait_for_load_state('networkidle', timeout=3000)
            logger.info("Page stabilized")
        except PlaywrightTimeoutError:
            pass

        self.close_popups()
        self.load_all_products()
        logger.info("Page ready")


# =============================================================================
# PRODUCT SCRAPER - with crash recovery
# =============================================================================

class ProductScraper:
    """Scrapes whiskey products with proper crash recovery"""

    def __init__(self, target_url, headless=True):
        self.target_url = target_url
        self.headless = headless

    def scrape(self):
        """Scrape products with crash recovery"""
        browser = None
        try:
            browser = BrowserManager(self.headless)
            browser.start()
            browser.navigate(self.target_url)
            products = self._extract_products_js(browser)
            filtered = self._filter_whiskey(products)

            if len(filtered) < 3:
                logger.warning(f"Only found {len(filtered)} products - retrying...")
                browser.page.wait_for_timeout(3000)
                browser.page.reload()
                browser.close_popups()
                browser.load_all_products()
                products = self._extract_products_js(browser)
                filtered = self._filter_whiskey(products)

            logger.info(f"Scrape complete: {len(filtered)} whiskey products")
            return filtered
            
        except Exception as e:
            logger.error(f"Scrape error: {e}")
            # Clean up asyncio on any error
            cleanup_asyncio_event_loop()
            return []
            
        finally:
            if browser:
                try:
                    browser.stop()
                except:
                    pass
                # Always clean up asyncio after scrape to ensure fresh state
                cleanup_asyncio_event_loop()

    def fetch_product_urls(self, products):
        """Fetch URLs by clicking products"""
        if not products:
            return products

        logger.info(f"Fetching URLs for {len(products)} product(s)...")
        
        browser = None
        try:
            browser = BrowserManager(self.headless)
            browser.start()
            browser.navigate(self.target_url)

            for product in products:
                try:
                    name = product.get("name", "")
                    escaped_name = name.replace("'", "\\'").replace('"', '\\"')

                    js_click = f"""
                    () => {{
                        const cards = document.querySelectorAll(".card:has([class*=price])");
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
            
        except Exception as e:
            logger.error(f"URL fetch error: {e}")
            cleanup_asyncio_event_loop()
            return products
            
        finally:
            if browser:
                try:
                    browser.stop()
                except:
                    pass
                cleanup_asyncio_event_loop()

    def _extract_products_js(self, browser):
        """Extract products with single JS call"""
        logger.info("Extracting products via JS...")

        js_extract = """
        () => {
            const products = [];
            const cards = document.querySelectorAll(".card:has([class*=price])");

            cards.forEach(card => {
                try {
                    const cardText = card.textContent || '';
                    const cardLower = cardText.toLowerCase();

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
                    const stockMatch = cardLower.match(/(\\d+)\\s*(?:available|in stock)/);
                    if (stockMatch) {
                        availability = parseInt(stockMatch[1]);
                    } else if (cardLower.includes("in stock") || cardLower.includes("available")) {
                        availability = 1;
                    }

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
        self.notifier = DiscordNotifier(CONFIG['discord_webhook_url'])
        self.last_products = {}
        self.stock_history = {}
        self.hot_items = set()
        self.hot_notified = set()
        self.running = True

    def check(self, is_first_run=False):
        """Run a single check"""
        logger.info("=" * 50)
        logger.info(f"Check at {datetime.now().strftime('%I:%M %p')}")

        try:
            scraper = ProductScraper(CONFIG["url"])
            products = scraper.scrape()

            if not products:
                logger.error("No products found - skipping check")
                return False

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
                            if stock > 0 and name_lower not in self.hot_notified:
                                self.hot_notified.add(name_lower)
                                hot_to_notify.append(p)

            # Send notifications
            if new_available:
                new_available = scraper.fetch_product_urls(new_available)
                self.notifier.send_new_available(new_available)
                logger.info(f"NEW AVAILABLE: {len(new_available)}")

            if new_coming_soon:
                new_coming_soon = scraper.fetch_product_urls(new_coming_soon)
                self.notifier.send_coming_soon(new_coming_soon)
                logger.info(f"NEW COMING SOON: {len(new_coming_soon)}")

            if new_lottery:
                new_lottery = scraper.fetch_product_urls(new_lottery)
                self.notifier.send_lottery(new_lottery)
                logger.info(f"NEW LOTTERY: {len(new_lottery)}")

            if now_available:
                now_available = scraper.fetch_product_urls(now_available)
                self.notifier.send_now_available(now_available)
                logger.info(f"NOW AVAILABLE: {len(now_available)}")

            if hot_to_notify:
                self.notifier.send_hot_items(hot_to_notify)
                logger.info(f"HOT ITEMS: {len(hot_to_notify)}")

            if not any([new_available, new_coming_soon, new_lottery, now_available, hot_to_notify]):
                logger.info("No changes detected")

            self.last_products = current
            logger.info("Check complete")
            return True

        except Exception as e:
            logger.error(f"Check failed: {e}")
            # Clean up asyncio on any check failure
            cleanup_asyncio_event_loop()
            return False

    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 50)
        logger.info("WHISKEY RELEASE MONITOR (Optimized)")
        logger.info(f"URL: {CONFIG['url']}")
        logger.info(f"Interval: {CONFIG['check_interval']}s")
        logger.info("=" * 50)

        def shutdown(signum, frame):
            logger.info("Shutdown signal received")
            self.running = False

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        # First check
        logger.info("Running initial check...")
        self.check(is_first_run=True)

        if self.last_products:
            self.notifier.send_startup(list(self.last_products.values()))

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
