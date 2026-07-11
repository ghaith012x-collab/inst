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
#  MAIL.TM — Disposable email inbox
# ═══════════════════════════════════════════════════════════════════════════

MAILTM_API = "https://api.mail.tm"

def create_temp_email():
    try:
        domain_resp = requests.get(f"{MAILTM_API}/domains", timeout=10)
        if domain_resp.status_code != 200:
            return None, None, None, None
        domains = domain_resp.json().get("hydra:member", [])
        domain = domains[0]["domain"] if domains else "@mail.tm"

        local_part = ''.join(random.choices(string.ascii_lowercase, k=12))
        email = f"{local_part}{domain}"
        password = "TempPass123!"

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
                log(f"  ✅ Temp email: {email}")
                return email, token, account_id, password
        return None, None, None, None
    except Exception as e:
        log(f"  ⚠️ mail.tm error: {e}")
        return None, None, None, None


def check_mailtm_inbox(token, account_id, timeout=60):
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

                    if "instagram" in from_addr.lower() or "instagram" in subject.lower() or "confirm" in subject.lower() or "code" in subject.lower():
                        msg_id = msg.get("id")
                        if msg_id:
                            msg_resp = requests.get(f"{MAILTM_API}/messages/{msg_id}", headers=headers, timeout=10)
                            if msg_resp.status_code == 200:
                                body = msg_resp.json().get("text", "") or ""
                                codes = re.findall(r'\b(\d{5,6})\b', body)
                                if codes:
                                    log(f"  ✅ Found code: {codes[0]}")
                                    return codes[0]
                                html_body = msg_resp.json().get("html", "") or []
                                for part in html_body if isinstance(html_body, list) else [html_body]:
                                    if isinstance(part, str):
                                        codes = re.findall(r'\b(\d{5,6})\b', part)
                                        if codes:
                                            log(f"  ✅ Found code in HTML: {codes[0]}")
                                            return codes[0]
                for msg in messages:
                    try:
                        mid = msg.get("id")
                        if mid:
                            requests.delete(f"{MAILTM_API}/messages/{mid}", headers=headers, timeout=5)
                    except: pass
        except Exception as e:
            log(f"  ⚠️ Mail check: {e}")
        time.sleep(5)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  COOKIE / CONSENT
# ═══════════════════════════════════════════════════════════════════════════

COOKIE_SELECTORS = [
    'button[data-testid="cookie-policy-manage-dialog-accept-button"]',
    'button:has-text("Allow all cookies")', 'button:has-text("Accept All")',
    'button:has-text("Accept")', 'button:has-text("Allow")',
    'button:has-text("Agree")', 'button:has-text("I accept")',
    'button:has-text("OK")', '[aria-label*="Accept"]',
    'button[id*="accept"]', 'button[class*="accept"]',
    'div[role="dialog"] button:last-of-type',
]

def accept_cookies(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except: pass
    time.sleep(1)
    for selector in COOKIE_SELECTORS:
        try:
            el = page.locator(selector)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                log(f"  🍪 Cookie accepted")
                time.sleep(0.5)
                return True
        except: continue
    for text in ["Allow all cookies", "Accept All", "Accept", "Allow", "I accept"]:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=3000)
                log(f"  🍪 Cookie accepted via role: {text}")
                time.sleep(0.5)
                return True
        except: continue
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

def type_slow(page, locator, text):
    """Click, clear, and type text slowly like a human."""
    locator.click(timeout=3000)
    time.sleep(0.2)
    locator.fill('', timeout=3000)
    time.sleep(0.1)
    locator.type(text, delay=random.randint(40, 100))

def get_visible_inputs(page):
    """Get all visible text-type inputs on the page."""
    inputs = []
    try:
        all_inputs = page.locator('input:visible')
        for i in range(all_inputs.count()):
            try:
                inp = all_inputs.nth(i)
                tp = inp.get_attribute('type') or 'text'
                aria = inp.get_attribute('aria-label') or ''
                name = inp.get_attribute('name') or ''
                placeholder = inp.get_attribute('placeholder') or ''
                if tp in ['text', 'email', 'password', 'search', 'number', 'tel', None, '']:
                    inputs.append({
                        'index': i,
                        'type': tp,
                        'aria': aria,
                        'name': name,
                        'placeholder': placeholder,
                        'locator': inp,
                    })
            except: pass
    except: pass
    return inputs

def get_visible_buttons(page):
    """Get all visible buttons on the page."""
    buttons = []
    try:
        all_btns = page.locator('button:visible')
        for i in range(all_btns.count()):
            try:
                text = all_btns.nth(i).inner_text()
                buttons.append({'index': i, 'text': text, 'locator': all_btns.nth(i)})
            except: pass
    except: pass
    return buttons


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
    time.sleep(1)

    with lock:
        latest_screenshot = page.screenshot(type='jpeg', quality=70)

    # Strategy 1: <select> dropdowns
    selects = page.locator('select')
    count = selects.count()
    if count >= 3:
        selects.nth(0).select_option(str(month), timeout=3000)
        time.sleep(0.3)
        selects.nth(1).select_option(str(day), timeout=3000)
        time.sleep(0.3)
        selects.nth(2).select_option(str(year), timeout=3000)
        log(f"  ✅ DOB via selects")
        return
    elif count > 0:
        vals = [str(month), str(day), str(year)]
        for i in range(min(count, 3)):
            try:
                selects.nth(i).select_option(vals[i], timeout=3000)
            except: pass
        log(f"  ✅ DOB via {count} selects")
        return

    # Strategy 2: text inputs
    for label, val in [("month", str(month)), ("day", str(day)), ("year", str(year))]:
        for sel in [f'input[aria-label*="{label}" i]', f'input[placeholder*="{label}" i]',
                    f'input[name*="{label}" i]', f'input[id*="{label}" i]']:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    type_slow(page, loc.first, val)
                    break
            except: continue
        time.sleep(0.2)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SIGNUP FLOW
# ═══════════════════════════════════════════════════════════════════════════

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        log("🌐 Running without proxy")

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

        # ── Create temp email ──
        log("📧 Creating temp email...")
        email, mail_token, account_id, mail_password = create_temp_email()
        if not email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
            log(f"  Using simple email: {email}")

        # ── Generate credentials ──
        first_names = ['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese']
        last_names = ['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson']
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(10, 9999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

        log(f"📋 Generated: name={full_name}  user={username}  email={email}")

        # ═══════════════════════════════════════════════
        #  LOAD THE SIGNUP PAGE
        # ═══════════════════════════════════════════════
        log("── Loading Instagram signup page ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/',
                  timeout=30000, wait_until='domcontentloaded')
        accept_cookies(page)
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        accept_cookies(page)
        time.sleep(3)

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # Debug: log all visible inputs and buttons
        inputs = get_visible_inputs(page)
        buttons = get_visible_buttons(page)
        log(f"  🔍 Visible inputs: {len(inputs)}, buttons: {len(buttons)}")
        for inp in inputs:
            log(f"  input: type='{inp['type']}' aria='{inp['aria']}' placeholder='{inp['placeholder']}' name='{inp['name']}'")
        for btn in buttons:
            log(f"  button: '{btn['text'][:50]}'")

        # ═══════════════════════════════════════════════
        #  FILL ALL FIELDS IN ORDER
        # ═══════════════════════════════════════════════
        # Instagram's current signup shows all fields on one page:
        # 1. Email or phone number
        # 2. Full Name
        # 3. Username
        # 4. Password
        # Then a "Sign up" button at the bottom

        # Find the inputs by their aria-labels or placeholder text
        field_filled = {'email': False, 'name': False, 'username': False, 'password': False}

        for inp in inputs:
            aria = inp['aria'].lower()
            ph = inp['placeholder'].lower()
            name = inp['name'].lower()
            loc = inp['locator']

            if not field_filled['email'] and ('email' in aria or 'phone' in aria or 'mobile' in aria or 'email' in ph or 'phone' in ph or 'mobile' in ph):
                type_slow(page, loc, email)
                field_filled['email'] = True
                log(f"  ✅ Email filled: {email}")
            elif not field_filled['name'] and ('name' in aria or 'full name' in aria or 'name' in ph):
                type_slow(page, loc, full_name)
                field_filled['name'] = True
                log(f"  ✅ Name filled: {full_name}")
            elif not field_filled['username'] and ('username' in aria or 'username' in ph):
                type_slow(page, loc, username)
                field_filled['username'] = True
                log(f"  ✅ Username filled: {username}")
            elif not field_filled['password'] and inp['type'] == 'password':
                type_slow(page, loc, password)
                field_filled['password'] = True
                log(f"  ✅ Password filled")
            elif inp['type'] == 'text' and not field_filled['email'] and not field_filled['name'] and not field_filled['username']:
                # First text input - fill with email as fallback
                type_slow(page, loc, email)
                field_filled['email'] = True
                log(f"  ✅ Email filled (fallback): {email}")

        time.sleep(1)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════
        #  CLICK SIGN UP
        # ═══════════════════════════════════════════════
        log("── Clicking Sign Up button ──")

        # Find the submit button
        signup_clicked = False
        for btn in buttons:
            txt = btn['text'].lower()
            if 'sign up' in txt or 'sign' in txt or 'create' in txt or 'submit' in txt or 'next' in txt or 'continue' in txt:
                btn['locator'].click(timeout=5000)
                signup_clicked = True
                log(f"  👆 Clicked: '{btn['text'][:50]}'")
                break

        if not signup_clicked:
            # Try by role
            for name in ["Sign up", "Sign Up", "Create account", "Submit", "Next", "Continue"]:
                try:
                    btn = page.get_by_role("button", name=name, exact=False)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click(timeout=5000)
                        signup_clicked = True
                        log(f"  👆 Clicked via role: {name}")
                        break
                except: pass

        if not signup_clicked:
            log("  ❌ Could not find submit button!")

        # ═══════════════════════════════════════════════
        #  WAIT FOR FORM SUBMISSION
        # ═══════════════════════════════════════════════
        time.sleep(5)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════
        #  CHECK FOR DOB / CONFIRMATION
        # ═══════════════════════════════════════════════
        current_url = page.url
        log(f"📄 URL after submit: {current_url[:120]}")

        # Check if we need DOB
        inputs = get_visible_inputs(page)
        buttons = get_visible_buttons(page)
        log(f"  🔍 After submit - inputs: {len(inputs)}, buttons: {len(buttons)}")

        has_dob = False
        for inp in inputs:
            aria = inp['aria'].lower()
            ph = inp['placeholder'].lower()
            if 'month' in aria or 'day' in aria or 'year' in aria or 'birth' in aria or 'birthday' in aria or 'date' in aria:
                has_dob = True
                break

        if has_dob:
            log("── DOB step detected ──")
            select_dob(page)
            human_delay()
            # Click submit again
            for btn in buttons:
                txt = btn['text'].lower()
                if 'next' in txt or 'sign' in txt or 'submit' in txt or 'continue' in txt:
                    btn['locator'].click(timeout=5000)
                    log(f"  👆 Clicked: '{btn['text'][:50]}'")
                    break
            time.sleep(4)

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════
        #  CHECK FOR VERIFICATION CODE
        # ═══════════════════════════════════════════════
        current_url = page.url
        log(f"📄 URL after DOB: {current_url[:120]}")

        on_verify = False
        if "confirm" in current_url or "challenge" in current_url or "verify" in current_url:
            on_verify = True
            log("  🔍 Verification page detected!")
        else:
            try:
                body_text = page.locator('body').inner_text()
                if 'code' in body_text.lower() and ('email' in body_text.lower() or 'confirm' in body_text.lower()):
                    on_verify = True
                    log("  🔍 Verification prompt detected!")
            except: pass

        verification_code = None
        if on_verify and mail_token:
            log("  📧 Waiting for Instagram verification email...")
            verification_code = check_mailtm_inbox(mail_token, account_id, timeout=45)

        if verification_code:
            log(f"  🔑 Entering code: {verification_code}")
            inputs = get_visible_inputs(page)
            if inputs:
                type_slow(page, inputs[0]['locator'], verification_code)
                log(f"  ✅ Code entered")
            else:
                fill_field_sel = ['input[inputmode="numeric"]', 'input[type="tel"]',
                                  'input[aria-label*="code" i]', 'input[placeholder*="code" i]',
                                  'input:visible']
                for sel in fill_field_sel:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            type_slow(page, loc.first, verification_code)
                            break
                    except: pass

            human_delay()
            buttons = get_visible_buttons(page)
            if buttons:
                buttons[0]['locator'].click(timeout=5000)
                log("  👆 Clicked verify button")
            time.sleep(4)
        elif on_verify:
            log("  ⚠️ No code received")

        # ═══════════════════════════════════════════════
        #  FINAL
        # ═══════════════════════════════════════════════
        time.sleep(3)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        current_url = page.url
        log(f"📄 Final URL: {current_url[:120]}")

        is_success = False
        try:
            bt = page.locator('body').inner_text()
            if any(kw in bt.lower() for kw in ["welcome", "let's go", "start exploring", "logged in", "find people", "save your login"]):
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
                'verification_code': verification_code or '',
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