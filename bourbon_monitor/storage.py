"""Product state management with flicker protection"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from .config import Config, Constants

logger = logging.getLogger(__name__)


class ProductStorage:
    """Manages product state with flicker cooldown"""

    def __init__(self, file_path=None):
        self.file_path = Path(file_path or Config.PRODUCTS_FILE)
        self.state_file = Config.STATE_FILE
        self.recently_seen = {}
        self._load_state()

    def _load_state(self):
        """Load persisted state from disk"""
        try:
            if not self.state_file.exists():
                return

            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.recently_seen = state.get('recently_seen', {})

            # Clean old entries (>24 hours)
            cutoff = time.time() - (24 * 60 * 60)
            self.recently_seen = {k: v for k, v in self.recently_seen.items() if v > cutoff}

            logger.info(f"Loaded state: {len(self.recently_seen)} recently seen products")

        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def _save_state(self):
        """Persist state to disk (atomic write)"""
        try:
            state = {
                'recently_seen': self.recently_seen,
                'saved_at': time.time(),
            }
            tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self.state_file.parent), suffix='.tmp')
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(state, f, indent=2)
            os.rename(tmp_path, str(self.state_file))
        except Exception as e:
            logger.error(f"Error saving state: {e}")

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
        """Save products to JSON file (atomic write)"""
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self.file_path.parent), suffix='.tmp')
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(products, f, indent=2)
            os.rename(tmp_path, str(self.file_path))
            logger.info(f"Saved {len(products)} products to storage")
            self._save_state()
            return True

        except Exception as e:
            logger.error(f"Error saving products: {e}")
            return False

    def get_new_products(self, old_products, new_products):
        """Find new products with flicker protection"""
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
                # Only notify if not seen recently (flicker protection)
                if last_seen == 0:
                    new.append(product)
                elif time_since_seen > Constants.FLICKER_COOLDOWN_SECONDS:
                    new.append(product)
                    logger.info(f"Product reappeared after {time_since_seen/3600:.1f} hours: {product['name']}")
                else:
                    logger.info(f"Skipping flicker for {product['name']} (seen {time_since_seen/60:.0f} min ago)")

        return new

    def get_status_changes(self, old_products, new_products):
        """Find products that changed from coming_soon/lottery/out_of_stock to available"""
        old_by_name = {p['name'].lower(): p for p in old_products}
        changed = []

        for product in new_products:
            name_lower = product['name'].lower()
            if name_lower not in old_by_name:
                continue

            old_status = old_by_name[name_lower].get('status', 'available')
            new_status = product.get('status', 'available')

            if old_status != new_status and new_status == 'available':
                logger.info(f"STATUS CHANGE: {product['name']} {old_status} -> available")
                changed.append(product)

        return changed
