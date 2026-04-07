from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from FraudCat import FraudCatSession
import threading
import time
import uuid
import logging
from typing import Dict, Any
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
CORS(app)

# Store active listeners and results
active_listeners: Dict[str, Dict] = {}
listener_results: Dict[str, Any] = {}
listener_status: Dict[str, str] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailListenerThread(threading.Thread):
    def __init__(self, session_id: str, username: str, password: str, 
                 email_username: str = None, max_iterations: int = 15):
        super().__init__()
        self.session_id = session_id
        self.username = username
        self.password = password
        self.email_username = email_username
        self.max_iterations = max_iterations
        self.is_running = True
        
    def run(self):
        try:
            listener_status[self.session_id] = "initializing"
            
            # Create FraudCat session
            fraud_session = FraudCatSession(self.username, self.password)
            
            if not fraud_session.is_logged_in:
                listener_status[self.session_id] = "error"
                listener_results[self.session_id] = {
                    "error": "Login failed. Check your credentials."
                }
                return
            
            listener_status[self.session_id] = "getting_domains"
            
            # Check if domains are available
            if not fraud_session.available_domains:
                listener_status[self.session_id] = "error"
                listener_results[self.session_id] = {
                    "error": "No available domains found. Your account might not have access."
                }
                return
            
            listener_status[self.session_id] = "creating_email"
            
            # Create and listen for emails
            if self.email_username:
                # Use specific username
                to_domain = fraud_session.get_random_domain()
                if to_domain:
                    listener_status[self.session_id] = "listening"
                    email_address = f"{self.email_username}@{to_domain}"
                    
                    try:
                        message = fraud_session.create_and_listen(
                            self.email_username, to_domain, 
                            fetch_full_body=True, 
                            max_iterations=self.max_iterations
                        )
                        listener_results[self.session_id] = {
                            "email": email_address,
                            "message": message,
                            "status": "success"
                        }
                        listener_status[self.session_id] = "completed"
                    except TimeoutError:
                        listener_results[self.session_id] = {
                            "email": email_address,
                            "error": f"No email received within {self.max_iterations * 20} seconds",
                            "status": "timeout"
                        }
                        listener_status[self.session_id] = "timeout"
                else:
                    listener_results[self.session_id] = {
                        "error": "Failed to get random domain"
                    }
                    listener_status[self.session_id] = "error"
            else:
                # Use random username
                try:
                    email_address, message = fraud_session.create_and_listen_random(
                        fraud_session.generate_random_user(),
                        fetch_full_body=True,
                        max_iterations=self.max_iterations
                    )
                    listener_results[self.session_id] = {
                        "email": email_address,
                        "message": message,
                        "status": "success"
                    }
                    listener_status[self.session_id] = "completed"
                except TimeoutError:
                    listener_results[self.session_id] = {
                        "error": f"No email received within {self.max_iterations * 20} seconds",
                        "status": "timeout"
                    }
                    listener_status[self.session_id] = "timeout"
            
            fraud_session.logout()
            
        except Exception as e:
            logger.error(f"Listener thread error: {e}")
            listener_status[self.session_id] = "error"
            listener_results[self.session_id] = {
                "error": str(e)
            }

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/start_listener', methods=['POST'])
def start_listener():
    """Start a new email listener"""
    data = request.json
    
    username = data.get('username')
    password = data.get('password')
    email_username = data.get('email_username')
    max_iterations = data.get('max_iterations', 15)
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    # Create session ID
    session_id = str(uuid.uuid4())
    
    # Start listener thread
    listener = EmailListenerThread(
        session_id, username, password, email_username, max_iterations
    )
    listener.daemon = True
    listener.start()
    
    active_listeners[session_id] = listener
    listener_status[session_id] = "started"
    
    return jsonify({
        "session_id": session_id,
        "message": "Listener started"
    })

@app.route('/api/check_status/<session_id>', methods=['GET'])
def check_status(session_id):
    """Check listener status and get results"""
    status = listener_status.get(session_id, "not_found")
    
    if status == "completed":
        result = listener_results.get(session_id, {})
        return jsonify({
            "status": status,
            "result": result
        })
    elif status == "timeout":
        result = listener_results.get(session_id, {})
        return jsonify({
            "status": status,
            "error": result.get("error", "Timeout occurred")
        })
    elif status == "error":
        result = listener_results.get(session_id, {})
        return jsonify({
            "status": status,
            "error": result.get("error", "Unknown error occurred")
        })
    else:
        return jsonify({
            "status": status
        })

@app.route('/api/test_login', methods=['POST'])
def test_login():
    """Test if login credentials work"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    try:
        fraud_session = FraudCatSession(username, password)
        if fraud_session.is_logged_in:
            domains_count = len(fraud_session.available_domains)
            fraud_session.logout()
            return jsonify({
                "success": True,
                "domains_available": domains_count,
                "message": f"Login successful! {domains_count} domains available."
            })
        else:
            return jsonify({
                "success": False,
                "error": "Login failed. Check your credentials."
            }), 401
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/get_domains', methods=['POST'])
def get_domains():
    """Get available domains for an account"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    try:
        fraud_session = FraudCatSession(username, password)
        if fraud_session.is_logged_in:
            return jsonify({
                "success": True,
                "domains": fraud_session.available_domains
            })
        else:
            return jsonify({
                "success": False,
                "error": "Login failed"
            }), 401
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)