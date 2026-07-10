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
status_log = []

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)
    status_log.append(line)
    # Keep only last 100 lines
    if len(status_log) > 100:
        status_log.pop(0)


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
    'div[role="dialog"] button:has-text("Allow essential and optional cookies")',
    'button:has-text("Allow all cookies")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("Agree")',
    'button:has-text("I accept")',
    'button:has-text("OK")',
    'button:has-text("Allow")',
    '[aria-label*="Accept"]',
    '[aria-label*="allow" i]',
    '[aria-label*="cookie" i]',
    'button[id*="accept"]',
    'button[id*="cookie"]',
    'button[class*="accept"]',
    'button[class*="cookie"]',
    'div[role="dialog"] button:last-of-type',
    'div[role="presentation"] button:last-of-type',
    'div[role="alertdialog"] button:last-of-type',
]


def accept_cookies(page):
    """Scan for and click any cookie/consent banner. Non-blocking if none found."""
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

    for text in ["Allow all cookies", "Accept All", "Accept", "Allow"]:
        try:
            btn = page.get_by_role("button", name=text)
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
#  FORM HELPERS — multi-strategy fill / click / select
# ═══════════════════════════════════════════════════════════════════════════

def fill_field(page, selectors, value, label="field"):
    """Try a list of selectors to fill a text input."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=3000)
                loc.first.fill('', timeout=3000)
                loc.first.type(value, delay=random.randint(30, 90))
                log(f"  ✅ {label} = {value}  ({sel})")
                return True
        except:
            continue
    log(f"  ❌ Could not find {label}!")
    return False


def click_button(page, selectors, label="button"):
    """Try a list of selectors to click a button."""
    for sel in selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=5000)
                log(f"  👆 Clicked {label}  ({sel})")
                time.sleep(0.5)
                return True
        except:
            continue
    # Last resort: try by role
    for name in ["Next", "Sign up", "Sign Up", "Continue", "Submit"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=5000)
                log(f"  👆 Clicked {label} via role={name}")
                time.sleep(0.5)
                return True
        except:
            continue
    log(f"  ❌ Could not click {label}!")
    return False


def select_dob(page):
    """
    Fill Instagram's date-of-birth step.
    Instagram uses 3 <select> dropdowns: month, day, year.
    Sometimes they're labeled; sometimes they're just in order.
    """
    # Generate a plausible DOB (18-35 years old)
    year = random.randint(1991, 2008)
    month = random.randint(1, 12)
    day = random.randint(1, 28 if month == 2 else 30)

    month_name = [
        '', 'January','February','March','April','May','June',
        'July','August','September','October','November','December'
    ][month]
    month_abbr = month_name[:3]

    log(f"  🎂 DOB: {month_name} {day}, {year}")

    # ── STRATEGY 1: <select> elements by order (most reliable) ──
    try:
        time.sleep(1)  # let DOB step render fully
        selects = page.locator('select')
        count = selects.count()
        log(f"  🔍 Found {count} <select> elements on DOB page")
        if count >= 3:
            # Usually: [0]=month, [1]=day, [2]=year
            selects.nth(0).select_option(str(month), timeout=3000)
            log(f"  ✅ Month set to {month}")
            time.sleep(0.4)
            selects.nth(1).select_option(str(day), timeout=3000)
            log(f"  ✅ Day set to {day}")
            time.sleep(0.4)
            selects.nth(2).select_option(str(year), timeout=3000)
            log(f"  ✅ Year set to {year}")
            return True
        elif count > 0:
            # Fewer than 3 — try sequentially
            log(f"  ⚠️ Only {count} selects, trying best-effort...")
            for i in range(count):
                try:
                    val = [str(month), str(day), str(year)][i]
                    selects.nth(i).select_option(val, timeout=3000)
                    log(f"  ✅ Select[{i}] set to {val}")
                except:
                    pass
            return count >= 1
    except Exception as e:
        log(f"  ⚠️ Select-by-order: {e}")

    # ── STRATEGY 2: Select by aria-label ──
    month_selectors = [
        'select[aria-label*="month" i]',
        'select[aria-label*="Month"]',
        'select[title*="month" i]',
        'select[name*="month" i]',
        'select[id*="month" i]',
    ]
    day_selectors = [
        'select[aria-label*="day" i]',
        'select[aria-label*="Day"]',
        'select[title*="day" i]',
        'select[name*="day" i]',
        'select[id*="day" i]',
    ]
    year_selectors = [
        'select[aria-label*="year" i]',
        'select[aria-label*="Year"]',
        'select[title*="year" i]',
        'select[name*="year" i]',
        'select[id*="year" i]',
    ]

    def pick_select(selectors_list, value, label):
        for s in selectors_list:
            try:
                el = page.locator(s)
                if el.count() > 0:
                    el.first.select_option(str(value), timeout=3000)
                    return True
            except:
                continue
        return False

    m_ok = pick_select(month_selectors, month, 'month')
    time.sleep(0.2)
    d_ok = pick_select(day_selectors, day, 'day')
    time.sleep(0.2)
    y_ok = pick_select(year_selectors, year, 'year')

    if m_ok and d_ok and y_ok:
        log(f"  ✅ DOB set via aria-label selectors")
        return True

    # ── STRATEGY 3: Try typing the values (some Instagram UIs use text inputs) ──
    # Month as text
    for txt in [month_name, month_abbr, str(month)]:
        if fill_field(page,
            [f'input[aria-label*="month" i]', f'input[aria-label*="Month"]',
             f'input[name*="month" i]', f'input[id*="month" i]'],
            txt, 'month-text'):
            break
    time.sleep(0.2)
    # Day as text
    fill_field(page,
        [f'input[aria-label*="day" i]', f'input[aria-label*="Day"]',
         f'input[name*="day" i]', f'input[id*="day" i]'],
        str(day), 'day-text')
    time.sleep(0.2)
    # Year as text
    fill_field(page,
        [f'input[aria-label*="year" i]', f'input[aria-label*="Year"]',
         f'input[name*="year" i]', f'input[id*="year" i]'],
        str(year), 'year-text')

    log(f"  ⚠️ DOB attempted via text inputs (may need manual intervention)")
    return False


def wait_for_next_step(page, previous_url, timeout=15):
    """Wait for the page URL to change (multi-step form navigation)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            cur = page.url
            if cur != previous_url and 'accounts' in cur:
                log(f"  🔄 Advanced to: {cur[:80]}")
                return True
        except:
            pass
        time.sleep(0.5)
    # Also check if page content changed significantly
    return True  # don't block — might be same URL with different UI


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SIGNUP FLOW
# ═══════════════════════════════════════════════════════════════════════════

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()

        proxy_config = None
        # Only use Tor if socks port is open
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        tor_available = s.connect_ex(('127.0.0.1', 9050)) == 0
        s.close()
        if tor_available:
            proxy_config = {"server": "socks5://127.0.0.1:9050"}
            log("🌐 Using Tor SOCKS5 proxy")
        else:
            log("⚠️  Tor not available — running without proxy")

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

        # ── Generate credentials ──
        email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
        full_name = f"{random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor'])} {random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz'])}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(10, 9999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

        log(f"📋 Generated: name={full_name}  user={username}  email={email}")

        # ═══════════════════════════════════════════════════
        #  STEP 1: Load signup page → enter EMAIL → Next
        # ═══════════════════════════════════════════════════
        log("── Step 1: Email ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/',
                  timeout=30000, wait_until='domcontentloaded')
        accept_cookies(page)

        try:
            page.wait_for_load_state('networkidle', timeout=12000)
        except:
            pass
        accept_cookies(page)
        time.sleep(1)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # Sometimes Instagram shows a "Use email" / "Sign up with email" option first
        for link_text in ["Sign up with email", "Use email", "Email", "Sign up with Email or Phone"]:
            try:
                link = page.get_by_text(link_text, exact=False)
                if link.count() > 0 and link.first.is_visible():
                    link.first.click(timeout=3000)
                    log(f"  👆 Clicked '{link_text}' link")
                    time.sleep(1.5)
                    accept_cookies(page)
                    break
            except:
                continue

        email_ok = fill_field(page, [
            'input[name="emailOrPhone"]',
            'input[aria-label="Mobile Number or Email"]',
            'input[aria-label*="email" i]',
            'input[aria-label*="Email"]',
            'input[type="email"]',
            'input[autocomplete="email"]',
            'input[name="email"]',
        ], email, 'email')

        if not email_ok:
            # Maybe Instagram changed flow — try a more generic approach
            log("  ⚠️ Email field not found, trying generic text input...")
            try:
                inputs = page.locator('input[type="text"]')
                if inputs.count() > 0:
                    inputs.first.fill(email, timeout=5000)
                    log(f"  ✅ email = {email}  (first text input)")
                    email_ok = True
            except:
                pass

        human_delay()
        next_clicked = click_button(page, [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'div[role="button"]:has-text("Next")',
        ], 'Next (step 1)')

        if not next_clicked:
            # Maybe no Next button yet (single-page form or different flow)
            log("  ℹ️  No Next button — may be single-page form, continuing...")

        time.sleep(3)
        accept_cookies(page)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 2: Full Name → Next
        # ═══════════════════════════════════════════════════
        log("── Step 2: Full Name ──")
        fill_field(page, [
            'input[name="fullName"]',
            'input[aria-label="Full Name"]',
            'input[aria-label*="name" i]',
            'input[aria-label*="Name"]',
        ], full_name, 'full name')

        human_delay()
        click_button(page, [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
        ], 'Next (step 2)')

        time.sleep(3)
        accept_cookies(page)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 3: Username → Next
        # ═══════════════════════════════════════════════════
        log("── Step 3: Username ──")
        fill_field(page, [
            'input[name="username"]',
            'input[aria-label="Username"]',
            'input[aria-label*="username" i]',
        ], username, 'username')

        human_delay()
        click_button(page, [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
        ], 'Next (step 3)')

        time.sleep(3)
        accept_cookies(page)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 4: Password → Next
        # ═══════════════════════════════════════════════════
        log("── Step 4: Password ──")
        fill_field(page, [
            'input[name="password"]',
            'input[aria-label="Password"]',
            'input[aria-label*="password" i]',
            'input[type="password"]',
        ], password, 'password')

        human_delay()
        click_button(page, [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
        ], 'Next (step 4)')

        time.sleep(3)
        accept_cookies(page)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 5: Date of Birth → Next
        # ═══════════════════════════════════════════════════
        log("── Step 5: Date of Birth ──")
        select_dob(page)

        human_delay()
        click_button(page, [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Sign up")',
            'button:has-text("Sign Up")',
            'div[role="button"]:has-text("Next")',
        ], 'Next (step 5 - DOB)')

        time.sleep(4)
        accept_cookies(page)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════════
        #  STEP 6: Possible confirmation / email code screen
        # ═══════════════════════════════════════════════════
        # Wait a moment and take final screenshot
        time.sleep(2)
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

        latest_credentials = {
            'email': email,
            'username': username,
            'password': password,
            'full_name': full_name,
        }
        log(f"🏁 FINISHED: {username} / {email}")

        # Rotate Tor if available
        if tor_available:
            try:
                requests.post('http://127.0.0.1:9051', data='SIGNAL NEWNYM', timeout=2)
                log("🔄 Tor circuit rotated")
            except:
                pass

        p.stop()

    except Exception as e:
        log(f"💥 CRASH: {e}")
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
    status_log.clear()
    threading.Thread(target=run_signup, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/credentials')
def creds():
    return jsonify(latest_credentials)


@app.route('/logs')
def logs():
    return jsonify(status_log[-50:])


# ── Helpers ──

def human_delay():
    time.sleep(random.uniform(0.3, 1.0))


if __name__ == '__main__':
    log(f"🚀 STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)
