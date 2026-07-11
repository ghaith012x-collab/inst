import os, sys, time, random, string, threading, requests, re
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
        if len(status_log) > 100: status_log.pop(0)

# ─── STEALTH ───
def apply_stealth(page):
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
    );
    const newProto = navigator.__proto__;
    delete newProto.webdriver;
    """
    page.add_init_script(stealth_js)

# ─── SCREENSHOT ───
def ss(page):
    with lock:
        global latest_screenshot
        try: latest_screenshot = page.screenshot(type='jpeg', quality=70)
        except: pass

# ─── SIGNUP ───
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
        email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@gmail.com"
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

        # ─── ACCEPT COOKIES ───
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

        # ─── GET CSRF TOKEN ───
        csrf_token = ""
        for c in context.cookies():
            if c['name'] == 'csrftoken':
                csrf_token = c['value']
                break
        log(f"  🔑 CSRF: {csrf_token[:20]}...")

        # ─── FILL FIELDS ───
        inputs = page.locator('input:visible')
        ic = inputs.count()
        log(f"  🔍 {ic} visible inputs")

        # Email
        inputs.nth(0).click(timeout=3000)
        time.sleep(0.2)
        inputs.nth(0).fill('', timeout=3000)
        time.sleep(0.1)
        inputs.nth(0).type(email, delay=random.randint(50,100))
        log(f"  ✅ Email: {email}")
        time.sleep(random.uniform(0.5,1.2))

        # Password
        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'password':
                inputs.nth(i).click(timeout=3000)
                time.sleep(0.2)
                inputs.nth(i).fill('', timeout=3000)
                time.sleep(0.1)
                inputs.nth(i).type(password, delay=random.randint(50,100))
                log(f"  ✅ Password filled")
                break
        time.sleep(random.uniform(0.5,1.2))

        # Full Name
        tf = 0
        for i in range(ic):
            tp = inputs.nth(i).get_attribute('type')
            if tp == 'text':
                if tf == 0: tf = 1
                elif tf == 1:
                    inputs.nth(i).click(timeout=3000)
                    time.sleep(0.2)
                    inputs.nth(i).fill('', timeout=3000)
                    time.sleep(0.1)
                    inputs.nth(i).type(full_name, delay=random.randint(50,100))
                    log(f"  ✅ Name: {full_name}")
                    tf = 2
                    break
        time.sleep(random.uniform(0.5,1.2))

        # Username
        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'search':
                inputs.nth(i).click(timeout=3000)
                time.sleep(0.2)
                inputs.nth(i).fill('', timeout=3000)
                time.sleep(0.1)
                inputs.nth(i).type(username, delay=random.randint(50,100))
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

        # ─── SUBMIT VIA FETCH API ───
        # This bypasses UI validation and directly calls Instagram's API
        log("── Submitting via Instagram API ──")
        
        timestamp = int(time.time())
        enc_password = f"#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}"
        
        result = page.evaluate("""(args) => {
            const [csrf, email, username, password, enc_password, full_name, day, month, year] = args;
            const formData = new URLSearchParams();
            formData.append('email', email);
            formData.append('password', password);
            formData.append('enc_password', enc_password);
            formData.append('username', username);
            formData.append('first_name', full_name.split(' ')[0]);
            formData.append('day', day);
            formData.append('month', month);
            formData.append('year', year);
            formData.append('seamless_login_enabled', '1');
            formData.append('tos_version', 'row');
            formData.append('client_id', '');
            
            return fetch('/api/v1/web/accounts/web_create_ajax/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrf,
                    'X-Instagram-AJAX': '1',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData,
                credentials: 'same-origin',
            }).then(r => r.text().then(body => ({status: r.status, body: body})));
        }""", [csrf_token, email, username, password, enc_password, full_name, str(dd), str(dm), str(dy)])

        log(f"  📡 API Status: {result['status']}")
        log(f"  📡 API Response: {result['body'][:200]}")
        
        if result['status'] == 200:
            log("✅ API SUCCESS!")
            
            # Try the second API endpoint for confirmation
            time.sleep(2)
            result2 = page.evaluate("""(args) => {
                const [csrf] = args;
                return fetch('/api/v1/web/accounts/web_create_ajax/attempt/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrf,
                        'X-Instagram-AJAX': '1',
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    credentials: 'same-origin',
                }).then(r => r.text().then(body => ({status: r.status, body: body})));
            }""", [csrf_token])
            log(f"  📡 Attempt response: {result2['body'][:200]}")
        
        time.sleep(5)
        ss(page)
        
        # If API didn't work, try clicking the UI submit button
        if result['status'] != 200:
            log("── Falling back to UI Submit ──")
            try:
                sub = page.locator('div[role="button"]:has-text("Submit")')
                if sub.count() > 0 and sub.first.is_visible():
                    sub.first.click(timeout=5000)
                    log("  👆 Clicked Submit (UI)")
            except: pass

        # ─── WAIT AND CHECK ───
        time.sleep(8)
        ss(page)

        current_url = page.url
        log(f"📄 URL after: {current_url[:120]}")

        # ─── USERNAME TAKEN RETRY ───
        for retry in range(5):
            body_text = ""
            try: body_text = page.locator('body').inner_text()
            except: pass
            
            if "not available" not in body_text and "already taken" not in body_text:
                break
            
            log(f"  ⚠️ Username taken! (retry {retry+1}/5)")
            username = f"{full_name.replace(' ','').lower()}{random.randint(100,99999)}"
            log(f"  🔄 New: {username}")
            
            # JS set the username
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
            log(f"  ✅ JS-set")
            time.sleep(random.uniform(0.5,1.2))
            
            # Resubmit via API with new username
            timestamp = int(time.time())
            enc_password = f"#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}"
            
            result = page.evaluate("""(args) => {
                const [csrf, email, username, password, enc_password, day, month, year] = args;
                const fd = new URLSearchParams();
                fd.append('email', email);
                fd.append('password', password);
                fd.append('enc_password', enc_password);
                fd.append('username', username);
                fd.append('first_name', '');
                fd.append('day', day);
                fd.append('month', month);
                fd.append('year', year);
                fd.append('seamless_login_enabled', '1');
                fd.append('tos_version', 'row');
                return fetch('/api/v1/web/accounts/web_create_ajax/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                    body: fd,
                    credentials: 'same-origin',
                }).then(r => r.text().then(b => ({status: r.status, body: b})));
            }""", [csrf_token, email, username, password, enc_password, str(dd), str(dm), str(dy)])
            
            log(f"  📡 API retry: {result['status']} - {result['body'][:150]}")
            
            if result['status'] == 200:
                log("✅ API SUCCESS on retry!")
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
            for kw in ["welcome","let's go","start exploring","logged in","find people","save your login","you're logged in","signed in"]:
                if kw.lower() in bt.lower():
                    is_success = True
                    log("✅ SUCCESS!")
                    break
        except: pass

        if "emailsignup" not in current_url and "signup" not in current_url:
            is_success = True
            log("✅ Navigated away!")

        with lock:
            latest_credentials = {
                'email': email, 'username': username, 'password': password,
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

# ─── FLASK ROUTES ───
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