#!/usr/bin/env python3
"""
Enhanced bourbon monitor for FWGS whiskey releases - Fixed version
"""

print("Starting script...")  # Debug line

import time
import hashlib
import logging
import smtplib
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from email.mime.text import MIMEText
import re

# Configuration
CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 60,  # 5 minutes
    'email_user': 'fwgs.bourbon.bot@gmail.com',
    'email_pass': 'REDACTED_GMAIL_APP_PASSWORD',
    'notify_email': ['fwgs.bourbon.bot@gmail.com', 'pyothers215@gmail.com'],
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class BourbonMonitor:
    def __init__(self):
        self.driver = None
        self.last_hash = None
        self.last_products = []
        
    def setup_driver(self):
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def handle_popups(self):
        """Handle age verification and other popups"""
        try:
            time.sleep(2)
            
            try:
                age_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'yes', 'YES'), 'YES')]"))
                )
                age_button.click()
                logger.info("Age verification clicked")
                time.sleep(2)
            except:
                try:
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for button in buttons:
                        if "yes" in button.text.lower():
                            button.click()
                            logger.info("Age verification clicked (alternative method)")
                            time.sleep(2)
                            break
                except:
                    pass
                    
        except Exception as e:
            logger.info("No age verification popup found or already handled")
        
        try:
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except:
            pass
    
    def get_bourbon_products(self):
        """Extract bourbon products using a direct approach"""
        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            self.handle_popups()
            
            time.sleep(5)
            
            # Scroll to load content
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            products = []
            seen_products = set()
            
            # Try common product selectors
            product_selectors = [
                "div[class*='product-tile']",
                "div[class*='product-card']",
                "div[class*='product-item']",
                "article[class*='product']",
                "div[class*='tile']",
                "div[class*='card']",
                "li[class*='product']",
                "div[data-product]",
                "a[href*='/product/']"
            ]
            
            for selector in product_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Found {len(elements)} potential products with selector: {selector}")
                        
                        for element in elements:
                            try:
                                text = element.text.strip()
                                if not text:
                                    continue
                                
                                if any(term in text.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                    lines = text.split('\n')
                                    
                                    name = ""
                                    price = ""
                                    size = "750ML"
                                    availability = "In Stock"
                                    
                                    for i, line in enumerate(lines):
                                        if not name and any(term in line.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                            name = line.strip()
                                        
                                        if '$' in line:
                                            price_match = re.search(r'\$[\d,]+\.?\d*', line)
                                            if price_match:
                                                price = price_match.group()
                                        
                                        size_match = re.search(r'\d+\s*(?:ML|ml|L|l)', line)
                                        if size_match:
                                            size = size_match.group().upper()
                                        
                                        stock_match = re.search(r'(\d+)\s*(?:available|in stock|left|remaining)', line.lower())
                                        if stock_match:
                                            availability = f"{stock_match.group(1)} In Stock"
                                    
                                    if name and price and name not in seen_products:
                                        product_str = f"{name} | {price} | {size} | {availability}"
                                        products.append(product_str)
                                        seen_products.add(name)
                                        logger.info(f"Found product: {name} - {price}")
                                        
                            except Exception as e:
                                continue
                        
                        if products:
                            break
                            
                except Exception as e:
                    continue
            
            # Fallback: find by price
            if not products:
                logger.info("Trying fallback extraction...")
                price_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '$')]")
                
                for price_elem in price_elements:
                    try:
                        parent = price_elem
                        for _ in range(3):
                            try:
                                parent = parent.find_element(By.XPATH, "..")
                                parent_text = parent.text.strip()
                                
                                if any(term in parent_text.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                    lines = parent_text.split('\n')
                                    
                                    name = ""
                                    price = ""
                                    size = "750ML"
                                    availability = "In Stock"
                                    
                                    for line in lines:
                                        if not name and any(term in line.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                            if len(line) < 100:
                                                name = line.strip()
                                        
                                        if '$' in line and not price:
                                            price_match = re.search(r'\$[\d,]+\.?\d*', line)
                                            if price_match:
                                                price = price_match.group()
                                        
                                        size_match = re.search(r'\d+\s*(?:ML|ml|L|l)', line)
                                        if size_match:
                                            size = size_match.group().upper()
                                        
                                        stock_match = re.search(r'(\d+)\s*(?:available|in stock|left|remaining)', line.lower())
                                        if stock_match:
                                            availability = f"{stock_match.group(1)} In Stock"
                                    
                                    if name and price and name not in seen_products:
                                        name = re.sub(r'\s*\(\d+\)', '', name)
                                        name = name.replace('Add to Cart', '').strip()
                                        
                                        product_str = f"{name} | {price} | {size} | {availability}"
                                        products.append(product_str)
                                        seen_products.add(name)
                                        logger.info(f"Found product via text: {name} - {price}")
                                        break
                                        
                            except:
                                break
                                
                    except Exception as e:
                        continue
            
            products = sorted(list(set(products)))
            logger.info(f"Total unique products found: {len(products)}")
            
            return products
            
        except Exception as e:
            logger.error(f"Error extracting products: {e}")
            return []
    
    def clean_product_text(self, product_text):
        """Format product info with name, price, size, and availability"""
        if '|' in product_text:
            parts = [part.strip() for part in product_text.split('|')]
            parts = [part for part in parts if part]
            
            if len(parts) < 2:
                return f"🥃 {product_text}"
            
            name = parts[0]
            price = parts[1] if len(parts) > 1 else ""
            size = parts[2] if len(parts) > 2 else "750ML"
            availability = parts[3] if len(parts) > 3 else "In Stock"
            
            name = re.sub(r'\s*\(\d+\)', '', name)
            
            result = f"🥃 {name}"
            if price and '$' in price:
                result += f" 💰 {price}"
            if size:
                result += f" 📏 {size}"
            if availability:
                result += f" 📦 {availability}"
            
            return result
        else:
            return f"🥃 {product_text}"
    
    def send_email(self, subject, message):
        try:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = CONFIG['email_user']
            msg['To'] = ', '.join(CONFIG['notify_email']) if isinstance(CONFIG['notify_email'], list) else CONFIG['notify_email']
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(CONFIG['email_user'], CONFIG['email_pass'])
            
            recipients = CONFIG['notify_email'] if isinstance(CONFIG['notify_email'], list) else [CONFIG['notify_email']]
            server.send_message(msg, from_addr=CONFIG['email_user'], to_addrs=recipients)
            
            server.quit()
            logger.info(f"Email sent to {len(recipients)} recipient(s)")
        except Exception as e:
            logger.error(f"Email failed: {e}")
    
    def check_changes(self):
        try:
            if not self.driver:
                self.setup_driver()
            
            logger.info("Checking for bourbon updates...")
            self.driver.get(CONFIG['url'])
            
            products = self.get_bourbon_products()
            
            if not products:
                logger.error("No products found - likely a page loading error")
                
                if self.last_products and len(self.last_products) > 0:
                    logger.error(f"ERROR: Found 0 products but was previously tracking {len(self.last_products)} products")
                    logger.error("Skipping this check to avoid false 'sold out' alerts")
                    
                    try:
                        self.driver.save_screenshot('error_no_products.png')
                        logger.info("Saved error screenshot to error_no_products.png")
                    except:
                        pass
                    
                    return
                else:
                    logger.warning("No products found on first run - will retry next cycle")
                    return
            
            if self.last_products and len(self.last_products) > 0:
                if len(products) < len(self.last_products) * 0.5:
                    logger.warning(f"Found only {len(products)} products but was tracking {len(self.last_products)}")
                    
                    if len(products) < len(self.last_products) * 0.25:
                        logger.error("Lost more than 75% of tracked products - skipping this check")
                        try:
                            self.driver.save_screenshot('error_few_products.png')
                            with open('error_page_source.html', 'w', encoding='utf-8') as f:
                                f.write(self.driver.page_source)
                            logger.info("Saved error screenshot and page source for debugging")
                        except:
                            pass
                        return
            
            current_products_dict = {}
            for product in products:
                parts = product.split(' | ')
                if parts:
                    name = parts[0]
                    current_products_dict[name] = product
            
            print(f"\n🥃 BOURBON INVENTORY UPDATE")
            print(f"📅 {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
            print(f"🔍 Found {len(products)} products available\n")
            
            for i, product in enumerate(sorted(products), 1):
                cleaned_product = self.clean_product_text(product)
                print(f"PRODUCT {i}: {cleaned_product}")
            
            print(f"\n{'=' * 60}")
            
            if self.last_hash is None:
                self.last_hash = "initialized"
                self.last_products = products
                logger.info(f"✅ Initial scan complete - tracking {len(products)} products")
                self.send_email("🥃 Bourbon Monitor Started", 
                               f"🚀 Monitoring started successfully!\n\n📊 Currently tracking {len(products)} products:\n\n" + 
                               "\n".join(f"PRODUCT {i}: {self.clean_product_text(p)}\n" for i, p in enumerate(sorted(products), 1)))
                
            else:
                previous_products_dict = {}
                for product in self.last_products:
                    parts = product.split(' | ')
                    if parts:
                        name = parts[0]
                        previous_products_dict[name] = product
                
                current_names = set(current_products_dict.keys())
                previous_names = set(previous_products_dict.keys())
                
                truly_new = current_names - previous_names
                truly_removed = previous_names - current_names
                
                low_inventory = []
                inventory_changes = []
                
                for name in current_names:
                    current_product = current_products_dict[name]
                    parts = current_product.split(' | ')
                    
                    if len(parts) >= 4:
                        availability = parts[3]
                        stock_match = re.search(r'(\d+)\s*In Stock', availability)
                        
                        if stock_match:
                            stock_count = int(stock_match.group(1))
                            
                            if stock_count < 5:
                                low_inventory.append(current_product)
                            
                            if name in previous_names:
                                previous_product = previous_products_dict[name]
                                prev_parts = previous_product.split(' | ')
                                
                                if len(prev_parts) >= 4:
                                    prev_availability = prev_parts[3]
                                    prev_stock_match = re.search(r'(\d+)\s*In Stock', prev_availability)
                                    
                                    if prev_stock_match:
                                        prev_stock = int(prev_stock_match.group(1))
                                        if stock_count != prev_stock:
                                            change = stock_count - prev_stock
                                            inventory_changes.append({
                                                'name': name,
                                                'previous': prev_stock,
                                                'current': stock_count,
                                                'change': change
                                            })
                
                if inventory_changes:
                    print(f"\n📊 INVENTORY CHANGES:")
                    for change in inventory_changes:
                        symbol = "📈" if change['change'] > 0 else "📉"
                        print(f"{symbol} {change['name']}: {change['previous']} → {change['current']} ({change['change']:+d})")
                    
                    increases = sum(1 for c in inventory_changes if c['change'] > 0)
                    decreases = sum(1 for c in inventory_changes if c['change'] < 0)
                    
                    summary_parts = []
                    if increases:
                        summary_parts.append(f"{increases} increased")
                    if decreases:
                        summary_parts.append(f"{decreases} decreased")
                    
                    summary = f"📊 INVENTORY SUMMARY: {' and '.join(summary_parts)} out of {len(inventory_changes)} products with stock changes"
                    print(summary)
                    logger.info(summary)
                
                if truly_new or truly_removed or low_inventory:
                    print(f"\n🚨 SIGNIFICANT CHANGES DETECTED!")
                    
                    message = f"🥃 BOURBON INVENTORY ALERT\n"
                    message += f"📅 {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
                    
                    email_parts = []
                    
                    if truly_new:
                        print(f"\n🆕 NEW ARRIVALS ({len(truly_new)}):")
                        message += f"🆕 NEW ARRIVALS ({len(truly_new)}):\n\n"
                        email_parts.append("New Arrivals")
                        
                        for i, name in enumerate(sorted(truly_new), 1):
                            product = current_products_dict[name]
                            cleaned = self.clean_product_text(product)
                            print(f"NEW PRODUCT {i}: {cleaned}")
                            message += f"NEW PRODUCT {i}: {cleaned}\n\n"
                    
                    if truly_removed:
                        print(f"\n❌ SOLD OUT ({len(truly_removed)}):")
                        message += f"❌ SOLD OUT ({len(truly_removed)}):\n\n"
                        email_parts.append("Sold Out")
                        
                        for i, name in enumerate(sorted(truly_removed), 1):
                            product = previous_products_dict[name]
                            cleaned = self.clean_product_text(product)
                            print(f"SOLD OUT PRODUCT {i}: {cleaned}")
                            message += f"SOLD OUT PRODUCT {i}: {cleaned}\n\n"
                    
                    if low_inventory:
                        print(f"\n⚠️ LOW INVENTORY ({len(low_inventory)}):")
                        message += f"⚠️ LOW INVENTORY - LESS THAN 5 BOTTLES ({len(low_inventory)}):\n\n"
                        email_parts.append("Low Inventory")
                        
                        for i, product in enumerate(sorted(low_inventory), 1):
                            cleaned = self.clean_product_text(product)
                            print(f"LOW STOCK {i}: {cleaned}")
                            message += f"LOW STOCK {i}: {cleaned}\n\n"
                    
                    message += f"\n📋 COMPLETE CURRENT INVENTORY ({len(products)}):\n\n"
                    for i, p in enumerate(sorted(products), 1):
                        message += f"PRODUCT {i}: {self.clean_product_text(p)}\n\n"
                    
                    subject = "🥃 Bourbon Alert: " + " | ".join(email_parts)
                    self.send_email(subject, message)
                    
                    logger.info(f"🔄 Significant changes: {len(truly_new)} new, {len(truly_removed)} removed, "
                              f"{len(low_inventory)} low stock, {len(inventory_changes)} inventory updates")
                else:
                    if inventory_changes:
                        logger.info(f"✅ No significant changes - {len(inventory_changes)} quantity updates only")
                    else:
                        logger.info("✅ No changes detected")
                
                self.last_products = products
                
        except Exception as e:
            logger.error(f"Check failed: {e}")
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def run(self):
        print("🥃 Starting FWGS Bourbon Monitor...")
        print(f"🌐 Monitoring: {CONFIG['url']}")
        print(f"⏰ Check interval: {CONFIG['check_interval']//60} minutes")
        print(f"📧 Notifications: {', '.join(CONFIG['notify_email']) if isinstance(CONFIG['notify_email'], list) else CONFIG['notify_email']}")
        print("─" * 50)
        
        try:
            while True:
                self.check_changes()
                mins = CONFIG['check_interval'] // 60
                logger.info(f"⏱️  Next check in {mins} minute{'s' if mins != 1 else ''}...")
                time.sleep(CONFIG['check_interval'])
        except KeyboardInterrupt:
            print(f"\n👋 Monitor stopped by user")
            logger.info("Monitor stopped by user")
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    try:
        monitor = BourbonMonitor()
        monitor.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
