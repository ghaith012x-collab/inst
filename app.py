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
    stealth_js = """   
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
    );
    try { delete navigator.__proto__.webdriver; } catch(e) {}
    """
    page.add_init_script(stealth_js)

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

        # ─── GEN CREDS ───
        fn = random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese'])
        ln = random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson'])
        full_name = f"{fn} {ln}"
        username = f"{full_name.replace(' ','').lower()}{random.randint(100,99999)}"
        password = ''.join(random.choices(string.ascii_letters+string.digits+'!@#$', k=14))
        # Use phone number format to avoid email verification
        phone = f"+{random.choice(['1','44','49','33','61','81'])}{random.randint(100000000, 999999999)}"
        log(f"📋 name={full_name} user={username} phone={phone[:8]}...")

        # ─── LOAD EMAIL SIGNUP (will switch to phone) ───
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

        # Try to switch to phone if available, otherwise use email
        # First try using phone number in the email field
        type_slow(inputs.nth(0), phone)
        log(f"  ✅ Phone: {phone[:15]}...")
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
            cb = page.locator(f'[role="combobox"][aria-label="{label}"]')
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

        # Try email first (phone may not work on this endpoint)
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
        }""", [csrf, phone, username, enc_pwd, full_name, str(dd), str(dm), str(dy)])

        log(f"  📡 API: {result['status']}")
        if isinstance(result['body'], dict):
            log(f"    account_created: {result['body'].get('account_created', '?')}")
            errors = result['body'].get('errors', {})
            if errors:
                for k, v in errors.items():
                    log(f"    error {k}: {v}")
            # Check for success
            if result['body'].get('account_created'):
                log("✅ ACCOUNT CREATED!")
                is_success = True
            else:
                is_success = False
        else:
            log(f"    body: {str(result['body'])[:200]}")
            is_success = False

        # If email verification is forced, try the phone number approach differently
        # or just accept the result
        if not is_success:
            log("── Trying UI Submit as fallback ──")
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const btn of btns) {
                    if (btn.textContent.includes('Submit')) {
                        btn.click(); return;
                    }
                }
            }""")
            time.sleep(8)
            ss(page)
            
            # Check if phone verification is needed
            body_text = ""
            try: body_text = page.locator('body').inner_text()
            except: pass
            
            if "confirm it's you" in body_text.lower() or "help us confirm" in body_text.lower():
                log("  🔒 Phone verification challenge!")
                # Try to bypass
                page.evaluate("""() => {
                    const btns = document.querySelectorAll('[role="button"]');
                    for (const btn of btns) {
                        if (btn.textContent.includes('Next')) {
                            btn.removeAttribute('aria-disabled');
                            btn.click(); return 'Clicked Next';
                        }
                    }
                    return 'No Next';
                }""")
                time.sleep(5)
                ss(page)

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
            # Resubmit
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const btn of btns) {
                    if (btn.textContent.includes('Submit')) {
                        btn.click(); return;
                    }
                }
            }""")
            time.sleep(8)
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

        with lock:
            latest_credentials = {
                'email': phone, 'username': username, 'password': password,
                'full_name': full_name, 'status': 'success' if is_success else 'completed',
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