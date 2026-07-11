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

# mail.tm API for temp email
MAILTM = "https://api.mail.tm"

def create_temp_inbox():
    """Create a temp email inbox via mail.tm API."""
    try:
        r = requests.get(f"{MAILTM}/domains", timeout=10)
        if r.status_code != 200: return None, None, None
        doms = r.json().get("hydra:member", [])
        if not doms: return None, None, None
        dom = doms[0]["domain"]
        local = ''.join(random.choices(string.ascii_lowercase, k=10))
        email = f"{local}@{dom}"
        pwd = "Temp321!"
        r = requests.post(f"{MAILTM}/accounts", json={"address": email, "password": pwd}, timeout=10)
        if r.status_code == 201:
            r2 = requests.post(f"{MAILTM}/token", json={"address": email, "password": pwd}, timeout=10)
            if r2.status_code == 200:
                tok = r2.json().get("token", "")
                log(f"Temp: {email}")
                return email, tok, pwd
    except Exception as e:
        log(f"Mail error: {e}")
    return None, None, None

def check_mail(token, timeout=60):
    """Check mail.tm inbox for verification code."""
    start = time.time()
    hdrs = {"Authorization": f"Bearer {token}"}
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{MAILTM}/messages", headers=hdrs, timeout=10)
            if r.status_code == 200:
                msgs = r.json().get("hydra:member", [])
                for msg in msgs:
                    frm = msg.get("from", {}).get("address", "")
                    subj = msg.get("subject", "")
                    log(f"Mail: {frm} | {subj}")
                    mid = msg.get("id")
                    if mid:
                        m = requests.get(f"{MAILTM}/messages/{mid}", headers=hdrs, timeout=10)
                        if m.status_code == 200:
                            data = m.json()
                            txt = data.get("text", "") or ""
                            codes = re.findall(r'\b(\d{5,6})\b', txt)
                            if codes: return codes[0]
                            html = data.get("html", []) or []
                            for p in html if isinstance(html, list) else [html]:
                                if isinstance(p, str):
                                    codes = re.findall(r'\b(\d{5,6})\b', p)
                                    if codes: return codes[0]
        except: pass
        time.sleep(5)
    return None

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        log("Starting browser...")

        browser = p.chromium.launch(
            proxy=None,
            args=['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage',
                  '--disable-gpu','--disable-blink-features=AutomationControlled',
                  '--disable-infobars','--window-size=1366,768'],
            headless=True,
        )
        ctx = browser.new_context(
            viewport={'width':1366,'height':768},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            locale='en-US', timezone_id='America/New_York', color_scheme='light',
        )
        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        page.add_init_script("""Object.defineProperty(navigator, 'webdriver', {get: () => false});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        window.chrome = {runtime: {}};
        try { delete navigator.__proto__.webdriver; } catch(e) {}""")

        # 1. CREATE TEMP EMAIL
        email, mail_token, _ = create_temp_inbox()
        if not email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@gmail.com"
            log(f"Gmail: {email}")

        # 2. CREDS
        fn = random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese'])
        ln = random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson'])
        full = f"{fn} {ln}"
        uname = f"{fn.lower()}{ln.lower()}{random.randint(100,99999)}"
        pwd = ''.join(random.choices(string.ascii_letters+string.digits+'!@#$', k=14))
        log(f"name={full} user={uname} email={email}")

        # 3. LOAD INSTAGRAM
        log("Loading Instagram...")
        page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(4)
        ss(page)

        for c in ["Allow all cookies","Accept All","Accept","Allow","I accept"]:
            try:
                btn = page.get_by_role("button", name=c, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=3000); log("Cookies"); time.sleep(0.5); break
            except: continue
        time.sleep(2)
        ss(page)

        csrf = page.evaluate("() => (document.cookie.match(/csrftoken=([^;]+)/)||[])[1] || ''")
        log(f"CSRF: {csrf[:20]}...")

        inp = page.locator('input:visible')
        ic = inp.count()

        def fill(el, text):
            el.click(timeout=5000); time.sleep(0.15)
            el.fill('', timeout=3000); time.sleep(0.1)
            el.type(text, delay=random.randint(40,90))

        fill(inp.nth(0), email); log("Email"); time.sleep(0.8)
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'password':
                fill(inp.nth(i), pwd); log("Password"); break
        time.sleep(0.8)
        tf = 0
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'text':
                if tf == 0: tf = 1
                elif tf == 1: fill(inp.nth(i), full); log("Name"); tf = 2; break
        time.sleep(0.8)
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'search':
                fill(inp.nth(i), uname); log("Username"); break
        time.sleep(0.8)
        ss(page)

        yr = random.randint(1991, 2005); mo = random.randint(1, 12); dy = random.randint(1, 28 if mo == 2 else 30)
        mn = ['','January','February','March','April','May','June','July','August','September','October','November','December'][mo]
        log(f"DOB: {mn} {dy}, {yr}")
        for label, val in [("Select Month", mn), ("Select Day", str(dy)), ("Select Year", str(yr))]:
            cb = page.locator(f'[role="combobox"][aria-label="{label}"]')
            if cb.count() > 0:
                cb.first.click(timeout=3000); time.sleep(0.3)
                page.keyboard.type(val, delay=random.randint(20,50))
                time.sleep(0.2); page.keyboard.press('Enter'); time.sleep(0.3)
        ss(page)

        # 4. SUBMIT VIA API
        log("Submitting via API...")
        t = int(time.time())
        ep = f"#PWD_INSTAGRAM_BROWSER:0:{t}:{pwd}"

        result = page.evaluate("""(args) => {
            const [c, e, u, p, fn, d, m, y] = args;
            const fd = new URLSearchParams();
            fd.append('email',e); fd.append('enc_password',p);
            fd.append('username',u); fd.append('first_name',fn.split(' ')[0]);
            fd.append('day',d); fd.append('month',m); fd.append('year',y);
            fd.append('client_id',''); fd.append('seamless_login_enabled','1'); fd.append('tos_version','row');
            return fetch('/api/v1/web/accounts/web_create_ajax/', {
                method:'POST', credentials:'same-origin',
                headers:{'X-CSRFToken':c, 'X-Instagram-AJAX':'1', 'Content-Type':'application/x-www-form-urlencoded'},
                body:fd,
            }).then(r => r.text().then(t => ({status:r.status, body:t})));
        }""", [csrf, email, uname, ep, full, str(dy), str(mo), str(yr)])

        log(f"API: {result['status']}")
        body_str = str(result['body'])
        log(f"Body: {body_str[:200]}")

        account_created = '"account_created":true' in body_str
        needs_code = 'force_sign_up_code' in body_str

        # 5. GET VERIFICATION CODE FROM EMAIL
        code = None
        if needs_code and mail_token:
            log("Waiting for verification email...")
            code = check_mail(mail_token, timeout=60)

        # 6. SUBMIT CODE
        if code:
            log(f"Code: {code}")
            cr = page.evaluate("""(args) => {
                const [c, code] = args;
                const fd = new URLSearchParams();
                fd.append('code',code); fd.append('device_id','');
                return fetch('/api/v1/web/accounts/web_create_ajax/confirm_code/', {
                    method:'POST', credentials:'same-origin',
                    headers:{'X-CSRFToken':c, 'X-Instagram-AJAX':'1', 'Content-Type':'application/x-www-form-urlencoded'},
                    body:fd,
                }).then(r => r.text().then(t => ({status:r.status, body:t})));
            }""", [csrf, code])
            log(f"Code result: {cr['status']} - {str(cr['body'])[:200]}")
            if '"account_created":true' in str(cr['body']):
                account_created = True
                log("ACCOUNT CREATED!")
            time.sleep(5)

        # 7. USERNAME RETRY
        if not account_created:
            for r in range(5):
                try:
                    bt = page.locator('body').inner_text()
                    if "not available" not in bt and "already taken" not in bt: break
                except: pass
                uname = f"{fn.lower()}{ln.lower()}{random.randint(1000,99999)}"
                log(f"Username taken! New: {uname}")
                page.evaluate("""(nu) => {
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        if (inp.type === 'search' || inp.getAttribute('aria-label') === 'Username') {
                            inp.disabled = false;
                            const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            s.call(inp, nu); inp.dispatchEvent(new Event('input', {bubbles:true}));
                            inp.dispatchEvent(new Event('change', {bubbles:true})); break;
                        }
                    }
                }""", uname)
                time.sleep(1)
                t = int(time.time())
                ep = f"#PWD_INSTAGRAM_BROWSER:0:{t}:{pwd}"
                result = page.evaluate("""(args) => {
                    const [c, e, u, p, d, m, y] = args;
                    const fd = new URLSearchParams();
                    fd.append('email',e); fd.append('enc_password',p);
                    fd.append('username',u); fd.append('first_name','');
                    fd.append('day',d); fd.append('month',m); fd.append('year',y);
                    fd.append('client_id',''); fd.append('seamless_login_enabled','1'); fd.append('tos_version','row');
                    return fetch('/api/v1/web/accounts/web_create_ajax/', {
                        method:'POST', credentials:'same-origin',
                        headers:{'X-CSRFToken':c, 'X-Instagram-AJAX':'1', 'Content-Type':'application/x-www-form-urlencoded'},
                        body:fd,
                    }).then(r => r.text().then(t => ({status:r.status, body:t})));
                }""", [csrf, email, uname, ep, str(dy), str(mo), str(yr)])
                log(f"Retry: {result['status']} - {str(result['body'])[:200]}")
                if '"account_created":true' in str(result['body']):
                    account_created = True
                    log("ACCOUNT CREATED!")
                    if needs_code and mail_token:
                        code = check_mail(mail_token, timeout=60)
                        if code:
                            cr = page.evaluate("""(args) => {
                                const [c, code] = args;
                                const fd = new URLSearchParams();
                                fd.append('code',code); fd.append('device_id','');
                                return fetch('/api/v1/web/accounts/web_create_ajax/confirm_code/', {
                                    method:'POST', credentials:'same-origin',
                                    headers:{'X-CSRFToken':c, 'X-Instagram-AJAX':'1', 'Content-Type':'application/x-www-form-urlencoded'},
                                    body:fd,
                                }).then(r => r.text().then(t => ({status:r.status, body:t})));
                            }""", [csrf, code])
                            if '"account_created":true' in str(cr['body']):
                                log("CONFIRMED!")
                    break
                time.sleep(5)
                ss(page)

        time.sleep(5); ss(page)
        cur = page.url
        log(f"Final: {cur[:120]}")

        ok = account_created
        try:
            bt = page.locator('body').inner_text()
            for kw in ["welcome","let's go","start exploring","logged in","find people","save your login"]:
                if kw.lower() in bt.lower():
                    ok = True; log("SUCCESS!"); break
        except: pass
        if "emailsignup" not in cur and "signup" not in cur:
            ok = True; log("Navigated away!")

        with lock:
            latest_credentials = {
                'email': email, 'username': uname, 'password': pwd,
                'full_name': full, 'status': 'success' if ok else 'submitted',
                'verification_code': code or '',
                'final_url': cur[:120],
            }
        log(f"Done: {uname} | success={ok}")
        p.stop()

    except Exception as e:
        log(f"CRASH: {e}")
        import traceback
        log(f"{traceback.format_exc()[-300:]}")
        with lock:
            latest_credentials = {'error': str(e)}

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
    log(f"STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)