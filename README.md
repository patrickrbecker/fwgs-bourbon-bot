# fwgs-bourbon-bot

An automated web scraper that monitors the Pennsylvania Fine Wine & Good Spirits (FWGS) whiskey release page for inventory changes and sends email alerts for important updates.
Features

24/7 Automated Monitoring: Runs continuously as a systemd service, checking inventory every 5 minutes
Smart Change Detection: Tracks products by name and distinguishes between minor quantity updates and significant changes
Selective Email Alerts: Only sends notifications for:

New bourbon arrivals
Products that completely sell out
Low inventory warnings (less than 5 bottles remaining)


Multi-Recipient Support: Sends alerts to multiple email addresses
Detailed Logging: Shows all inventory changes in system logs for reference without email spam
Robust Scraping: Uses Selenium with multiple extraction methods to ensure all products are captured
Clean Email Formatting: Mobile-friendly email layout optimized for iPhone viewing

What It Does
The bot scrapes the FWGS whiskey release page, extracting:

Product names
Prices
Bottle sizes
Current stock levels

It maintains a running inventory and compares each scan to detect changes. Minor quantity fluctuations are logged but don't trigger emails, while significant events (new products, sellouts, or critically low stock) generate immediate email alerts.


Make sure you update the following variables. I used gmail:

    'email_user': '<email>',
    'email_pass': '<app password>',
    'notify_email': ['<email_1>', '<email_2>'],
