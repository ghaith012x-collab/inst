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
#  MAIL.TM
# ═══════════════════════════════════════════════════════════════════════════

MAILTM_API = "https://api.mail.tm"

def create_temp_email():
    try:
        domain_resp = requests.get(f"{MAILTM_API}/domains", timeout=10)
        if domain_resp.status_code != 200:
            return None, None, None, None
        domains = domain_resp.json().get("hydra:member", [])
        if not domains:
            return None, None, None, None
        domain = domains[0]["domain"]
        local_part = ''.join(random.choices(string.ascii_lowercase, k=10))
        email = f"{local_part}@{domain}"
        pwd = "TempPass123!"
        log(f"  Using domain: {domain}")
        resp = requests.post(f"{MAILTM_API}/accounts", json={"address": email, "password": pwd}, timeout=10)
        if resp.status_code == 201:
            token_resp = requests.post(f"{MAILTM_API}/token", json={"address": email, "password": pwd}, timeout=10)
            if token_resp.status_code == 200:
                token = token_resp.json().get("token", "")
                account_id = resp.json().get("id", "")
                log(f"  ✅ Temp inbox: {email}")
                return email, token, account_id, pwd
        log(f"  ⚠️ mail.tm API error: {resp.status_code}")
        return None, None, None, None
    except Exception as e:
        log(f"  ⚠️ mail.tm: {e}")
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
                    log(f"  📧 From: {from_addr} | {subject}")
                    if any(k in (from_addr + subject).lower() for k in ['instagram', 'code', 'confirm', 'verify']):
                        msg_id = msg.get("id")
                        if msg_id:
                            m = requests.get(f"{MAILTM_API}/messages/{msg_id}", headers=headers, timeout=10)
                            if m.status_code == 200:
                                data = m.json()
                                body = data.get("text", "") or ""
                                codes = re.findall(r'\b(\d{5,6})\b', body)
                                if codes:
                                    log(f"  ✅ Code: {codes[0]}")
                                    return codes[0]
                                html_parts = data.get("html", []) if isinstance(data.get("html"), list) else [data.get("html", "")]
                                for part in html_parts:
                                    if isinstance(part, str):
                                        codes = re.findall(r'\b(\d{5,6})\b', part)
                                        if codes:
                                            log(f"  ✅ Code in HTML: {codes[0]}")
                                            return codes[0]
        except Exception as e:
            log(f"  ⚠️ mail check: {e}")
        time.sleep(5)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  COOKIE / CONSENT
# ═══════════════════════════════════════════════════════════════════════════

def accept_cookies(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except: pass
    time.sleep(1)
    for text in ["Allow all cookies", "Accept All", "Accept", "Allow", "I accept"]:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=3000)
                log(f"  🍪 Cookie accepted")
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
        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
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
    time.sleep(random.uniform(0.5, 1.2))

def type_slow(locator, text):
    locator.click(timeout=3000)
    time.sleep(0.15)
    locator.fill('', timeout=3000)
    time.sleep(0.1)
    locator.type(text, delay=random.randint(50, 100))

def click_div_button(page, text, label="button"):
    try:
        btn = page.locator(f'div[role="button"]:has-text("{text}"):not([aria-disabled="true"])')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=5000)
            log(f"  👆 Clicked '{text}'")
            time.sleep(0.5)
            return True
    except: pass
    try:
        btn = page.get_by_role("button", name=text, exact=False)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=5000)
            log(f"  👆 Clicked role=button '{text}'")
            time.sleep(0.5)
            return True
    except: pass
    log(f"  ❌ Could not click {label}")
    return False

def page_contains(page, texts):
    try:
        body = page.locator('body').inner_text()
        for t in texts:
            if t.lower() in body.lower():
                return True
    except: pass
    return False


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

        # ── Create temp email inbox ──
        log("📧 Creating temp email inbox...")
        email, mail_token, account_id, mail_password = create_temp_email()
        if not email:
            # Fallback - use a Gmail-like format (won't receive emails but form may accept)
            email = f"{''.join(random.choices(string.ascii_lowercase, k=10))}@gmail.com"
            log(f"  Using gmail format: {email}")

        # ── Generate credentials ──
        first_names = ['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese']
        last_names = ['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson']
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(100, 99999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))

        log(f"📋 Generated: name={full_name}  user={username}  email={email}")

        # ═══════════════════════════════════════════════
        #  LOAD SIGNUP PAGE
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

        # ═══════════════════════════════════════════════
        #  FILL ALL FIELDS BY INDEX
        # ═══════════════════════════════════════════════
        all_inputs = page.locator('input:visible')
        ic = all_inputs.count()
        log(f"  🔍 Found {ic} visible inputs")

        # Input 0: Email
        type_slow(all_inputs.nth(0), email)
        log(f"  ✅ Email: {email}")
        human_delay()

        # Password (type=password)
        for i in range(ic):
            if all_inputs.nth(i).get_attribute('type') == 'password':
                type_slow(all_inputs.nth(i), password)
                log(f"  ✅ Password filled")
                break
        human_delay()

        # Full Name (2nd text input)
        text_found = 0
        for i in range(ic):
            tp = all_inputs.nth(i).get_attribute('type')
            if tp == 'text':
                if text_found == 0:
                    text_found = 1
                elif text_found == 1:
                    type_slow(all_inputs.nth(i), full_name)
                    log(f"  ✅ Name: {full_name}")
                    text_found = 2
                    break
        human_delay()

        # Username (type=search)
        for i in range(ic):
            if all_inputs.nth(i).get_attribute('type') == 'search':
                type_slow(all_inputs.nth(i), username)
                log(f"  ✅ Username: {username}")
                break
        human_delay()

        # ═══════════════════════════════════════════════
        #  FILL DOB
        # ═══════════════════════════════════════════════
        dob_year = random.randint(1991, 2008)
        dob_month = random.randint(1, 12)
        dob_day = random.randint(1, 28 if dob_month == 2 else 30)
        month_name = ['', 'January','February','March','April','May','June',
                      'July','August','September','October','November','December'][dob_month]
        log(f"  🎂 DOB: {month_name} {dob_day}, {dob_year}")

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # Month
        mc = page.locator('[role="combobox"][aria-label="Select Month"]')
        if mc.count() > 0:
            mc.first.click(timeout=3000)
            time.sleep(0.4)
            page.keyboard.type(month_name, delay=30)
            time.sleep(0.3)
            page.keyboard.press('Enter')
            time.sleep(0.3)
            log(f"  ✅ Month: {month_name}")

        # Day
        dc = page.locator('[role="combobox"][aria-label="Select Day"]')
        if dc.count() > 0:
            dc.first.click(timeout=3000)
            time.sleep(0.4)
            page.keyboard.type(str(dob_day), delay=30)
            time.sleep(0.3)
            page.keyboard.press('Enter')
            time.sleep(0.3)
            log(f"  ✅ Day: {dob_day}")

        # Year
        yc = page.locator('[role="combobox"][aria-label="Select Year"]')
        if yc.count() > 0:
            yc.first.click(timeout=3000)
            time.sleep(0.4)
            page.keyboard.type(str(dob_year), delay=30)
            time.sleep(0.3)
            page.keyboard.press('Enter')
            time.sleep(0.3)
            log(f"  ✅ Year: {dob_year}")

        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        # ═══════════════════════════════════════════════
        #  CLICK SUBMIT
        # ═══════════════════════════════════════════════
        log("── Clicking Submit ──")
        click_div_button(page, "Submit", "Submit")

        # ═══════════════════════════════════════════════
        #  WAIT AND CHECK FOR ERRORS/VERIFICATION
        # ═══════════════════════════════════════════════
        time.sleep(6)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        current_url = page.url
        log(f"📄 URL after submit: {current_url[:120]}")

        # ═══════════════════════════════════════════════
        #  HANDLE USERNAME TAKEN ERROR
        # ═══════════════════════════════════════════════
        if page_contains(page, ["not available", "already taken"]):
            log("  ⚠️ Username taken! Generating new one...")
            username = f"{full_name.replace(' ','').lower()}{random.randint(100, 99999)}"
            log(f"  🔄 New: {username}")
            page.evaluate("""(nu) => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    if (inp.type === 'search' || inp.getAttribute('aria-label') === 'Username') {
                        inp.disabled = false;
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, nu);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        break;
                    }
                }
            }""", username)
            log(f"  ✅ JS-set username: {username}")
            human_delay()
            click_div_button(page, "Submit", "Submit (retry)")
            time.sleep(5)
            with lock:
                latest_screenshot = page.screenshot(type='jpeg', quality=70)
            current_url = page.url
            log(f"📄 URL after retry: {current_url[:120]}")

        # ═══════════════════════════════════════════════
        #  DETECT VERIFICATION CHALLENGE
        # ═══════════════════════════════════════════════
        is_verify = page_contains(page, ["confirm it's you", "Help us confirm", "confirmation step", "security check"])
        verification_code = None

        if is_verify:
            log("  🔒 Instagram verification challenge detected!")
            log("  📧 Checking for verification email...")
            verification_code = check_mailtm_inbox(mail_token, account_id, timeout=45) if mail_token else None

            if verification_code:
                log(f"  🔑 Entering code: {verification_code}")
                # Find the code input field (usually a text input in the dialog)
                try:
                    # The verification dialog likely has a text input for the code
                    code_input = page.locator('[role="dialog"] input:visible')
                    if code_input.count() == 0:
                        code_input = page.locator('input:visible')
                    if code_input.count() > 0:
                        type_slow(code_input.first, verification_code)
                        log("  ✅ Code entered")
                        human_delay()
                        # Click Next - should be enabled now
                        click_div_button(page, "Next", "Next after code")
                        time.sleep(5)
                except Exception as e:
                    log(f"  ⚠️ Code entry error: {e}")
            else:
                log("  ⚠️ No verification code received")
                # Try to proceed anyway
                click_div_button(page, "Next", "Next (no code)")
                time.sleep(3)

        # ═══════════════════════════════════════════════
        #  FINAL STATE
        # ═══════════════════════════════════════════════
        time.sleep(4)
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=70)

        current_url = page.url
        log(f"📄 Final URL: {current_url[:120]}")

        is_success = False
        try:
            bt = page.locator('body').inner_text()
            success_kw = ["welcome", "let's go", "start exploring", "logged in", "find people",
                         "save your login", "you're logged in", "signed in"]
            if any(kw in bt.lower() for kw in success_kw):
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
                'verification_triggered': is_verify,
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