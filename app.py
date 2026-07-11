import os, sys, time, random, string, threading, requests, re, json
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
    with lock: status_log.append(line)
    if len(status_log) > 100: status_log.pop(0)

def ss(page):
    with lock:
        global latest_screenshot
        try: latest_screenshot = page.screenshot(type='jpeg', quality=70)
        except: pass

def apply_stealth(page):
    stealth_js = """\n    Object.defineProperty(navigator, 'webdriver', {get: () => false});\n    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});\n    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});\n    window.chrome = {runtime: {}};\n    const origQuery = window.navigator.permissions.query;\n    window.navigator.permissions.query = (p) => (\n        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)\n    );\n    try { delete navigator.__proto__.webdriver; } catch(e) {}\n    """
    page.add_init_script(stealth_js)

def create_temp_email():
    """Create a disposable email via mail.tm API."""
    try:
        r = requests.get("https://api.mail.tm/domains", timeout=10)
        if r.status_code != 200: return None, None, None
        domains = r.json().get("hydra:member", [])
        if not domains: return None, None, None
        domain = domains[0]["domain"]
        local = ''.join(random.choices(string.ascii_lowercase, k=10))
        email = f"{local}@{domain}"
        pwd = "TempAcc123!"
        r = requests.post("https://api.mail.tm/accounts", json={"address": email, "password": pwd}, timeout=10)
        if r.status_code == 201:
            r2 = requests.post("https://api.mail.tm/token", json={"address": email, "password": pwd}, timeout=10)
            if r2.status_code == 200:
                token = r2.json().get("token", "")
                log(f"  ✅ Temp inbox: {email}")
                return email, token, pwd
    except Exception as e:
        log(f"  ⚠️ mail.tm: {e}")
    return None, None, None

def check_inbox(token, timeout=60):
    """Poll mail.tm inbox for Instagram verification code."""
    start = time.time()
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() - start < timeout:
        try:
            r = requests.get("https://api.mail.tm/messages", headers=headers, timeout=10)
            if r.status_code == 200:
                msgs = r.json().get("hydra:member", [])
                for msg in msgs:
                    frm = msg.get("from", {}).get("address", "")
                    subj = msg.get("subject", "")
                    log(f"  📧 From: {frm} | {subj}")
                    if any(k in (frm+subj).lower() for k in ['instagram', 'code', 'confirm', 'verify']):
                        mid = msg.get("id")
                        if mid:
                            m = requests.get(f"https://api.mail.tm/messages/{mid}", headers=headers, timeout=10)
                            if m.status_code == 200:
                                data = m.json()
                                body = data.get("text", "") or ""
                                codes = re.findall(r'\b(\d{5,6})\b', body)
                                if codes:
                                    log(f"  ✅ Code: {codes[0]}")
                                    return codes[0]
                                html = data.get("html", []) if isinstance(data.get("html"), list) else [data.get("html", "")]
                                for part in html:
                                    if isinstance(part, str):
                                        codes = re.findall(r'\b(\d{5,6})\b', part)
                                        if codes:
                                            log(f"  ✅ Code in HTML: {codes[0]}")
                                            return codes[0]
        except Exception as e:
            log(f"  ⚠️ inbox check: {e}")
        time.sleep(5)
    return None

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        log("🌐 Starting browser...")

        browser = p.chromium.launch(
            proxy=None,
            args=['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage',
                  '--disable-gpu','--disable-blink-features=AutomationControlled',
                  '--disable-infobars','--window-size=1366,768'],
            headless=True,
        )

        ctx = browser.new_context(
            viewport={'width':1366,'height':768},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            locale='en-US', timezone_id='America/New_York', color_scheme='light',
        )

        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        apply_stealth(page)

        # ─── CREATE TEMP EMAIL ───
        log("📧 Creating temp email inbox...")
        email, mail_token, mail_pwd = create_temp_email()

        if not email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@gmail.com"
            log(f"  Using gmail: {email}")

        # ─── GEN CREDS ───
        fn = random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese'])
        ln = random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson'])
        full_name = f"{fn} {ln}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(100,99999)}"
        password = ''.join(random.choices(string.ascii_letters+string.digits+'!@#$', k=14))
        log(f"📋 name={full_name} user={username} email={email}")

        # ─── LOAD PAGE ───
        log("── Loading Instagram signup ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(3)
        ss(page)

        # Accept cookies
        for text in ["Allow all cookies","Accept All","Accept","Allow","I accept"]:
            try:
                btn = page.get_by_role("button", name=text, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=3000)
                    log("  🍪 Cookie accepted")
                    time.sleep(0.5)
                    break
            except: continue
        time.sleep(2)
        ss(page)

        # Get CSRF
        csrf = page.evaluate("() => (document.cookie.match(/csrftoken=([^;]+)/)||[])[1] || ''")
        log(f"  🔑 CSRF: {csrf[:20]}...")

        # ─── FILL FIELDS ───
        inputs = page.locator('input:visible')
        ic = inputs.count()
        log(f"  🔍 {ic} visible inputs")

        def type_slow(el, text):
            el.click(timeout=5000)
            time.sleep(0.2)
            el.fill('', timeout=3000)
            time.sleep(0.15)
            el.type(text, delay=random.randint(50,100))

        type_slow(inputs.nth(0), email)
        log(f"  ✅ Email: {email}")
        time.sleep(random.uniform(0.5,1.2))

        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'password':
                type_slow(inputs.nth(i), password)
                log(f"  ✅ Password filled")
                break
        time.sleep(random.uniform(0.5,1.2))

        tf = 0
        for i in range(ic):
            tp = inputs.nth(i).get_attribute('type')
            if tp == 'text':
                if tf == 0: tf = 1
                elif tf == 1:
                    type_slow(inputs.nth(i), full_name)
                    log(f"  ✅ Name: {full_name}")
                    tf = 2; break
        time.sleep(random.uniform(0.5,1.2))

        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'search':
                type_slow(inputs.nth(i), username)
                log(f"  ✅ Username: {username}")
                break
        time.sleep(random.uniform(0.5,1.2))
        ss(page)

        # ─── DOB ───
        dy = random.randint(1991, 2005)
        dm = random.randint(1, 12)
        dd = random.randint(1, 28 if dm == 2 else 30)
        mn = ['','January','February','March','April','May','June',
              'July','August','September','October','November','December'][dm]
        log(f"  🎂 DOB: {mn} {dd}, {dy}")
        ss(page)

        for label, val in [("Select Month", mn), ("Select Day", str(dd)), ("Select Year", str(dy))]:
            cb = page.locator(f'[role=\"combobox\"][aria-label=\"{label}\"]')
            if cb.count() > 0:
                cb.first.click(timeout=3000)
                time.sleep(0.4)
                page.keyboard.type(val, delay=random.randint(30,60))
                time.sleep(0.3)
                page.keyboard.press('Enter')
                time.sleep(0.3)
                log(f"  ✅ {label.split()[1]}: {val}")
        ss(page)

        # ─── SUBMIT VIA API ───
        log("── Submitting via API ──")
        ts = int(time.time())
        enc_pwd = f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{password}"

        result = page.evaluate("""(args) => {
            const [csrf, email, username, enc_pwd, full_name, day, month, year] = args;
            const fd = new URLSearchParams();
            fd.append('email', email);
            fd.append('enc_password', enc_pwd);
            fd.append('username', username);
            fd.append('first_name', full_name.split(' ')[0]);
            fd.append('day', day);
            fd.append('month', month);
            fd.append('year', year);
            fd.append('client_id', '');
            fd.append('seamless_login_enabled', '1');
            fd.append('tos_version', 'row');
            return fetch('/api/v1/web/accounts/web_create_ajax/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                body: fd, credentials: 'same-origin',
            }).then(r => r.json().then(b => ({status: r.status, body: b})).catch(() =>
                r.text().then(t => ({status: r.status, body: t}))
            ));
        }""", [csrf, email, username, enc_pwd, full_name, str(dd), str(dm), str(dy)])

        log(f"  📡 API: {result['status']}")
        if isinstance(result['body'], dict):
            log(f"    account_created: {result['body'].get('account_created', '?')}")
            errors = result['body'].get('errors', {})
            if errors:
                for k, v in errors.items():
                    log(f"    error {k}: {v}")
            # Check for force_sign_up_code
            if 'force_sign_up_code' in str(errors):
                log("  🔐 Verification code required!")
                code_required = True
            else:
                code_required = False
        else:
            log(f"    body: {str(result['body'])[:200]}")
            code_required = False

        # If code is required and we have a mail token, wait for it
        verification_code = None
        if code_required and mail_token:
            log("  📧 Waiting for verification email...")
            verification_code = check_inbox(mail_token, timeout=50)

        if verification_code:
            log(f"  🔑 Submitting code: {verification_code}")
            code_result = page.evaluate("""(args) => {
                const [csrf, code] = args;
                const fd = new URLSearchParams();
                fd.append('code', code);
                fd.append('device_id', '');
                return fetch('/api/v1/web/accounts/web_create_ajax/confirm_code/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                    body: fd, credentials: 'same-origin',
                }).then(r => r.json().then(b => ({status: r.status, body: b})).catch(() =>
                    r.text().then(t => ({status: r.status, body: t}))
                ));
            }""", [csrf, verification_code])
            log(f"  📡 Code API: {code_result['status']}")
            log(f"    {str(code_result['body'])[:300]}")
            time.sleep(5)

        # ─── USERNAME TAKEN RETRY ───
        for retry in range(5):
            body_text = ""
            try: body_text = page.locator('body').inner_text()
            except: pass
            if "not available" not in body_text and "already taken" not in body_text:
                break
            username = f"{full_name.replace(' ','').lower()}{random.randint(100,99999)}"
            log(f"  ⚠️ Username taken! New: {username}")
            page.evaluate("""(nu) => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    if (inp.type === 'search' || inp.getAttribute('aria-label') === 'Username') {
                        inp.disabled = false;
                        const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        s.call(inp, nu);
                        inp.dispatchEvent(new Event('input', {bubbles:true}));
                        inp.dispatchEvent(new Event('change', {bubbles:true}));
                        break;
                    }
                }
            }""", username)
            time.sleep(1)
            # Re-submit with new username
            ts = int(time.time())
            enc_pwd = f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{password}"
            result = page.evaluate("""(args) => {
                const [csrf, email, username, enc_pwd, day, month, year] = args;
                const fd = new URLSearchParams();
                fd.append('email', email); fd.append('enc_password', enc_pwd);
                fd.append('username', username); fd.append('first_name', '');
                fd.append('day', day); fd.append('month', month); fd.append('year', year);
                fd.append('client_id', ''); fd.append('seamless_login_enabled', '1'); fd.append('tos_version', 'row');
                return fetch('/api/v1/web/accounts/web_create_ajax/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                    body: fd, credentials: 'same-origin',
                }).then(r => r.json().then(b => ({status: r.status, body: b})).catch(() =>
                    r.text().then(t => ({status: r.status, body: t}))
                ));
            }""", [csrf, email, username, enc_pwd, str(dd), str(dm), str(dy)])
            log(f"  📡 API retry {retry+1}: {result['status']}")
            if isinstance(result['body'], dict):
                log(f"    account_created: {result['body'].get('account_created', '?')}")
            if result['status'] == 200 and isinstance(result['body'], dict) and result['body'].get('account_created'):
                log("✅ Account created on retry!")
                break
            time.sleep(5)
            ss(page)

        # ─── FINAL ───
        time.sleep(5)
        ss(page)
        current_url = page.url
        log(f"📄 Final URL: {current_url[:120]}")

        is_success = False
        try:
            bt = page.locator('body').inner_text()
            if any(kw in bt.lower() for kw in ["welcome","let's go","start exploring","logged in","find people","save your login","you're logged in","signed in"]):
                is_success = True
                log("✅ SUCCESS!")
        except: pass

        if "emailsignup" not in current_url and "signup" not in current_url:
            is_success = True
            log("✅ Navigated away!")

        # Also check API result
        if isinstance(result['body'], dict) and result['body'].get('account_created'):
            is_success = True
            log("✅ API confirmed account created!")

        with lock:
            latest_credentials = {
                'email': email, 'username': username, 'password': password,
                'full_name': full_name, 'status': 'success' if is_success else 'completed',
                'verification_code': verification_code or '',
                'final_url': current_url[:120],
            }
        log(f"🏁 Done: {username} | success={is_success}")
        p.stop()

    except Exception as e:
        log(f"💥 CRASH: {e}")
        import traceback
        log(f"💥 {traceback.format_exc()[-300:]}")
        with lock:
            latest_credentials = {'error': str(e)}

# ─── FLASK ───
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
    with lock: status_log.clear()
    threading.Thread(target=run_signup, daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/credentials')
def creds():
    with lock: return jsonify(latest_credentials)

@app.route('/logs')
def logs():
    with lock: return jsonify(status_log[-50:])

if __name__ == '__main__':
    log(f"🚀 STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)