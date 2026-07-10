import os
import sys
import time
import random
import string
import threading
import requests
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8080))

latest_screenshot = b''
latest_credentials = {}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ── Cookie Acceptance ──────────────────────────────────────────────────────

COOKIE_SELECTORS = [
    # Instagram-specific cookie/consent selectors (most targeted first)
    'button[data-testid="cookie-policy-manage-dialog-accept-button"]',
    'div[role="presentation"] button:has-text("Allow all cookies")',
    'div[role="presentation"] button:has-text("Allow")',
    'div[role="dialog"] button:has-text("Allow all cookies")',
    'div[role="dialog"] button:has-text("Accept All")',
    'div[role="dialog"] button:has-text("Accept")',
    'div[role="dialog"] button:has-text("Allow essential and optional cookies")',
    # Generic cookie buttons
    'button:has-text("Allow all cookies")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("Agree")',
    'button:has-text("I accept")',
    'button:has-text("OK")',
    'button:has-text("Allow")',
    # By attribute
    '[aria-label*="Accept"]',
    '[aria-label*="allow" i]',
    '[aria-label*="cookie" i]',
    # By id/class patterns
    'button[id*="accept"]',
    'button[id*="cookie"]',
    'button[class*="accept"]',
    'button[class*="cookie"]',
    # Fallback: last button in a dialog is usually the accept button
    'div[role="dialog"] button:last-of-type',
    'div[role="presentation"] button:last-of-type',
    'div[role="alertdialog"] button:last-of-type',
]

def accept_cookies(page, timeout_ms=8000):
    """
    Wait for and auto-accept cookies/consent banners.
    Scans multiple selectors and clicks the first match found.
    Returns True if a banner was found and clicked, False otherwise.
    """
    # First, wait a moment for any cookie banner to render
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except:
        pass

    # Give the banner a moment to appear
    time.sleep(1.5)

    for selector in COOKIE_SELECTORS:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                first = el.first
                if first.is_visible():
                    first.click(timeout=3000)
                    log(f"✅ Cookie banner accepted via: {selector}")
                    time.sleep(0.5)
                    return True
        except Exception:
            continue

    # Try Playwright's get_by_role as a last resort
    for role_text in ["Allow all cookies", "Accept All", "Accept", "Allow"]:
        try:
            btn = page.get_by_role("button", name=role_text)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=3000)
                log(f"✅ Cookie banner accepted via role: {role_text}")
                time.sleep(0.5)
                return True
        except Exception:
            continue

    log("ℹ️  No cookie banner detected (may not be shown this session)")
    return False


# ── Stealth / Anti-Detection ───────────────────────────────────────────────

def apply_stealth(page):
    """Apply stealth patches to reduce bot detection."""
    stealth_js = """
    // Overwrite navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    
    // Overwrite plugins
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    
    // Overwrite languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    
    // Fake chrome runtime
    window.chrome = {runtime: {}};
    
    // Overwrite permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
    );
    """
    page.add_init_script(stealth_js)
    log("🛡️  Stealth patches applied")


# ── Ad / Tracker Blocking ──────────────────────────────────────────────────

BLOCKED_DOMAINS = [
    'googleads.g.doubleclick.net',
    'googlesyndication.com',
    'google-analytics.com',
    'facebook.com/tr/',
    'connect.facebook.net',
    'analytics.google.com',
    'googletagmanager.com',
    'adsystem.amazon.com',
    'advertising.amazon.com',
    'amazon-adsystem.com',
    'outbrain.com',
    'taboola.com',
    'scorecardresearch.com',
    'quantserve.com',
    'moatads.com',
    'adsrvr.org',
    'adnxs.com',
    'adsafeprotected.com',
    'doubleverify.com',
    'iasds.net',
]

def setup_ad_block(page):
    """Block ad and tracking requests."""

    def handler(route):
        url = route.request.url
        if any(domain in url for domain in BLOCKED_DOMAINS):
            route.abort()
        else:
            route.continue_()

    page.route("**/*", handler)
    log("🚫 Ad/tracker blocking enabled")


# ── Flask Routes ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/stream')
def stream():
    def gen():
        while True:
            if latest_screenshot:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + latest_screenshot + b'\r\n')
            time.sleep(1)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    return jsonify({'alive': True, 'port': PORT})


@app.route('/create', methods=['POST'])
def create():
    global latest_screenshot, latest_credentials

    def run():
        global latest_screenshot, latest_credentials
        try:
            from playwright.sync_api import sync_playwright

            p = sync_playwright().start()
            browser = p.chromium.launch(
                proxy={"server": "socks5://127.0.0.1:9050"},
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-infobars',
                    '--window-size=1366,768',
                ],
                headless=True,
            )

            ctx = browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/125.0.0.0 Safari/537.36'
                ),
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},
                color_scheme='light',
            )

            page = ctx.new_page()

            # Auto-dismiss any alert() / confirm() dialogs
            page.on("dialog", lambda d: d.dismiss())

            # Apply stealth and ad blocking
            apply_stealth(page)
            setup_ad_block(page)

            # ── Navigate to Instagram signup ──
            log("🌐 Navigating to Instagram signup...")
            page.goto('https://www.instagram.com/accounts/emailsignup/',
                       timeout=30000, wait_until='domcontentloaded')

            # Accept cookies AS EARLY AS POSSIBLE
            accept_cookies(page)

            # Let the page finish rendering
            try:
                page.wait_for_load_state('networkidle', timeout=15000)
            except:
                log("⚠️  Network did not fully idle, continuing anyway...")

            # Re-check for any late-appearing cookie banners
            accept_cookies(page)

            time.sleep(1)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

            # ── Generate fake credentials ──
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
            name = f"{random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor'])} {random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz'])}"
            username = f"{name.replace(' ','').lower()}{random.randint(10, 9999)}"
            password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

            # ── Fill the signup form ──
            log(f"📝 Filling form: email={email}, name={name}, user={username}")

            # Try multiple selector strategies for each field

            # Email field
            email_selectors = [
                'input[name="emailOrPhone"]',
                'input[aria-label="Mobile Number or Email"]',
                'input[aria-label*="email" i]',
                'input[aria-label*="Email"]',
                'input[type="text"]:first-of-type',
            ]
            for sel in email_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(email, timeout=5000)
                        log(f"  ✅ Email filled via: {sel}")
                        break
                except:
                    continue
            else:
                log("  ❌ Could not find email field!")

            human_delay()

            # Full name field
            name_selectors = [
                'input[name="fullName"]',
                'input[aria-label="Full Name"]',
                'input[aria-label*="name" i]',
                'input[type="text"]:nth-of-type(2)',
            ]
            for sel in name_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(name, timeout=5000)
                        log(f"  ✅ Name filled via: {sel}")
                        break
                except:
                    continue
            else:
                log("  ❌ Could not find name field!")

            human_delay()

            # Username field
            user_selectors = [
                'input[name="username"]',
                'input[aria-label="Username"]',
                'input[aria-label*="username" i]',
                'input[type="text"]:nth-of-type(3)',
            ]
            for sel in user_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(username, timeout=5000)
                        log(f"  ✅ Username filled via: {sel}")
                        break
                except:
                    continue
            else:
                log("  ❌ Could not find username field!")

            human_delay()

            # Password field
            pass_selectors = [
                'input[name="password"]',
                'input[aria-label="Password"]',
                'input[aria-label*="password" i]',
                'input[type="password"]',
            ]
            for sel in pass_selectors:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(password, timeout=5000)
                        log(f"  ✅ Password filled via: {sel}")
                        break
                except:
                    continue
            else:
                log("  ❌ Could not find password field!")

            latest_screenshot = page.screenshot(type='jpeg', quality=70)

            # Accept cookies again (Instagram sometimes shows after filling form)
            accept_cookies(page)

            human_delay()

            # ── Submit ──
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Sign up")',
                'button:has-text("Sign Up")',
                'button:has-text("Next")',
                'div[role="button"]:has-text("Sign up")',
                'button:has-text("Continue")',
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    el = page.locator(sel)
                    if el.count() > 0 and el.first.is_visible():
                        el.first.click(timeout=5000)
                        log(f"  ✅ Form submitted via: {sel}")
                        submitted = True
                        break
                except:
                    continue

            if not submitted:
                log("  ⚠️  No submit button found, trying Enter key...")
                try:
                    page.keyboard.press("Enter")
                    submitted = True
                except:
                    log("  ❌ Could not submit form at all!")

            if submitted:
                # Wait for response
                time.sleep(3)
                # Accept any post-submit cookie prompts
                accept_cookies(page)
                time.sleep(2)

            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            latest_credentials = {
                'email': email,
                'username': username,
                'password': password,
            }
            log(f"✅ Done. Credentials: {username} / {email}")

            # Rotate Tor identity for next session
            try:
                requests.post('http://127.0.0.1:9051', data='SIGNAL NEWNYM', timeout=3)
                log("🔄 Tor circuit rotated")
            except:
                pass

            p.stop()

        except Exception as e:
            log(f"💥 CRASH: {e}")
            latest_credentials = {'error': str(e)}

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/credentials')
def creds():
    return jsonify(latest_credentials)


# ── Helpers ────────────────────────────────────────────────────────────────

def human_delay():
    """Random human-like delay between keystrokes/actions."""
    time.sleep(random.uniform(0.4, 1.2))


if __name__ == '__main__':
    log(f"🚀 STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)
