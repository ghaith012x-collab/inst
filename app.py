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

def get_email(page):
    page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
    try: page.wait_for_load_state('networkidle', timeout=15000)
    except: pass
    time.sleep(4)
    ss(page)
    page.evaluate("""() => {
        const all = document.querySelectorAll('button, div, span, a');
        for (const el of all) {
            const t = el.textContent.trim().toLowerCase();
            if (t === 'generate' && el.offsetParent !== null) { el.click(); return; }
        }
    }""")
    log("Clicked Generate")
    time.sleep(5)
    ss(page)
    for i in range(15):
        email = page.evaluate("""() => {
            const t = document.body.innerText;
            const m = t.match(/[a-zA-Z]{3,15}@[a-zA-Z0-9.-]+\\.(?:com|net|org|info|io|co|in|me|app|dev|xyz|online|site|tk|ml|ga)\\b/);
            if (m && m[0].length > 6 && m[0].includes('@')) return m[0];
            return '';
        }""")
        if email and '@' in email and len(email) > 8 and 'random@' not in email:
            log(f"Got: {email}")
            return email
        log(f"Wait... ({i+1}/15)")
        time.sleep(1)
    return None

def click_recaptcha_checkbox(page):
    """Click the reCAPTCHA 'I am not a robot' checkbox inside any iframe."""
    for _ in range(20):
        total = page.locator('iframe').count()
        for i in range(total):
            try:
                fr = page.locator('iframe').nth(i).content_frame()
                if fr:
                    anchor = fr.locator('#recaptcha-anchor')
                    if anchor.count() > 0:
                        anchor.first.click(timeout=3000)
                        time.sleep(2)
                        if anchor.first.get_attribute('aria-checked') == 'true':
                            log("  ✅ Checkbox clicked!")
                            return True
            except: pass
        time.sleep(1)
    return False

def check_inbox_for_code(page):
    """Check hi2.in for verification code."""
    page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
    time.sleep(3)
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    ss(page)
    for a in range(15):
        txt = page.evaluate("() => document.body.innerText")
        codes = re.findall(r'\b(\d{5,6})\b', txt)
        if codes:
            log(f"Code: {codes[0]}")
            return codes[0]
        log(f"Check ({a+1}/15)")
        page.reload(timeout=30000, wait_until='domcontentloaded')
        time.sleep(3)
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        ss(page)
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

        # 1. GET EMAIL FROM hi2.in
        email = get_email(page)
        if not email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@gmail.com"
            log(f"Gmail: {email}")

        # 2. GENERATE CREDS
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

        inp = page.locator('input:visible')
        ic = inp.count()

        def fill(el, text):
            el.click(timeout=5000); time.sleep(0.15)
            el.fill('', timeout=3000); time.sleep(0.1)
            el.type(text, delay=random.randint(40,90))

        # 4. FILL ALL FIELDS
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

        # 5. DOB
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

        # 6. CLICK SUBMIT
        log("Clicking Submit...")
        page.evaluate("""() => {
            const btns = document.querySelectorAll('[role="button"]');
            for (const b of btns) { if (b.textContent.includes('Submit')) { b.click(); return; } }
        }""")
        time.sleep(10)
        ss(page)

        # 7. HANDLE SECURITY DIALOG + reCAPTCHA
        log("Security dialog handling...")
        for i in range(3):
            has = page.evaluate("""() => { const d = document.querySelector('[role="dialog"]'); return d ? true : false; }""")
            if not has:
                log("No dialog - submitted!")
                break
            # Click Next to trigger reCAPTCHA
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase() === 'next') {
                        b.removeAttribute('aria-disabled'); b.click(); return;
                    }
                }
            }""")
            log(f"Clicked Next ({i+1})")
            time.sleep(5)
            ss(page)

        # 8. CLICK reCAPTCHA CHECKBOX (the empty box)
        log("Clicking reCAPTCHA checkbox...")
        clicked = click_recaptcha_checkbox(page)
        if clicked:
            log("✅ reCAPTCHA checkbox clicked!")
            time.sleep(5)
            ss(page)
            # Click Next after reCAPTCHA
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase() === 'next') {
                        b.removeAttribute('aria-disabled'); b.click(); return;
                    }
                }
            }""")
            log("Clicked Next after captcha")
            time.sleep(5)
            ss(page)
        else:
            log("No reCAPTCHA found, clicking Next...")
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase() === 'next') {
                        b.removeAttribute('aria-disabled'); b.click(); return;
                    }
                }
            }""")
            time.sleep(5)
            ss(page)

        # 9. CHECK hi2.in FOR VERIFICATION CODE
        log("Checking hi2.in for verification code...")
        code = check_inbox_for_code(page)

        # 10. ENTER CODE IF FOUND
        if code:
            log(f"Entering code: {code}")
            page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
            time.sleep(3)
            ss(page)
            inp2 = page.locator('input:visible')
            if inp2.count() > 0:
                fill(inp2.first, code)
                log("Code entered!")
                time.sleep(1)
            # Click Next/Submit
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase() === 'next' || b.textContent.includes('Submit')) {
                        b.removeAttribute('aria-disabled'); b.click(); return;
                    }
                }
            }""")
            time.sleep(5)
            ss(page)
            # Maybe click Next again
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase() === 'next') {
                        b.removeAttribute('aria-disabled'); b.click(); return;
                    }
                }
            }""")
            time.sleep(5)
            ss(page)

        # 11. USERNAME RETRY
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
            page.evaluate("""() => {
                const btns = document.querySelectorAll('[role="button"]');
                for (const b of btns) { if (b.textContent.includes('Submit')) { b.click(); return; } }
            }""")
            time.sleep(8); ss(page)

        time.sleep(5); ss(page)
        cur = page.url
        log(f"Final: {cur[:120]}")

        ok = False
        try:
            bt = page.locator('body').inner_text()
            for kw in ["welcome","let's go","start exploring","logged in","find people","save your login"]:
                if kw.lower() in bt.lower(): ok = True; log("SUCCESS!"); break
        except: pass
        if "emailsignup" not in cur and "signup" not in cur: ok = True; log("Navigated away!")

        with lock:
            latest_credentials = {
                'email': email, 'username': uname, 'password': pwd,
                'full_name': full, 'status': 'success' if ok else 'needs_verification',
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