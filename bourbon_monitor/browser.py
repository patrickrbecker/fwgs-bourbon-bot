"""Browser management with Playwright + manual stealth scripts"""

import logging
import random
import sys
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Stealth scripts to avoid detection
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
        # Check for unrecoverable asyncio error
        if exc_val and "asyncio" in str(exc_val).lower():
            logger.critical(f"Unrecoverable asyncio error: {exc_val}")
            logger.critical("Exiting for clean restart...")
            sys.exit(1)
        return False

    def start(self):
        """Launch browser with stealth and fresh context"""
        self.playwright = sync_playwright().start()

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
        errors = []

        for name, obj in [("page", self.page), ("context", self.context),
                          ("browser", self.browser), ("playwright", self.playwright)]:
            if obj:
                try:
                    if name == "playwright":
                        obj.stop()
                    else:
                        obj.close()
                except Exception as e:
                    errors.append(f"{name}: {e}")

        if errors:
            logger.warning(f"Browser cleanup errors: {', '.join(errors)}")
        else:
            logger.info("Browser stopped cleanly")

    def close_popups(self):
        """Close popups and age gates"""
        try:
            js_close = """
            () => {
                let clicked = [];

                // Age gate - YES button
                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    const text = (btn.textContent || '').toUpperCase().trim();
                    if ((text === 'YES' || text.includes('I AM 21') || text === 'CONFIRM')
                        && btn.offsetParent !== null) {
                        btn.click();
                        clicked.push('age-gate');
                    }
                });

                // Close buttons by aria-label
                document.querySelectorAll('[aria-label*="close" i], [aria-label*="dismiss" i]').forEach(btn => {
                    if (btn.offsetParent !== null) {
                        btn.click();
                        clicked.push('close-btn');
                    }
                });

                // X buttons
                document.querySelectorAll('button, [role="button"]').forEach(btn => {
                    const text = (btn.textContent || '').trim();
                    if ((text === 'X' || text === 'x' || text === '\u00d7') && btn.offsetParent !== null) {
                        btn.click();
                        clicked.push('x-btn');
                    }
                });

                return clicked.length > 0 ? clicked.join(', ') : 'none';
            }
            """
            result = self.page.evaluate(js_close)
            if result != 'none':
                logger.info(f"Closed popups: {result}")

            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(500)
        except Exception as e:
            logger.warning(f"Popup close error: {e}")

    def load_all_products(self):
        """Click Load More until all products are visible"""
        clicks = 0
        consecutive_misses = 0

        while clicks < 15:
            try:
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(500)

                load_more = self.page.get_by_role("button", name="Load More")
                if load_more.is_visible(timeout=2000):
                    load_more.click()
                    clicks += 1
                    consecutive_misses = 0
                    logger.info(f"Clicked Load More (#{clicks})")
                    self.page.wait_for_timeout(2000)
                else:
                    consecutive_misses += 1
                    if consecutive_misses >= 2:
                        break
            except Exception:
                consecutive_misses += 1
                if consecutive_misses >= 2:
                    break

        if clicks:
            logger.info(f"Loaded all products ({clicks} Load More clicks)")

    def navigate(self, url):
        """Navigate to URL and prepare page"""
        logger.info(f"Navigating to {url}")
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

        # Close any popups
        self.close_popups()

        # Scroll to trigger lazy loading
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.page.wait_for_timeout(2000)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(1000)

        # Load all paginated products
        self.load_all_products()

        logger.info("Page ready")
