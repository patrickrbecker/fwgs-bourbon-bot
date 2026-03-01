"""Configuration and constants"""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR = BASE_DIR / "logs"

    # Ensure directories exist
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    # Target URL
    TARGET_URL = "https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release"

    # Discord webhook (loaded from .env or environment)
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
    
    # Timing
    CHECK_INTERVAL = 0.5  # minutes (30 seconds)
    
    # Browser
    HEADLESS = True
    
    # Data files
    PRODUCTS_FILE = DATA_DIR / "products.json"
    STATE_FILE = DATA_DIR / "state.json"


class Constants:
    """Application constants"""
    # Safety thresholds
    MIN_PRODUCTS_REASONABLE = 1
    MAX_PRODUCTS_REASONABLE = 500
    PRODUCT_DROP_THRESHOLD = 0.5  # 50% drop = likely scrape failure
    
    # Discord
    DISCORD_TIMEOUT = 10
    DISCORD_MAX_RETRIES = 3
    DISCORD_RETRY_DELAY = 2
    
    # Flicker protection - don't re-notify for products seen within this window
    FLICKER_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 hours
    
    # Error notification cooldown
    ERROR_COOLDOWN_SECONDS = 600  # 10 minutes
    
    # Max consecutive failures before exit
    MAX_CONSECUTIVE_FAILURES = 5


def setup_logging():
    """Configure logging"""
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
