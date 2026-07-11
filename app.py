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
    page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : origQuery(p)
    );
    try { delete navigator.__proto__.webdriver; } catch(e) {}
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    """)

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

        # ═══════════════════════════════════════════════
        #  STEP 1: Get temp email from hi2.in
        # ═══════════════════════════════════════════════
        log("📧 Getting temp email from hi2.in...")
        page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(3)
        ss(page)

        # Click the "Generate" button to create a temp email
        try:
            gen_btn = page.locator('button:has-text("Generate"), button:has-text("generate"), div:has-text("Generate")').first
            gen_btn.click(timeout=5000)
            log("  👆 Clicked Generate")
            time.sleep(3)
        except:
            log("  ⚠️ Could not click Generate, trying fallback...")
            # Try clicking by text
            page.evaluate("""() => {
                const btns = document.querySelectorAll('button, div, span');
                for (const btn of btns) {
                    if (btn.textContent.includes('Generate') && btn.offsetParent !== null) {
                        btn.click(); return;
                    }
                }
            }""")
            time.sleep(3)
        ss(page)

        # Extract the email address from the page
        email = ""
        for attempt in range(5):
            try:
                # Look for email in various elements
                email = page.evaluate("""() => {
                    const body = document.body.innerText;
                    const match = body.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                    return match ? match[0] : '';
                }""")
                if email and '@' in email:
                    break
            except: pass
            time.sleep(1)
        
        if not email or '@' not in email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@gmail.com"
            log(f"  ⚠️ Could not get temp email, using gmail: {email}")
        else:
            log(f"  ✅ Temp email: {email}")

        # ═══════════════════════════════════════════════
        #  STEP 2: Open Instagram signup in same page
        # ═══════════════════════════════════════════════
        fname = random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese'])
        lname = random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson'])
        full_name = f"{fname} {lname}"
        uname = f"{fname.lower()}{lname.lower()}{random.randint(1000,99999)}"
        pwd = ''.join(random.choices(string.ascii_letters+string.digits+'!@#$', k=14))
        log(f"📋 name={full_name} user={uname} email={email}")

        log("── Loading Instagram ──")
        page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(3)
        ss(page)

        for text in ["Allow all cookies","Accept All","Accept","Allow","I accept"]:
            try:
                btn = page.get_by_role("button", name=text, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=3000); log("  🍪 Cookie accepted"); time.sleep(0.5); break
            except: continue
        time.sleep(2)
        ss(page)

        csrf = page.evaluate("() => (document.cookie.match(/csrftoken=([^;]+)/)||[])[1] || ''")
        log(f"  🔑 CSRF: {csrf[:20]}...")

        # FILL FIELDS
        inputs = page.locator('input:visible')
        ic = inputs.count()
        log(f"  🔍 {ic} visible inputs")

        def ts(el, text):
            el.click(timeout=5000); time.sleep(0.2)
            el.fill('', timeout=3000); time.sleep(0.15)
            el.type(text, delay=random.randint(50,100))

        ts(inputs.nth(0), email)
        log(f"  ✅ Email: {email}")
        time.sleep(random.uniform(0.5,1.2))

        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'password':
                ts(inputs.nth(i), pwd); log("  ✅ Password"); break
        time.sleep(random.uniform(0.5,1.2))

        tf = 0
        for i in range(ic):
            tp = inputs.nth(i).get_attribute('type')
            if tp == 'text':
                if tf == 0: tf = 1
                elif tf == 1: ts(inputs.nth(i), full_name); log(f"  ✅ Name: {full_name}"); tf = 2; break
        time.sleep(random.uniform(0.5,1.2))

        for i in range(ic):
            if inputs.nth(i).get_attribute('type') == 'search':
                ts(inputs.nth(i), uname); log(f"  ✅ Username: {uname}"); break
        time.sleep(random.uniform(0.5,1.2))
        ss(page)

        # DOB
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
                cb.first.click(timeout=3000); time.sleep(0.4)
                page.keyboard.type(val, delay=random.randint(30,60))
                time.sleep(0.3); page.keyboard.press('Enter'); time.sleep(0.3)
                log(f"  ✅ {label.split()[1]}: {val}")
        ss(page)

        # ═══════════════════════════════════════════════
        #  STEP 3: Submit via API
        # ═══════════════════════════════════════════════
        log("── Submitting via API ──")
        ts2 = int(time.time())
        enc_pwd = f"#PWD_INSTAGRAM_BROWSER:0:{ts2}:{pwd}"

        result = page.evaluate("""(args) => {
            const [csrf, email, uname, enc_pwd, full_name, day, month, year] = args;
            const fd = new URLSearchParams();
            fd.append('email', email); fd.append('enc_password', enc_pwd);
            fd.append('username', uname); fd.append('first_name', full_name.split(' ')[0]);
            fd.append('day', day); fd.append('month', month); fd.append('year', year);
            fd.append('client_id', ''); fd.append('seamless_login_enabled', '1'); fd.append('tos_version', 'row');
            return fetch('/api/v1/web/accounts/web_create_ajax/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                body: fd, credentials: 'same-origin',
            }).then(r => r.text().then(t => ({status: r.status, body: t})));
        }""", [csrf, email, uname, enc_pwd, full_name, str(dd), str(dm), str(dy)])

        log(f"  📡 API: {result['status']}")
        body_str = str(result['body'])
        log(f"    body: {body_str[:300]}")
        account_created = '"account_created":true' in body_str

        # ═══════════════════════════════════════════════
        #  STEP 4: Submit via UI (triggers email)
        # ═══════════════════════════════════════════════
        log("── Clicking Submit in UI ──")
        page.evaluate("""() => {
            const btns = document.querySelectorAll('[role="button"]');
            for (const btn of btns) {
                if (btn.textContent.includes('Submit')) { btn.click(); return; }
            }
        }""")
        time.sleep(5)
        ss(page)

        # ═══════════════════════════════════════════════
        #  STEP 5: Check hi2.in for verification code
        # ═══════════════════════════════════════════════
        log("📧 Checking hi2.in for verification email...")
        verification_code = None
        
        # Go back to hi2.in 
        page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
        time.sleep(3)
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        
        # Wait for email to arrive
        for attempt in range(12):
            try:
                # Get the page text - look for verification code
                page_text = page.evaluate("() => document.body.innerText")
                log(f"  📄 Checking hi2.in... ({attempt+1}/12)")
                
                # Look for 5-6 digit codes
                codes = re.findall(r'\b(\d{5,6})\b', page_text)
                if codes:
                    verification_code = codes[0]
                    log(f"  ✅ Found code: {verification_code}")
                    break
                
                # Refresh the page
                page.reload(timeout=30000, wait_until='domcontentloaded')
                time.sleep(3)
                ss(page)
            except Exception as e:
                log(f"  ⚠️ Check error: {e}")
                time.sleep(5)
        
        if not verification_code:
            log("  ⚠️ No verification code found on hi2.in")
            # Try clicking around to see if more emails load
            page.evaluate("""() => {
                const btns = document.querySelectorAll('button, div, span');
                for (const btn of btns) {
                    if (btn.textContent.includes('More') && btn.offsetParent !== null) {
                        btn.click(); return;
                    }
                }
            }""")
            time.sleep(3)
            page_text = page.evaluate("() => document.body.innerText")
            codes = re.findall(r'\b(\d{5,6})\b', page_text)
            if codes:
                verification_code = codes[0]
                log(f"  ✅ Found code after clicking More: {verification_code}")

        # ═══════════════════════════════════════════════
        #  STEP 6: Enter verification code on Instagram
        # ═══════════════════════════════════════════════
        if verification_code:
            log(f"  🔑 Going back to Instagram to enter code: {verification_code}")
            page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
            time.sleep(3)
            ss(page)
            
            # Try to enter the code via API
            log("── Submitting verification code via API ──")
            try:
                code_result = page.evaluate("""(args) => {
                    const [csrf, code] = args;
                    const fd = new URLSearchParams();
                    fd.append('code', code);
                    fd.append('device_id', '');
                    return fetch('/api/v1/web/accounts/web_create_ajax/confirm_code/', {
                        method: 'POST',
                        headers: {'X-CSRFToken': csrf, 'X-Instagram-AJAX': '1', 'Content-Type': 'application/x-www-form-urlencoded'},
                        body: fd, credentials: 'same-origin',
                    }).then(r => r.text().then(t => ({status: r.status, body: t})));
                }""", [csrf, verification_code])
                log(f"  📡 Code API: {code_result['status']} - {str(code_result['body'])[:200]}")
                if '"account_created":true' in str(code_result['body']):
                    account_created = True
                    log("✅ ACCOUNT CREATED!")
                time.sleep(3)
                ss(page)
            except Exception as e:
                log(f"  ⚠️ Code API error: {e}")

        # ═══════════════════════════════════════════════
        #  STEP 7: Handle verification dialog (UI)
        # ═══════════════════════════════════════════════
        if not account_created:
            log("── Handling verification dialog ──")
            for attempt in range(8):
                try:
                    has_dialog = page.evaluate("""() => {
                        const d = document.querySelector('[role="dialog"]');
                        return d ? d.textContent.includes('confirm') || d.textContent.includes('Confirm') : false;
                    }""")
                    if not has_dialog:
                        log("  ✅ No more verification dialog!")
                        break
                    
                    clicked = page.evaluate("""() => {
                        const btns = document.querySelectorAll('[role="button"]');
                        for (const btn of btns) {
                            if (btn.textContent.includes('Next')) {
                                btn.removeAttribute('aria-disabled');
                                btn.click(); return true;
                            }
                        }
                        const divs = document.querySelectorAll('div[role="button"]');
                        for (const div of divs) {
                            if (div.textContent.includes('Next')) {
                                div.removeAttribute('aria-disabled');
                                div.click(); return true;
                            }
                        }
                        return false;
                    }""")
                    log(f"  🔓 Attempt {attempt+1}: {'Clicked Next' if clicked else 'No Next'}")
                    time.sleep(4); ss(page)
                except Exception as e:
                    log(f"  ⚠️ Error: {e}"); break

        # ═══════════════════════════════════════════════
        #  STEP 8: Username retry
        # ═══════════════════════════════════════════════
        for retry in range(5):
            try:
                bt = page.locator('body').inner_text()
                if "not available" not in bt and "already taken" not in bt: break
            except: pass
            uname = f"{fname.lower()}{lname.lower()}{random.randint(1000,99999)}"
            log(f"  ⚠️ Username taken! New: {uname}")
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
                for (const btn of btns) { if (btn.textContent.includes('Submit')) { btn.click(); return; } }
            }""")
            time.sleep(8); ss(page)

        # ═══════════════════════════════════════════════
        #  FINAL
        # ═══════════════════════════════════════════════
        time.sleep(5)
        ss(page)
        cur = page.url
        log(f"📄 Final URL: {cur[:120]}")

        is_ok = account_created
        try:
            bt = page.locator('body').inner_text()
            for kw in ["welcome","let's go","start exploring","logged in","find people","save your login","you're logged in","signed in"]:
                if kw.lower() in bt.lower(): is_ok = True; log("✅ SUCCESS!"); break
        except: pass
        if "emailsignup" not in cur and "signup" not in cur: is_ok = True; log("✅ Navigated away!")

        with lock:
            latest_credentials = {
                'email': email, 'username': uname, 'password': pwd,
                'full_name': full_name, 
                'status': 'success' if is_ok else 'needs_verification',
                'verification_code': verification_code or '',
                'final_url': cur[:120],
            }
        log(f"🏁 Done: {uname} | success={is_ok}")
        p.stop()

    except Exception as e:
        log(f"💥 CRASH: {e}")
        import traceback
        log(f"💥 {traceback.format_exc()[-300:]}")
        with lock:
            latest_credentials = {'error': str(e)}

# FLASK ROUTES
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