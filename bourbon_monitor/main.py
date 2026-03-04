"""Main monitoring loop with robust error handling"""

import logging
import signal
import sys
import time
from datetime import datetime

from .config import Config, Constants, setup_logging
from .scraper import ProductScraper
from .storage import ProductStorage
from .notifier import DiscordNotifier

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
running = True
consecutive_failures = 0


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info("Shutdown signal received, stopping...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def is_unrecoverable_error(error):
    """Check if error requires process restart"""
    error_str = str(error).lower()
    unrecoverable = [
        "asyncio loop",
        "playwright sync api inside the asyncio",
        "event loop is closed",
        "cannot schedule new futures",
    ]
    return any(e in error_str for e in unrecoverable)


def run_check(storage, notifier, is_first_run=False):
    """Execute single monitoring check"""
    global consecutive_failures

    logger.info("=" * 60)
    logger.info(f"WHISKEY MONITOR - {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    logger.info("=" * 60)

    try:
        # Fresh scraper each check
        scraper = ProductScraper(Config.TARGET_URL, headless=Config.HEADLESS)

        # Load previous products
        old_products = storage.load()

        # Scrape current products
        new_products = scraper.scrape()

        # Safety: skip if 0 products but had some before
        if old_products and len(new_products) == 0:
            logger.error(f"Found 0 products but was tracking {len(old_products)} - skipping")
            return False

        # Safety: skip if >50% drop
        if old_products and len(old_products) > 0:
            drop = (len(old_products) - len(new_products)) / len(old_products)
            if drop >= Constants.PRODUCT_DROP_THRESHOLD:
                logger.error(f"Found {len(new_products)} but was tracking {len(old_products)} ({drop*100:.0f}% drop) - skipping")
                return False

        # Detect new products
        new_arrivals = storage.get_new_products(old_products, new_products)

        # Detect status changes (coming_soon/lottery/out_of_stock -> available)
        status_changes = storage.get_status_changes(old_products, new_products)

        # Send notifications (not on first run)
        notification_failed = False
        if not is_first_run:
            if new_arrivals:
                if notifier.send_new_products(new_arrivals):
                    logger.info(f"NEW ARRIVALS: {len(new_arrivals)} product(s)")
                else:
                    logger.error("Failed to send new arrivals notification - NOT saving state")
                    notification_failed = True
            if status_changes:
                if notifier.send_now_available(status_changes):
                    logger.info(f"NOW AVAILABLE: {len(status_changes)} product(s)")
                else:
                    logger.error("Failed to send availability notification - NOT saving state")
                    notification_failed = True
            if not new_arrivals and not status_changes:
                logger.info("No changes detected")
        elif new_arrivals:
            logger.info(f"Establishing baseline with {len(new_arrivals)} product(s)")

        # Only save state if notifications succeeded (or weren't needed)
        if notification_failed:
            logger.warning("Skipping state save - will retry notifications next cycle")
            return False

        storage.save(new_products)

        # Reset failure counter on success
        consecutive_failures = 0

        logger.info("Check complete")
        return True

    except Exception as e:
        consecutive_failures += 1
        logger.error(f"Error during check: {e}", exc_info=True)

        # Check for unrecoverable error
        if is_unrecoverable_error(e):
            logger.critical(f"Unrecoverable error detected: {e}")
            logger.critical("Exiting for clean restart...")
            notifier.send_error(f"Unrecoverable error - restarting: {e}")
            sys.exit(1)

        # Check for too many consecutive failures
        if consecutive_failures >= Constants.MAX_CONSECUTIVE_FAILURES:
            logger.critical(f"Too many consecutive failures ({consecutive_failures})")
            logger.critical("Exiting for clean restart...")
            notifier.send_error(f"Too many failures ({consecutive_failures}) - restarting")
            sys.exit(1)

        # Send error notification (rate limited)
        notifier.send_error(str(e))

        return False


def main():
    """Main monitoring loop"""
    global running

    setup_logging()

    logger.info("=" * 60)
    logger.info("WHISKEY RELEASE MONITOR")
    logger.info("=" * 60)
    logger.info(f"Target: {Config.TARGET_URL}")
    logger.info(f"Check interval: {Config.CHECK_INTERVAL} minutes ({int(Config.CHECK_INTERVAL * 60)} seconds)")
    logger.info("=" * 60)

    # Initialize components
    storage = ProductStorage()
    notifier = DiscordNotifier()

    # First check
    logger.info("Running initial check...")
    run_check(storage, notifier, is_first_run=True)

    # Startup notification
    try:
        current_products = storage.load()
        notifier.send_startup(current_products)
    except Exception as e:
        logger.warning(f"Could not send startup notification: {e}")

    # Main loop
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

            run_check(storage, notifier)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt")
            break

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

            if is_unrecoverable_error(e):
                logger.critical("Unrecoverable error in main loop - exiting")
                sys.exit(1)

            time.sleep(60)

    logger.info("Monitor stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
