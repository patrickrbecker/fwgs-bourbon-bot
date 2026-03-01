"""Discord webhook notifications"""

import logging
import time
import requests
from datetime import datetime
from .config import Config, Constants

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Sends notifications via Discord webhook"""

    def __init__(self, webhook_url=None):
        self.webhook_url = webhook_url or Config.DISCORD_WEBHOOK_URL
        self._last_request_time = 0
        self._last_error_time = 0

    def _format_price(self, price):
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
        """Send notification for products that just became available"""
        if not products:
            return True

        logger.info(f"Sending NOW AVAILABLE notification for {len(products)} product(s)...")

        message = "**NOW AVAILABLE FOR PURCHASE!**\n\n"

        for product in products:
            name = product.get("name", "Unknown")
            price = self._format_price(product.get("price"))
            availability = product.get("availability", 0)
            url = product.get("url")

            message += f"**{name}**\n"
            message += f"  {price}"
            if availability > 1:
                message += f" | {availability} in stock"
            elif availability == 1:
                message += " | In Stock"
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
            message += f"Currently tracking {len(products)} product(s)\n"
        else:
            message += "System online - no products found yet\n"

        message += f"\nCheck interval: {int(Config.CHECK_INTERVAL * 60)} seconds"
        message += "\n" + datetime.now().strftime("%B %d, %Y at %I:%M %p")

        return self._send_webhook(message)

    def send_error(self, error_msg):
        """Send error notification with rate limiting"""
        now = time.time()
        if now - self._last_error_time < Constants.ERROR_COOLDOWN_SECONDS:
            remaining = int(Constants.ERROR_COOLDOWN_SECONDS - (now - self._last_error_time))
            logger.info(f"Skipping error notification (cooldown: {remaining}s remaining)")
            return True

        self._last_error_time = now
        sanitized = str(error_msg)[:500]
        message = f"**Whiskey Monitor Error**\n\n```{sanitized}```"
        return self._send_webhook(message)

    def _send_webhook(self, message, mention_everyone=False):
        """Send message via Discord webhook with retry"""
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
                time.sleep(Constants.DISCORD_RETRY_DELAY * (2 ** attempt))

        logger.error(f"Failed to send Discord notification after {Constants.DISCORD_MAX_RETRIES} attempts")
        return False
