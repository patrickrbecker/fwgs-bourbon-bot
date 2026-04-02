"""Browser management with Playwright + manual stealth scripts - OPTIMIZED"""

import logging
import random
from .config import Constants
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# Stealth JS scripts to inject - avoids async issues with playwright-stealth library
STEALTH_SCRIPTS = """
// webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// chrome
window.chrome = { runtime: {} };

// permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32'
});

// hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8
});

// WebGL vendor and renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};
"""


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

        # Randomize viewport slightly to avoid fingerprinting
        viewport_width = 1920 + random.randint(-100, 100)
        viewport_height = 1080 + random.randint(-50, 50)

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

        # Use current Chrome version in user agent
        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': viewport_width, 'height': viewport_height},
            locale='en-US',
            timezone_id='America/New_York',
        )

        # Add stealth script to run before each page navigation
        self.context.add_init_script(STEALTH_SCRIPTS)

        self.page = self.context.new_page()

        logger.info(f"Browser started (viewport: {viewport_width}x{viewport_height})")

    def stop(self):
        """Clean shutdown with proper error handling"""
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

    def _get_product_cards(self):
        """Get product cards using resilient selectors with fallbacks"""
        # Priority order: most likely to work first for this site
        selectors = [
            '.card:has([class*="price"])',
            '.card',
            'article:has([class*="price"]):has([class*="title"])',
            '.product-card',
            '.product-tile',
        ]

        for selector in selectors:
            try:
                cards = self.page.query_selector_all(selector)
                if cards and 5 <= len(cards) <= 150:
                    logger.info(f"Found {len(cards)} products using: {selector}")
                    return cards, selector
            except Exception:
                continue

        logger.error("No product cards found with any selector")
        return [], None

    def close_all_popups(self):
        """Close all popups including email signup and age gate - OPTIMIZED"""
        try:
            logger.info("Closing popups...")

            # Use JavaScript to find and close popups - tracks what was clicked to avoid duplicates
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

            # Press Escape once as additional measure
            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(300)

            return True

        except Exception as e:
            logger.warning(f"Popup close error: {e}")
            return False

    def scroll_to_load_all(self):
        """Scroll page to trigger any lazy-loaded content"""
        try:
            # Quick scroll to bottom and back - triggers lazy loading
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)
            return True
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
            return False

    def navigate_and_prepare(self, url):
        """Navigate and prepare page - OPTIMIZED version"""
        logger.info(f"Navigating to {url}")

        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

        # Quick wait for initial content - reduced from 15s to 3s
        # Site never fully settles due to lazy loading, so don't wait long
        logger.info("Waiting for page to stabilize...")
        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
            logger.info("Page stabilized")
        except PlaywrightTimeoutError:
            # This is expected - site uses lazy loading
            pass

        # Close all popups once
        self.close_all_popups()

        # Quick scroll to trigger any lazy content
        self.scroll_to_load_all()

        # Wait for product cards to render
        try:
            self.page.wait_for_selector('.card:has([class*="price"])', timeout=10000)
            logger.info('Product cards detected')
        except PlaywrightTimeoutError:
            logger.warning('Product cards not found after 10s — may fail extraction')
        self.page.wait_for_timeout(500)

        logger.info("Page ready")
        return True

    def load_all_products(self, max_attempts=2):
        """Ensure all products are loaded - OPTIMIZED version

        The URL already has Nrpp=125 which loads all products at once.
        This method just does a quick scroll to trigger any lazy-loaded images
        and confirms products are visible.
        """
        try:
            logger.info("Loading all products...")

            # Quick scroll to trigger lazy loading
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)

            # Check product count
            cards, selector = self._get_product_cards()
            logger.info(f"Product count: {len(cards)}")

            # Scroll back to top
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)

            logger.info("All products loaded")
            return 0  # No Load More clicks needed

        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return 0
