import os
import sys
import time
import random
import string
import threading
import requests
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 8080))

latest_screenshot = b''
latest_credentials = {}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/stream')
def stream():
    def gen():
        while True:
            if latest_screenshot:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + latest_screenshot + b'\r\n'
            time.sleep(1)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify({'alive': True, 'port': PORT})

@app.route('/create', methods=['POST'])
def create():
    global latest_screenshot, latest_credentials
    
    def run():
        global latest_screenshot, latest_credentials
        try:
            from playwright.sync_api import sync_playwright
            p = sync_playwright().start()
            browser = p.chromium.launch(
                proxy={"server": "socks5://127.0.0.1:9050"},
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
                headless=True
            )
            ctx = browser.new_context(viewport={'width': 1366, 'height': 768})
            page = ctx.new_page()
            
            page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000)
            time.sleep(3)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            email = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
            page.fill('input[name="emailOrPhone"]', email)
            time.sleep(random.uniform(0.3, 0.8))
            
            name = f"{random.choice(['Alex','Jordan','Casey'])} {random.choice(['Smith','Jones'])}"
            page.fill('input[name="fullName"]', name)
            time.sleep(random.uniform(0.3, 0.8))
            
            user = f"{name.replace(' ','').lower()}{random.randint(10,9999)}"
            page.fill('input[name="username"]', user)
            time.sleep(random.uniform(0.3, 0.8))
            
            pw = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$', k=14))
            page.fill('input[name="password"]', pw)
            time.sleep(random.uniform(0.3, 0.8))
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            page.click('button[type="submit"]')
            time.sleep(5)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            latest_credentials = {'email': email, 'username': user, 'password': pw}
            
            try:
                requests.post('http://127.0.0.1:9051', data='SIGNAL NEWNYM', timeout=3)
            except:
                pass
                
            browser.close()
        except Exception as e:
            log(f"CRASH: {e}")
            latest_credentials = {'error': str(e)}
    
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/credentials')
def creds():
    return jsonify(latest_credentials)

if __name__ == '__main__':
    log(f"STARTING ON PORT {PORT}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)
