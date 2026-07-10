import os
import sys
import time
import random
import string
import threading
import requests
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)

PORT = 8080
latest_screenshot = b''
latest_credentials = {}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def tor_check():
    try:
        proxies = {
            'http': 'socks5://127.0.0.1:9050',
            'https': 'socks5://127.0.0.1:9050'
        }
        r = requests.get('https://check.torproject.org', proxies=proxies, timeout=15)
        return 'Congratulations' in r.text
    except Exception as e:
        log(f"Tor check error: {e}")
        return False

def get_email():
    try:
        addr = f"{''.join(random.choices(string.ascii_lowercase, k=12))}@mail.tm"
        r = requests.post("https://api.mail.tm/accounts", json={
            "address": addr,
            "password": "temp123!"
        }, timeout=10)
        return r.json().get('address', addr)
    except Exception as e:
        log(f"Email error: {e}")
        return f"fail_{random.randint(1000,9999)}@mail.tm"

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
    return jsonify({
        'tor': tor_check(),
        'port': PORT,
        'screenshot_size': len(latest_screenshot)
    })

@app.route('/create', methods=['POST'])
def create():
    global latest_screenshot, latest_credentials
    
    def run():
        global latest_screenshot, latest_credentials
        try:
            from playwright.sync_api import sync_playwright
            
            browser = sync_playwright().start().chromium.launch(
                proxy={"server": "socks5://127.0.0.1:9050"},
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled'
                ],
                headless=True
            )
            
            ctx = browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.0'
            )
            
            page = ctx.new_page()
            page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000)
            time.sleep(3)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            email = get_email()
            
            page.fill('input[name="emailOrPhone"]', email)
            time.sleep(random.uniform(0.3, 0.8))
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
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
            log(f"Automation error: {e}")
            latest_credentials = {'error': str(e)}
    
    threading.Thread(target=run).start()
    return jsonify({'status': 'started'})

@app.route('/credentials')
def creds():
    return jsonify(latest_credentials)

if __name__ == '__main__':
    log(f"Starting app on 0.0.0.0:{PORT}")
    log(f"Tor status: {tor_check()}")
    app.run(host='0.0.0.0', port=PORT, threaded=True)
