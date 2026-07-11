import os
import sys
import time
import random
import string
import threading
import requests
import re
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
#  STEALTH
# ═══════════════════════════════════════════════════════════════════════════

def apply_stealth(page):
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
    );
    // Fix webdriver detection
    const newProto = navigator.__proto__;
    delete newProto.webdriver;
    """
    page.add_init_script(stealth_js)


def setup_ad_block(page):
    BLOCKED = [
        'doubleclick.net', 'googlesyndication.com', 'google-analytics.com',
        'facebook.com/tr/', 'connect.facebook.net', 'analytics.google.com',
        'googletagmanager.com', 'adsystem.amazon.com', 'amazon-adsystem.com',
        'outbrain.com', 'taboola.com', 'scorecardresearch.com',
        'quantserve.com', 'moatads.com', 'adsrvr.org', 'adnxs.com',
        'adsafeprotected.com', 'doubleverify.com', 'iasds.net',
    ]
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
    time.sleep(random.uniform(0.5, 1.2))

def type_slow(page, locator, text):
    locator.click(timeout=5000)
    time.sleep(0.2)
    locator.fill('', timeout=3000)
    time.sleep(0.15)
    locator.type(text, delay=random.randint(50, 120))

def click_div_btn(page, text, label="btn"):
    try:
        btn = page.locator(f'div[role="button"]:has-text("{text}"):not([aria-disabled="true"])')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=5000)
            log(f"  👆 '{text}'")
            time.sleep(0.5)
            return True
    except: pass
    try:
        btn = page.get_by_role("button", name=text, exact=False)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=5000)
            log(f"  👆 '{text}'")
            time.sleep(0.5)
            return True
    except: pass
    log(f"  ❌ Could not click {label}")
    return False

def page_has(page, texts):
    try:
        body = page.locator('body').inner_text()
        for t in texts:
            if t.lower() in body.lower():
                return True
    except: pass
    return False

def take_screenshot(page):
    with lock:
        global latest_screenshot
        latest_screenshot = page.screenshot(type='jpeg', quality=70)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SIGNUP FLOW
# ═══════════════════════════════════════════════════════════════════════════

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        log("🌐 Starting browser...")

        browser = p.chromium.launch(
            proxy=None,
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
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            color_scheme='light',
        )

        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        apply_stealth(page)
        setup_ad_block(page)

        # ── Generate credentials ──
        email_local = ''.join(random.choices(string.ascii_lowercase, k=random.randint(8, 15)))
        email = f"{email_local}@gmail.com"
        first_names = ['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese']
        last_names = ['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson']
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(100, 99999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

        log(f"📋 Generated: name={full_name}  user={username}  email={email}")

        # ═══════════════════════════════════════════════
        #  LOAD SIGNUP PAGE
        # ═══════════════════════════════════════════════
        log("── Loading Instagram signup ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/',
                  timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(2)

        # Accept cookies
        for text in ["Allow all cookies", "Accept All", "Accept", "Allow", "I accept"]:
            try:
                btn = page.get_by_role("button", name=text, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=3000)
                    log(f"  🍪 Cookie accepted")
                    time.sleep(0.5)
                    break
            except: continue

        time.sleep(2)
        take_screenshot(page)

        # ═══════════════════════════════════════════════
        #  FILL FIELDS
        # ═══════════════════════════════════════════════
        all_inputs = page.locator('input:visible')
        ic = all_inputs.count()
        log(f"  🔍 Found {ic} visible inputs")

        # 1. Email (input 0)
        type_slow(page, all_inputs.nth(0), email)
        log(f"  ✅ Email: {email}")
        human_delay()

        # 2. Password (type=password)
        for i in range(ic):
            if all_inputs.nth(i).get_attribute('type') == 'password':
                type_slow(page, all_inputs.nth(i), password)
                log(f"  ✅ Password filled")
                break
        human_delay()

        # 3. Full Name (2nd text input)
        text_found = 0
        for i in range(ic):
            tp = all_inputs.nth(i).get_attribute('type')
            if tp == 'text':
                if text_found == 0: text_found = 1
                elif text_found == 1:
                    type_slow(page, all_inputs.nth(i), full_name)
                    log(f"  ✅ Name: {full_name}")
                    text_found = 2
                    break
        human_delay()

        # 4. Username (type=search)
        for i in range(ic):
            if all_inputs.nth(i).get_attribute('type') == 'search':
                type_slow(page, all_inputs.nth(i), username)
                log(f"  ✅ Username: {username}")
                break
        human_delay()

        # ═══════════════════════════════════════════════
        #  FILL DOB - combobox keyboard method
        # ═══════════════════════════════════════════════
        dob_year = random.randint(1991, 2005)
        dob_month = random.randint(1, 12)
        dob_day = random.randint(1, 28 if dob_month == 2 else 30)
        month_name = ['', 'January','February','March','April','May','June',
                      'July','August','September','October','November','December'][dob_month]
        log(f"  🎂 DOB: {month_name} {dob_day}, {dob_year}")
        take_screenshot(page)

        for label, val in [("Select Month", month_name), ("Select Day", str(dob_day)), ("Select Year", str(dob_year))]:
            cb = page.locator(f'[role="combobox"][aria-label="{label}"]')
            if cb.count() > 0:
                cb.first.click(timeout=3000)
                time.sleep(0.4)
                page.keyboard.type(val, delay=random.randint(30, 60))
                time.sleep(0.3)
                page.keyboard.press('Enter')
                time.sleep(0.3)
                log(f"  ✅ {label.split()[1]}: {val}")

        take_screenshot(page)

        # ═══════════════════════════════════════════════
        #  CLICK SUBMIT
        # ═══════════════════════════════════════════════
        log("── Clicking Submit ──")
        click_div_btn(page, "Submit", "Submit")

        # ═══════════════════════════════════════════════
        #  WAIT & CHECK
        # ═══════════════════════════════════════════════
        time.sleep(8)
        take_screenshot(page)

        current_url = page.url
        log(f"📄 URL after submit: {current_url[:120]}")

        # ═══════════════════════════════════════════════
        #  HANDLE USERNAME TAKEN
        # ═══════════════════════════════════════════════
        for retry in range(5):
            if not page_has(page, ["not available", "already taken"]):
                break
            log(f"  ⚠️ Username taken! (retry {retry+1}/5)")
            username = f"{full_name.replace(' ','').lower()}{random.randint(100, 99999)}"
            log(f"  🔄 New: {username}")
            page.evaluate("""(nu) => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    if (inp.type === 'search' || inp.getAttribute('aria-label') === 'Username') {
                        inp.disabled = false;
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, nu);
                        inp.dispatchEvent(new Event('input', {bubbles:true}));
                        inp.dispatchEvent(new Event('change', {bubbles:true}));
                        break;
                    }
                }
            }""", username)
            log(f"  ✅ JS-set: {username}")
            human_delay()
            click_div_btn(page, "Submit", "Retry")
            time.sleep(6)
            take_screenshot(page)
            current_url = page.url
            log(f"📄 URL retry: {current_url[:120]}")

        # ═══════════════════════════════════════════════
        #  HANDLE VERIFICATION CHALLENGE
        # ═══════════════════════════════════════════════
        if page_has(page, ["confirm it's you", "Help us confirm"]):
            log("  🔒 Verification challenge detected!")
            # Try bypass: enable and click Next via JS
            bypassed = page.evaluate("""() => {
                const allBtns = document.querySelectorAll('[role="button"]');
                for (const btn of allBtns) {
                    if (btn.textContent.includes('Next')) {
                        btn.removeAttribute('aria-disabled');
                        btn.setAttribute('tabindex', '0');
                        btn.click();
                        return 'Clicked Next';
                    }
                }
                return 'No Next button found';
            }""")
            log(f"  🔓 Bypass: {bypassed}")
            time.sleep(5)
            take_screenshot(page)
            current_url = page.url
            log(f"📄 URL after bypass: {current_url[:120]}")

            # If still on verification, try to find a code input and submit
            if page_has(page, ["confirm it's you", "Help us confirm"]):
                log("  Still on verification - trying to input code field...")
                # Try setting a dummy 6-digit code
                page.evaluate("""() => {
                    const inputs = document.querySelectorAll('input[type="text"], input[type="tel"]');
                    for (const inp of inputs) {
                        if (inp.offsetParent !== null) {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            setter.call(inp, '123456');
                            inp.dispatchEvent(new Event('input', {bubbles:true}));
                            inp.dispatchEvent(new Event('change', {bubbles:true}));
                            break;
                        }
                    }
                }""")
                time.sleep(1)
                # Try clicking Next again
                page.evaluate("""() => {
                    const allBtns = document.querySelectorAll('[role="button"]');
                    for (const btn of allBtns) {
                        if (btn.textContent.includes('Next')) {
                            btn.removeAttribute('aria-disabled');
                            btn.click();
                            return 'Clicked Next again';
                        }
                    }
                    return 'No Next';
                }""")
                time.sleep(5)
                take_screenshot(page)
                current_url = page.url
                log(f"📄 URL after code: {current_url[:120]}")

        # ═══════════════════════════════════════════════
        #  FINAL STATE
        # ═══════════════════════════════════════════════
        time.sleep(4)
        take_screenshot(page)
        current_url = page.url
        log(f"📄 Final URL: {current_url[:120]}")

        is_success = False
        try:
            bt = page.locator('body').inner_text()
            if any(kw in bt.lower() for kw in ["welcome", "let's go", "start exploring", "logged in", "find people", "save your login", "you're logged in", "signed in"]):
                is_success = True
                log("✅ SUCCESS - Account created!")
        except: pass

        if "emailsignup" in current_url or "signup" in current_url:
            log("⚠️ Still on signup page")
        else:
            is_success = True
            log("✅ Navigated away from signup page!")

        with lock:
            latest_credentials = {
                'email': email,
                'username': username,
                'password': password,
                'full_name': full_name,
                'status': 'success' if is_success else 'completed',
                'final_url': current_url[:120],
            }
        log(f"🏁 Done: {username} / {email} | success={is_success}")
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