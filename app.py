import os, sys, time, random, string, threading, requests, re, json
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8080))

latest_screenshot = b''
latest_credentials = {}
status_log = []
lock = threading.Lock()

def log(msg):
    with lock:
        status_log.append(msg)
        if len(status_log) > 100: status_log.pop(0)
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

def ss(page):
    global latest_screenshot
    try:
        with lock:
            latest_screenshot = page.screenshot(type='jpeg', quality=60)
    except:
        pass

def run_signup():
    global latest_screenshot, latest_credentials
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        log("👤 Starting browser...")
        
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
        page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => false});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        window.chrome = {runtime: {}};
        try { delete navigator.__proto__.webdriver; } catch(e) {}
        """)

        # 1. Get hi2.in email
        log("📧 Getting hi2.in email...")
        for attempt in range(3):
            page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
            time.sleep(4)
            # Click Generate
            clicks = page.evaluate("""
                () => { const els = document.querySelectorAll('button, div, span'); 
                for (const el of els) { if (el.textContent.trim().toLowerCase() === 'generate' && el.offsetParent !== null) { el.click(); return true; } } return false; }
            """)
            log(f"Generate clicked: {clicks}")
            time.sleep(5)
            
            # Get email - check full page text
            email = page.evaluate("""
                () => {
                    const t = document.body.innerText;
                    const m = t.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
                    if (m && m[0].includes('@') && m[0].length > 6 && !m[0].includes('{{')) return m[0];
                    const panel = document.querySelector('.mailpanel, .genmail, .contentmail');
                    if (panel) {
                        const m2 = panel.textContent.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
                        if (m2) return m2[0];
                    }
                    return '';
                }
            """)
            if email and '@' in email and len(email) > 6 and '{{' not in email:
                break
            time.sleep(2)
        
        if not email or '@' not in email:
            email = f"{''.join(random.choices(string.ascii_lowercase, k=10))}@gmail.com"
            log(f"⚠️ Using gmail: {email}")
        else:
            log(f"✅ Email: {email}")
        
        ss(page)

        # 2. Generate credentials
        fn = random.choice(['Alex','Jordan','Casey','Riley','Morgan','Taylor','Jamie','Avery','Quinn','Skyler','Drew','Reese'])
        ln = random.choice(['Smith','Jones','Brown','Davis','Lee','Cruz','Wang','Kim','Patel','Garcia','Miller','Wilson'])
        full = f"{fn} {ln}"
        uname = f"{fn.lower()}{ln.lower()}{random.randint(1000,99999)}"
        pwd = ''.join(random.choices(string.ascii_letters+string.digits+'!@#$', k=14))
        log(f"📋 {full} | {uname}")

        # 3. Instagram signup
        log("📷 Loading Instagram...")
        page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
        try: page.wait_for_load_state('networkidle', timeout=15000)
        except: pass
        time.sleep(4)
        ss(page)

        for c in ["Allow all cookies","Accept All","Accept","Allow"]:
            try:
                btn = page.get_by_role("button", name=c, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=3000)
                    time.sleep(0.5)
                    break
            except: continue
        time.sleep(2)

        csrf = page.evaluate("() => (document.cookie.match(/csrftoken=([^;]+)/)||[])[1] || ''")
        log(f"🔑 CSRF: {csrf[:20]}")

        # Fill fields
        inp = page.locator('input:visible')
        ic = inp.count()

        def fill(el, text):
            el.click(timeout=5000); time.sleep(0.2)
            el.fill('', timeout=3000); time.sleep(0.1)
            el.type(text, delay=random.randint(40,90))

        fill(inp.nth(0), email); log("Email"); time.sleep(0.7)
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'password':
                fill(inp.nth(i), pwd); log("Password"); break
        time.sleep(0.7)
        tf = 0
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'text':
                if tf == 0: tf = 1
                elif tf == 1: fill(inp.nth(i), full); log("Name"); tf = 2; break
        time.sleep(0.7)
        for i in range(ic):
            if inp.nth(i).get_attribute('type') == 'search':
                fill(inp.nth(i), uname); log("Username"); break
        time.sleep(0.7)
        ss(page)

        yr = random.randint(1991, 2005); mo = random.randint(1, 12); dy = random.randint(1, 28 if mo == 2 else 30)
        mn = ['','January','February','March','April','May','June','July','August','September','October','November','December'][mo]
        log(f"🎂 {mn} {dy}, {yr}")
        for label, val in [("Select Month", mn), ("Select Day", str(dy)), ("Select Year", str(yr))]:
            cb = page.locator(f'[role="combobox"][aria-label="{label}"]')
            if cb.count() > 0:
                cb.first.click(timeout=3000); time.sleep(0.3)
                page.keyboard.type(val, delay=random.randint(20,50))
                time.sleep(0.2); page.keyboard.press('Enter'); time.sleep(0.3)
        ss(page)

        # 4. Submit via API
        log("🚀 Submitting via API...")
        ts = int(time.time())
        ep = f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{pwd}"
        
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

        log(f"API: {result['status']} - {str(result['body'])[:200]}")
        
        acc_created = '"account_created":true' in str(result['body'])
        needs_code = 'force_sign_up_code' in str(result['body']) or 'email_code' in str(result['body'])

        # Save credentials
        latest_credentials = {
            'email': email, 'username': uname, 'password': pwd,
            'full_name': full, 'status': 'success' if acc_created else 'needs_verification',
        }

        # 5. If code needed, try to get it from hi2.in
        if needs_code:
            log("🔐 Email verification required! Checking hi2.in inbox...")
            page.goto('https://hi2.in/', timeout=30000, wait_until='domcontentloaded')
            time.sleep(3)
            
            for check in range(15):
                # Scroll to refresh mail panel
                page.evaluate("""
                    () => {
                        window.scrollTo(0, document.body.scrollHeight);
                        const mp = document.querySelector('.mailpanel, .contentmail, .genmail');
                        if (mp) mp.scrollIntoView({behavior:'instant', block:'end'});
                    }
                """)
                time.sleep(2)
                
                txt = page.evaluate("() => document.body.innerText")
                codes = re.findall(r'\b(\d{5,6})\b', txt)
                if codes:
                    code = codes[0]
                    log(f"✅ CODE: {code}")
                    latest_credentials['verification_code'] = code
                    
                    # Submit code
                    page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
                    time.sleep(3)
                    csrf2 = page.evaluate("() => (document.cookie.match(/csrftoken=([^;]+)/)||[])[1] || ''")
                    
                    cr = page.evaluate("""(args) => {
                        const [c, code] = args;
                        const fd = new URLSearchParams();
                        fd.append('code',code); fd.append('device_id','');
                        return fetch('/api/v1/web/accounts/web_create_ajax/confirm_code/', {
                            method:'POST', credentials:'same-origin',
                            headers:{'X-CSRFToken':c, 'X-Instagram-AJAX':'1', 'Content-Type':'application/x-www-form-urlencoded'},
                            body:fd,
                        }).then(r => r.text().then(t => ({status:r.status, body:t})));
                    }""", [csrf2, code])
                    log(f"Code API: {cr['status']} - {str(cr['body'])[:200]}")
                    if '"account_created":true' in str(cr['body']):
                        acc_created = True
                        latest_credentials['status'] = 'success'
                        log("✅ ACCOUNT CREATED!")
                    break
                
                log(f"📬 Check ({check+1}/15)")
                page.reload(timeout=30000, wait_until='domcontentloaded')
                time.sleep(3)
        
        if not acc_created:
            log("⚠️ Account needs manual verification")

        ss(page)
        log(f"🏁 Done: {uname}")
        p.stop()

    except Exception as e:
        log(f"💥 {e}")
        import traceback
        log(traceback.format_exc()[-300:])

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/stream')
def stream():
    def gen():
        while True:
            with lock:
                if latest_screenshot:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + latest_screenshot + b'\r\n')
            time.sleep(1)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    with lock: return jsonify({'alive': True, 'log': status_log[-20:]})

@app.route('/create', methods=['POST'])
def create():
    with lock: status_log.clear(); latest_credentials = {}
    threading.Thread(target=run_signup, daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/credentials')
def credentials():
    with lock: return jsonify(latest_credentials)

@app.route('/logs')
def logs():
    with lock: return jsonify(status_log[-50:])

if __name__ == '__main__':
    log(f"🚀 ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)