#!/usr/bin/env python3
"""
Enhanced bourbon monitor for FWGS whiskey releases - Direct and efficient approach
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from email.mime.text import MIMEText
import re

# Configuration
CONFIG = {
    'url': 'https://www.finewineandgoodspirits.com/en/whiskey-release/whiskey-release',
    'check_interval': 300,
    'email_user': '<email>@gmail.com',
    'email_pass': '<app API password>',
    'notify_email': ['<email-1>', '<email-2>'],
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
            # Wait a moment for popups to appear
            time.sleep(2)
            
            # Try to find and click YES for age verification
            try:
                age_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'yes', 'YES'), 'YES')]"))
                )
                age_button.click()
                logger.info("Age verification clicked")
                time.sleep(2)
            except:
                # Try other selectors
                try:
                    # Look for any button with YES text
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
        
        # Close any other popups with ESC
        try:
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except:
            pass
    
    def get_bourbon_products(self):
        """Extract bourbon products using a direct approach"""
        try:
            # Wait for page to load
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            self.handle_popups()
            
            # Give the page time to fully render
            time.sleep(5)
            
            # Scroll to load any lazy-loaded content
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Scroll back up
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            products = []
            seen_products = set()
            
            # Method 1: Look for product tiles/cards - common patterns
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
                                # Get all text from the element
                                text = element.text.strip()
                                if not text:
                                    continue
                                
                                # Check if it contains whiskey-related terms
                                if any(term in text.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                    # Extract product info
                                    lines = text.split('\n')
                                    
                                    # Look for name and price
                                    name = ""
                                    price = ""
                                    size = "750ML"
                                    availability = "In Stock"
                                    
                                    for i, line in enumerate(lines):
                                        # First line with whiskey terms is likely the name
                                        if not name and any(term in line.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                            name = line.strip()
                                        
                                        # Look for price
                                        if '$' in line:
                                            price_match = re.search(r'\$[\d,]+\.?\d*', line)
                                            if price_match:
                                                price = price_match.group()
                                        
                                        # Look for size
                                        size_match = re.search(r'\d+\s*(?:ML|ml|L|l)', line)
                                        if size_match:
                                            size = size_match.group().upper()
                                        
                                        # Look for availability/stock count
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
                            break  # Found products, stop trying other selectors
                            
                except Exception as e:
                    continue
            
            # Method 2: If no products found, try finding by link pattern
            if not products:
                logger.info("Trying link-based extraction...")
                links = self.driver.find_elements(By.TAG_NAME, "a")
                
                for link in links:
                    try:
                        href = link.get_attribute('href') or ''
                        text = link.text.strip()
                        
                        # Check if link points to a product
                        if '/product/' in href and text:
                            # Get parent element for more context
                            parent = link.find_element(By.XPATH, "..")
                            parent_text = parent.text.strip()
                            
                            if any(term in parent_text.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                lines = parent_text.split('\n')
                                
                                name = ""
                                price = ""
                                size = "750ML"
                                availability = "In Stock"
                                
                                for line in lines:
                                    if not name and any(term in line.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                        name = line.strip()
                                    
                                    if '$' in line:
                                        price_match = re.search(r'\$[\d,]+\.?\d*', line)
                                        if price_match:
                                            price = price_match.group()
                                    
                                    size_match = re.search(r'\d+\s*(?:ML|ml|L|l)', line)
                                    if size_match:
                                        size = size_match.group().upper()
                                    
                                    # Look for stock count
                                    stock_match = re.search(r'(\d+)\s*(?:available|in stock|left|remaining)', line.lower())
                                    if stock_match:
                                        availability = f"{stock_match.group(1)} In Stock"
                                
                                if name and price and name not in seen_products:
                                    product_str = f"{name} | {price} | {size} | {availability}"
                                    products.append(product_str)
                                    seen_products.add(name)
                                    logger.info(f"Found product via link: {name} - {price}")
                                    
                    except Exception as e:
                        continue
            
            # Method 3: If still no products, extract all text and parse
            if not products:
                logger.info("Using full text extraction method...")
                
                # Get all elements that contain price
                price_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '$')]")
                
                for price_elem in price_elements:
                    try:
                        # Get surrounding context
                        parent = price_elem
                        for _ in range(3):  # Go up to 3 levels
                            try:
                                parent = parent.find_element(By.XPATH, "..")
                                parent_text = parent.text.strip()
                                
                                if any(term in parent_text.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                    lines = parent_text.split('\n')
                                    
                                    name = ""
                                    price = ""
                                    size = "750ML"
                                    availability = "In Stock"
                                    
                                    # Process lines
                                    for line in lines:
                                        if not name and any(term in line.lower() for term in ['whiskey', 'whisky', 'bourbon', 'rye', 'scotch']):
                                            # Skip if line is too long (likely description)
                                            if len(line) < 100:
                                                name = line.strip()
                                        
                                        if '$' in line and not price:
                                            price_match = re.search(r'\$[\d,]+\.?\d*', line)
                                            if price_match:
                                                price = price_match.group()
                                        
                                        size_match = re.search(r'\d+\s*(?:ML|ml|L|l)', line)
                                        if size_match:
                                            size = size_match.group().upper()
                                        
                                        # Look for stock count
                                        stock_match = re.search(r'(\d+)\s*(?:available|in stock|left|remaining)', line.lower())
                                        if stock_match:
                                            availability = f"{stock_match.group(1)} In Stock"
                                    
                                    if name and price and name not in seen_products:
                                        # Clean up name
                                        name = re.sub(r'\s*\(\d+\)', '', name)  # Remove ratings
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
            
            # Remove duplicates and sort
            products = sorted(list(set(products)))
            
            logger.info(f"Total unique products found: {len(products)}")
            
            # If we found fewer than expected, save debug info
            if len(products) < 7:
                logger.warning(f"Found only {len(products)} products, expected 7")
                try:
                    # Save page source
                    with open('debug_page_source.html', 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    logger.info("Saved page source to debug_page_source.html")
                    
                    # Take screenshot
                    self.driver.save_screenshot('debug_screenshot.png')
                    logger.info("Saved screenshot to debug_screenshot.png")
                except:
                    pass
            
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
            
            # Clean up name
            name = re.sub(r'\s*\(\d+\)', '', name)
            
            # Format nicely without dashes
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
            
            # Send to all recipients
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
                logger.warning("No products found")
                return
            
            # Create content hash
            content = '\n'.join(sorted(products))
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Display current products
            print(f"\n🥃 BOURBON INVENTORY UPDATE")
            print(f"📅 {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
            print(f"🔍 Found {len(products)} products available\n")
            
            for i, product in enumerate(products, 1):
                cleaned_product = self.clean_product_text(product)
                print(f"PRODUCT {i}: {cleaned_product}")
            
            print(f"\n{'=' * 60}")
            
            if self.last_hash is None:
                # First run
                self.last_hash = content_hash
                self.last_products = products
                logger.info(f"✅ Initial scan complete - tracking {len(products)} products")
                self.send_email("🥃 Bourbon Monitor Started", 
                               f"🚀 Monitoring started successfully!\n\n📊 Currently tracking {len(products)} products:\n\n" + 
                               "\n".join(f"PRODUCT {i}: {self.clean_product_text(p)}\n" for i, p in enumerate(products, 1)))
                
            elif content_hash != self.last_hash:
                # Changes detected
                current_set = set(products)
                previous_set = set(self.last_products)
                
                added = current_set - previous_set
                removed = previous_set - current_set
                
                print(f"\n🚨 CHANGES DETECTED!")
                print(f"📈 Previous: {len(self.last_products)} → Current: {len(products)}")
                
                message = f"🥃 BOURBON INVENTORY ALERT\n"
                message += f"📅 {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"
                
                if added:
                    print(f"\n🆕 NEW ARRIVALS ({len(added)}):")
                    message += f"🆕 NEW ARRIVALS ({len(added)}):\n\n"
                    for i, item in enumerate(sorted(added), 1):
                        cleaned_item = self.clean_product_text(item)
                        print(f"NEW PRODUCT {i}: {cleaned_item}")
                        message += f"NEW PRODUCT {i}: {cleaned_item}\n\n"
                
                if removed:
                    print(f"\n❌ NO LONGER AVAILABLE ({len(removed)}):")
                    message += f"❌ NO LONGER AVAILABLE ({len(removed)}):\n\n"
                    for i, item in enumerate(sorted(removed), 1):
                        cleaned_item = self.clean_product_text(item)
                        print(f"SOLD OUT PRODUCT {i}: {cleaned_item}")
                        message += f"SOLD OUT PRODUCT {i}: {cleaned_item}\n\n"
                
                print(f"\n📋 COMPLETE CURRENT INVENTORY ({len(products)}):")
                message += f"📋 COMPLETE CURRENT INVENTORY ({len(products)}):\n\n"
                for i, p in enumerate(products, 1):
                    cleaned_p = self.clean_product_text(p)
                    print(f"PRODUCT {i}: {cleaned_p}")
                    message += f"PRODUCT {i}: {cleaned_p}\n\n"
                
                subject = "🥃 Bourbon Alert: "
                if added and removed:
                    subject += f"{len(added)} New, {len(removed)} Sold Out"
                elif added:
                    subject += f"{len(added)} New Arrival{'s' if len(added) > 1 else ''}!"
                else:
                    subject += f"{len(removed)} Sold Out"
                
                self.send_email(subject, message)
                self.last_hash = content_hash
                self.last_products = products
                logger.info(f"🔄 Changes processed: +{len(added)} new, -{len(removed)} removed")
                
            else:
                logger.info("✅ No changes - inventory unchanged")
                
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
