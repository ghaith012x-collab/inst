from flask import Flask, render_template, Response, jsonify
from playwright.sync_api import sync_playwright
import requests, random, string, time, json, os, base64, threading

app = Flask(__name__)
latest_screenshot = b''
latest_credentials = {}

def get_free_email():
    r = requests.post("https://api.mail.tm/accounts", json={
        "address": f"{''.join(random.choices(string.ascii_lowercase, k=10))}@mail.tm",
        "password": "temp123!"
    })
    return r.json()

def get_tor_proxy():
    return {"server": "socks5://127.0.0.1:9050"}

def humanized_typing(page, selector, text):
    page.click(selector)
    for char in text:
        page.keyboard.press(char)
        time.sleep(random.uniform(0.05, 0.25))
        if random.random() < 0.05:
            page.keyboard.press("Backspace")
            time.sleep(random.uniform(0.1, 0.3))
            page.keyboard.press(char)

def random_mouse_wander(page):
    for _ in range(random.randint(5, 12)):
        x, y = random.randint(100, 1200), random.randint(100, 700)
        page.mouse.move(x, y, steps=random.randint(3, 8))
        time.sleep(random.uniform(0.2, 0.8))

def screenshot_stream():
    global latest_screenshot
    while True:
        time.sleep(1)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/stream')
def stream():
    def generate():
        while True:
            if latest_screenshot:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_screenshot + b'\r\n')
            time.sleep(1)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/create', methods=['POST'])
def create_account():
    global latest_screenshot, latest_credentials
    
    def run_automation():
        global latest_screenshot, latest_credentials
        with sync_playwright() as p:
            browser = p.chromium.launch(
                proxy=get_tor_proxy(),
                args=[
                    '--disable-blink-features=AutomationControlled',
                    f'--load-extension=/app/buster',
                    '--disable-extensions-except=/app/buster',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ],
                headless=True
            )
            
            context = browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.0',
                locale='en-US',
                timezone_id='America/New_York'
            )
            
            page = context.new_page()
            page.goto('https://www.instagram.com/accounts/emailsignup/')
            time.sleep(random.uniform(2, 4))
            
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            random_mouse_wander(page)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            email_data = get_free_email()
            email = email_data['address']
            
            humanized_typing(page, 'input[name="emailOrPhone"]', email)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            time.sleep(random.uniform(0.5, 1.5))
            
            full_name = f"{random.choice(['Alex','Jordan','Casey','Taylor','Morgan'])} {random.choice(['Smith','Jones','Brown','Davis','Wilson'])}"
            humanized_typing(page, 'input[name="fullName"]', full_name)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            username = f"{full_name.replace(' ','').lower()}{random.randint(10,9999)}"
            humanized_typing(page, 'input[name="username"]', username)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*', k=16))
            humanized_typing(page, 'input[name="password"]', password)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            random_mouse_wander(page)
            time.sleep(random.uniform(1, 3))
            
            page.click('button[type="submit"]')
            time.sleep(5)
            latest_screenshot = page.screenshot(type='jpeg', quality=70)
            
            latest_credentials = {
                'email': email,
                'username': username,
                'password': password,
                'status': 'submitted'
            }
            
            requests.post('http://127.0.0.1:9051', auth=('', ''), data='SIGNAL NEWNYM')
            browser.close()
    
    thread = threading.Thread(target=run_automation)
    thread.start()
    
    return jsonify({'status': 'started', 'message': 'Automation running, watch live feed'})

@app.route('/credentials')
def credentials():
    return jsonify(latest_credentials)

if __name__ == '__main__':
    stream_thread = threading.Thread(target=screenshot_stream, daemon=True)
    stream_thread.start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
