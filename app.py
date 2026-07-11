import os
import sys
import time
import random
import string
import threading
import socket
import requests
import re
import json
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8080))

latest_screenshot = b''
latest_credentials = {}
status_log = []
lock = threading.Lock()

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)
    with lock:
        status_log.append(line)
        if len(status_log) > 100:
            status_log.pop(0)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIL.TM — Disposable email inbox
# ═══════════════════════════════════════════════════════════════════════════

MAILTM_API = "https://api.mail.tm"

def create_temp_email():
    """Create a disposable email inbox via mail.tm API."""
    try:
        # Generate a random email
        domain_resp = requests.get(f"{MAILTM_API}/domains", timeout=10)
        if domain_resp.status_code != 200:
            log("  ⚠️ Could not fetch mail.tm domains, using mail.tm directly")
            domain = "@mail.tm"
        else:
            domains = domain_resp.json().get("hydra:member", [])
            domain = domains[0]["domain"] if domains else "@mail.tm"

        local_part = ''.join(random.choices(string.ascii_lowercase, k=12))
        email = f"{local_part}{domain}"
        password = "TempPass123!"

        # Create account
        resp = requests.post(f"{MAILTM_API}/accounts", json={
            "address": email,
            "password": password
        }, timeout=10)

        if resp.status_code == 201:
            token_resp = requests.post(f"{MAILTM_API}/token", json={
                "address": email,
                "password": password
            }, timeout=10)
            if token_resp.status_code == 200:
                token = token_resp.json().get("token", "")
                account_id = resp.json().get("id", "")
                log(f"  ✅ Temp email created: {email}")
                return email, token, account_id, password
        else:
            # Fallback to simple mail.tm format
            log(f"  ⚠️ mail.tm API error: {resp.status_code}, using simple format")
            return None, None, None, None
    except Exception as e:
        log(f"  ⚠️ mail.tm error: {e}")
        return None, None, None, None


def check_mailtm_inbox(token, account_id, timeout=60):
    """Poll mail.tm inbox for Instagram verification code."""
    start = time.time()
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{MAILTM_API}/messages", headers=headers, timeout=10)
            if resp.status_code == 200:
                messages = resp.json().get("hydra:member", [])
                for msg in messages:
                    from_addr = msg.get("from", {}).get("address", "")
                    subject = msg.get("subject", "")
                    log(f"  📧 Mail from: {from_addr} subject: {subject}")

                    # Check if from Instagram
                    if "instagram" in from_addr.lower() or "instagram" in subject.lower() or "confirm" in subject.lower() or "code" in subject.lower() or "verify" in subject.lower():
                        # Get full message
                        msg_id = msg.get("id")
                        if msg_id:
                            msg_resp = requests.get(
                                f"{MAILTM_API}/messages/{msg_id}",
                                headers=headers, timeout=10
                            )
                            if msg_resp.status_code == 200:
                                body = msg_resp.json().get("text", "") or ""
                                html_body = msg_resp.json().get("html", "") or []

                                # Extract code from text body
                                codes = re.findall(r'\b(\d{5,6})\b', body)
                                if codes:
                                    log(f"  ✅ Found verification code: {codes[0]}")
                                    return codes[0]

                                # Extract from HTML
                                for part in html_body:
                                    if isinstance(part, str):
                                        codes = re.findall(r'\b(\d{5,6})\b', part)
                                        if codes:
                                            log(f"  ✅ Found verification code in HTML: {codes[0]}")
                                            return codes[0]

                # Delete processed messages
                for msg in messages:
                    try:
                        mid = msg.get("id")
                        if mid:
                            requests.delete(f"{MAILTM_API}/messages/{mid}", headers=headers, timeout=5)
                    except:
                        pass
        except Exception as e:
            log(f"  ⚠️ Mail check error: {e}")

        time.sleep(5)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  COOKIE / CONSENT HANDLING
# ═══════════════════════════════════════════════════════════════════════════

COOKIE_SELECTORS = [
    'button[data-testid="cookie-policy-manage-dialog-accept-button"]',
    'div[role="presentation"] button:has-text("Allow all cookies")',
    'div[role="presentation"] button:has-text("Allow")',
    'div[role="dialog"] button:has-text("Allow all cookies")',
    'div[role="dialog"] button:has-text("Accept All")',
    'div[role="dialog"] button:has-text("Accept")',
    'button:has-text("Allow all cookies")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("Agree")',
    'button:has-text("I accept")',
    'button:has-text("OK")',
    'button:has-text("Allow")',
    '[aria-label*="Accept"]',
    '[aria-label*="allow" i]',
    'button[id*="accept"]',
    'button[class*="accept"]',
    'div[role="dialog"] button:last-of-type',
    'div[role="alertdialog"] button:last-of-type',
]


def accept_cookies(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except:
        pass
    time.sleep(1)

    for selector in COOKIE_SELECTORS:
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                log(f"  🍪 Cookie accepted: {selector}")
                time.sleep(0.5)
                return True
        except:
            continue

    for text in ["Allow all cookies", "Accept All", "Accept", "Allow", "I accept"]:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=3000)
                log(f"  🍪 Cookie accepted via role: {text}")
                time.sleep(0.5)
                return True
        except:
            continue
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  STEALTH
# ═══════════════════════════════════════════════════════════════════════════

def apply_stealth(page):
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : origQuery(p)
    );
    """
    page.add_init_script(stealth_js)


# ═══════════════════════════════════════════════════════════════════════════
#  AD BLOCK
# ═══════════════════════════════════════════════════════════════════════════

BLOCKED = [
    'doubleclick.net', 'googlesyndication.com', 'google-analytics.com',
    'facebook.com/tr/', 'connect.facebook.net', 'analytics.google.com',
    'googletagmanager.com', 'adsystem.amazon.com', 'amazon-adsystem.com',
    'outbrain.com', 'taboola.com', 'scorecardresearch.com',
    'quantserve.com', 'moatads.com', 'adsrvr.org', 'adnxs.com',
    'adsafeprotected.com', 'doubleverify.com', 'iasds.net',
]


def setup_ad_block(page):
    def handler(route):
        if any(d in route.request.url for d in BLOCKED):
            route.abort()
        else:
            route.continue_()
    page.route("**/*", handler)


# ═══════════════════════════════════════════════════════════════════════════
#  FORM HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def human_delay():
    time.sleep(random.uniform(0.5, 1.5))


def fill_field(page, selectors, value, label="field"):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=3000)
                loc.first.fill('', timeout=3000)
                time.sleep(0.2)
                loc.first.type(value, delay=random.randint(30, 90))
                log(f"  ✅ {label} = {value}")
                return True
        except:
            continue
    # Fallback: find matching input by aria/placeholder/name
    try:
        inputs = page.locator('input:visible')
        count = inputs.count()
        for i in range(count):
            try:
                aria = inputs.nth(i).get_attribute('aria-label') or ''
                placeholder = inputs.nth(i).get_attribute('placeholder') or ''
                name = inputs.nth(i).get_attribute('name') or ''
                if label.lower() in (aria + placeholder + name).lower():
                    inputs.nth(i).click(timeout=2000)
                    inputs.nth(i).fill('', timeout=2000)
                    inputs.nth(i).type(value, delay=random.randint(30, 90))
                    log(f"  ✅ {label} = {value} (fallback)")
                    return True
            except:
                continue
    except:
        pass
    log(f"  ❌ Could not find {label}!")
    return False


def click_button(page, selectors, label="button"):
    for sel in selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=5000)
                log(f"  👆 Clicked {label}")
                time.sleep(0.5)
                return True
        except:
            continue
    for name in ["Next", "Sign up", "Sign Up", "Continue", "Submit", "Create account", "Done"]:
        try:
            btn = page.get_by_role("button", name=name, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=5000)
                log(f"  👆 Clicked {label} via role='{name}'")
                time.sleep(0.5)
                return True
        except:
            continue
    log(f"  ❌ Could not click {label}!")
    return False


def click_first_visible_button(page, label="button"):
    try:
        btn = page.locator('button:visible').first
        if btn.count() > 0:
            btn.first.click(timeout=5000)
            log(f"  👆 Clicked {label} (first visible button)")
            time.sleep(0.5)
            return True
    except:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  DATE OF BIRTH
# ═══════════════════════════════════════════════════════════════════════════

def select_dob(page):
    year = random.randint(1991, 2008)
    month = random.randint(1, 12)
    day = random.randint(1, 28 if month == 2 else 30)
    month_name = ['', 'January','February','March','April','May','June',
                  'July','August','September','October','November','December'][month]

    log(f"  🎂 DOB: {month_name} {day}, {year}")
    time.sleep(1.5)
    with lock:
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

    # Strategy 1: <select> dropdowns
    try:
        selects = page.locator('select')
        count = selects.count()
        if count >= 3:
            selects.nth(0).select_option(str(month), timeout=3000)
            time.sleep(0.3)
            selects.nth(1).select_option(str(day), timeout=3000)
            time.sleep(0.3)
            selects.nth(2).select_option(str(year), timeout=3000)
            log(f"  ✅ DOB via select: {month}/{day}/{year}")
            return True
    except:
        pass

    # Strategy 2: By aria-label
    for label, val in [("month", str(month)), ("day", str(day)), ("year", str(year))]:
        for sel in [f'select[aria-label*="{label}" i]', f'select[title*="{label}" i]',
                    f'select[name*="{label}" i]', f'select[id*="{label}" i]']:
            try:
                el = page.locator(sel)
                if el.count() > 0 and el.first.is_visible():
                    el.first.select_option(val, timeout=3000)
                    break
            except:
                continue

    # Strategy 3: Text inputs
    for label, val in [("month", str(month)), ("day", str(day)), ("year", str(year))]:
        for sel in [f'input[aria-label*="{label}" i]', f'input[placeholder*="{label}" i]',
                    f'input[name*="{label}" i]', f'input[id*="{label}" i]']:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=2000)
                    loc.first.fill('', timeout=2000)
                    loc.first.type(val, delay=random.randint(30, 70))
                    break
            except:
                continue
        time.sleep(0.2)

    # Strategy 4: Fill first 3 visible inputs
    try:
        text_inputs = page.locator('input[type="text"]:visible, input:not([type]):visible, input[type="number"]:visible')
        count_ti = text_inputs.count()
        if count_ti >= 3:
            dob_vals = [str(month), str(day), str(year)]
            for i in range(3):
                text_inputs.nth(i).click(timeout=2000)
                text_inputs.nth(i).fill('', timeout=2000)
                text_inputs.nth(i).type(dob_vals[i], delay=random.randint(30, 70))
            log(f"  ✅ DOB via generic inputs: {month}/{day}/{year}")
    except:
        pass

    return True


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SIGNUP FLOW
# ═══════════════════════════════════════════════════════════════════════════

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()

        # Check Tor
        proxy_config = None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        tor_available = s.connect_ex(('127.0.0.1', 9050)) == 0
        s.close()
        if tor_available:
            proxy_config = {"server": "socks5://127.0.0.1:9050"}
            log("🌐 Using Tor SOCKS5 proxy")
        else:
            log("⚠️ Tor not available — running without proxy")

        browser = p.chromium.launch(
            proxy=proxy_config,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-dev-shm-usage', '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-infobars', '--window-size=1366,768',
            ],
            headless=True,
        )

        ctx = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/126.0.0.0 Safari/537.36'
            ),
            locale='en-US',
            timezone_id='America/New_York',
            color_scheme='light',
        )

        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        apply_stealth(page)
        setup_ad_block(page)

        # ── Create temp email inbox ──
        log("📧 Creating temp email...")
        email, mail_token, account_id, mail_password = create_temp_email()
        if not email:
            # Fallback to simple format
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
            log(f"  Using simple email: {email}")

        # ── Generate credentials ──
        first_names = ['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese']
        last_names = ['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson']
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(10, 9999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

        log(f"📋 Generated: name={full_name}  user={username}  email={email}")

        # ═══════════════════════════════════════════════════
        #  STEP 1: Load Instagram signup page
        # ═══════════════════════════════════════════════════
        log("── Step 1: Load Instagram signup ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/',
                  timeout=30000, wait_until='domcontentloaded')
        accept_cookies(page)
        try:
            page.wait_for_load_state('networkidle', timeout=12000)
        except:
            pass
        accept_cookies(page)
        time.sleep(2)

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # Detect what fields are visible
        has_email = False
        has_name = False
        for sel in ['input[name="emailOrPhone"]', 'input[type="email"]', 'input[aria-label*="email" i]', 'input[aria-label*="Mobile" i]', 'input[aria-label*="Phone" i]']:
            try:
                if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible():
                    has_email = True; break
            except: pass
        for sel in ['input[name="fullName"]', 'input[aria-label*="name" i]', 'input[aria-label*="Full Name" i]']:
            try:
                if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible():
                    has_name = True; break
            except: pass

        log(f"  🔍 Detected: email={has_email}  name={has_name}")

        if not has_email and not has_name:
            log("  ⚠️ No known fields! Trying first visible input...")
            try:
                first_input = page.locator('input:visible').first
                if first_input.count() > 0:
                    first_input.click(timeout=3000)
                    first_input.fill('', timeout=3000)
                    first_input.type(email, delay=random.randint(30, 90))
                    log(f"  ✅ Filled first input with email")
                    has_email = True
            except: pass
            try:
                btn = page.locator('button:visible').first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    log(f"  👆 Clicked first button")
            except: pass
            time.sleep(2)

        if has_email:
            fill_field(page, [
                'input[name="emailOrPhone"]', 'input[type="email"]',
                'input[aria-label*="email" i]', 'input[aria-label*="Mobile" i]',
                'input[aria-label*="Phone" i]', 'input[placeholder*="email" i]',
                'input[placeholder*="phone" i]',
            ], email, 'email')
            human_delay()
            click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                                'button:has-text("Sign up")', 'button:has-text("Continue")'],
                        'Next (email)')
            time.sleep(3)

        if has_name:
            fill_field(page, ['input[name="fullName"]', 'input[aria-label*="name" i]',
                              'input[aria-label*="Full Name" i]', 'input[placeholder*="name" i]'],
                      full_name, 'full name')
            human_delay()
            click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                                'button:has-text("Continue")'],
                        'Next (name)')
            time.sleep(3)

        accept_cookies(page)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 2: Username
        # ═══════════════════════════════════════════════════
        log("── Step 2: Username ──")
        fill_field(page, ['input[name="username"]', 'input[aria-label="Username"]',
                          'input[aria-label*="username" i]', 'input[placeholder*="username" i]'],
                  username, 'username')
        human_delay()
        click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                            'button:has-text("Continue")', 'button:has-text("Sign up")'],
                    'Next (username)')
        time.sleep(3)
        accept_cookies(page)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 3: Password
        # ═══════════════════════════════════════════════════
        log("── Step 3: Password ──")
        fill_field(page, ['input[name="password"]', 'input[aria-label="Password"]',
                          'input[aria-label*="password" i]', 'input[type="password"]',
                          'input[placeholder*="password" i]'],
                  password, 'password')
        human_delay()
        click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                            'button:has-text("Continue")', 'button:has-text("Sign up")',
                            'button:has-text("Sign Up")', 'button:has-text("Create account")'],
                    'Next (password)')
        time.sleep(4)
        accept_cookies(page)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 4: Date of Birth (if shown)
        # ═══════════════════════════════════════════════════
        log("── Step 4: Date of Birth ──")
        # Check if DOB is on the page
        has_dob = False
        for sel in ['select:visible', 'input[aria-label*="month" i]', 'input[aria-label*="birth" i]',
                    'input[aria-label*="date" i]', 'input[placeholder*="birth" i]']:
            try:
                if page.locator(sel).count() > 0:
                    has_dob = True; break
            except: pass

        if has_dob:
            select_dob(page)
            human_delay()
            click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                                'button:has-text("Continue")', 'button:has-text("Sign up")'],
                        'Next (DOB)')
            time.sleep(3)
            accept_cookies(page)
        else:
            log("  ⏭️ No DOB fields detected, skipping")

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 5: Email verification code
        # ═══════════════════════════════════════════════════
        log("── Step 5: Email Verification ──")

        # Check if we're on a verification page
        on_verify = False
        cur_url = page.url
        if "confirm" in cur_url or "challenge" in cur_url or "verify" in cur_url:
            on_verify = True
            log("  🔍 Verification page detected!")
        else:
            # Check for "enter confirmation code" text
            try:
                body_text = page.locator('body').inner_text()
                if 'code' in body_text.lower() and ('email' in body_text.lower() or 'confirm' in body_text.lower()):
                    on_verify = True
                    log("  🔍 Verification prompt detected!")
            except:
                pass

        verification_code = None
        if on_verify and mail_token:
            log("  📧 Waiting for Instagram verification email...")
            verification_code = check_mailtm_inbox(mail_token, account_id, timeout=45)

        if verification_code:
            log(f"  🔑 Entering verification code: {verification_code}")
            # Try to find the verification code input
            fill_field(page, [
                'input[inputmode="numeric"]', 'input[type="tel"]', 'input[type="text"]',
                'input[aria-label*="code" i]', 'input[aria-label*="confirm" i]',
                'input[placeholder*="code" i]', 'input[name*="code" i]',
            ], verification_code, 'verification code')

            human_delay()
            click_button(page, ['button[type="submit"]', 'button:has-text("Next")',
                                'button:has-text("Confirm")', 'button:has-text("Verify")',
                                'button:has-text("Done")', 'button:has-text("Submit")'],
                        'Verify code')
            time.sleep(4)
        elif on_verify:
            log("  ⚠️ No verification code received")
        else:
            log("  ⏭️ No verification page detected")

        # ═══════════════════════════════════════════════════
        #  FINAL: Check result
        # ═══════════════════════════════════════════════════
        time.sleep(3)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        current_url = page.url
        log(f"📄 Final URL: {current_url[:120]}")

        # Check for success indicators
        is_success = False
        try:
            body_text = page.locator('body').inner_text()
            if "welcome" in body_text.lower() or "let's go" in body_text.lower() or "start exploring" in body_text.lower() or "logged in" in body_text.lower():
                is_success = True
                log("✅ SUCCESS - Account created!")
        except:
            pass

        if "accounts/emailsignup" in current_url or "signup" in current_url:
            log("⚠️ Still on signup page - account may not have been created")
        else:
            is_success = True
            log("✅ Navigated away from signup page - likely success!")

        with lock:
            latest_credentials = {
                'email': email,
                'username': username,
                'password': password,
                'full_name': full_name,
                'status': 'success' if is_success else 'completed',
                'verification_code': verification_code or '',
                'final_url': current_url[:120],
            }

        log(f"🏁 Done: {username} / {email} | success={is_success}")

        # Rotate Tor
        if tor_available:
            try:
                requests.post('http://127.0.0.1:9051', data='SIGNAL NEWNYM', timeout=2)
                log("🔄 Tor circuit rotated")
            except:
                pass

        p.stop()

    except Exception as e:
        log(f"💥 CRASH: {e}")
        import traceback
        log(f"💥 {traceback.format_exc()[-300:]}")
        with lock:
            latest_credentials = {'error': str(e)}


# ═══════════════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/stream')
def stream():
    def gen():
        while True:
            with lock:
                if latest_screenshot:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n'
                           + latest_screenshot + b'\r\n')
            time.sleep(1)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    return jsonify({'alive': True, 'port': PORT, 'log': status_log[-30:]})


@app.route('/create', methods=['POST'])
def create():
    with lock:
        status_log.clear()
    threading.Thread(target=run_signup, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/credentials')
def creds():
    with lock:
        return jsonify(latest_credentials)


@app.route('/logs')
def logs():
    with lock:
        return jsonify(status_log[-50:])


if __name__ == '__main__':
    log(f"🚀 STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)