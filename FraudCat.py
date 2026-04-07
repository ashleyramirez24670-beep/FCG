from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import requests
import time
import json
import logging
import random
import string
import threading
import uuid
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.secret_key = 'fraudcat-secret-key-2024'
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== HARDCODED FRAUDCAT CREDENTIALS =====
# CHANGE THESE TO YOUR ACTUAL CREDENTIALS
FRAUDCAT_USERNAME = "ronaldcarimi"  # CHANGE THIS
FRAUDCAT_PASSWORD = "Amachika@698"  # CHANGE THIS
# ==========================================

# Store active listeners and results
active_listeners: Dict[str, Dict] = {}
listener_results: Dict[str, Any] = {}
listener_status: Dict[str, str] = {}

# Global session that stays logged in
global_fraud_session = None

def get_global_session():
    """Get or create a persistent global FraudCat session"""
    global global_fraud_session
    if global_fraud_session is None or not global_fraud_session.is_logged_in:
        global_fraud_session = FraudCatSession(FRAUDCAT_USERNAME, FRAUDCAT_PASSWORD)
    return global_fraud_session

# FraudCat Session Class
class FraudCatSession:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.base_url = "https://fraud.cat"
        self.session = requests.Session()
        self.available_domains = []
        self.is_logged_in = False
        self.last_message_count = 0
        self.received_messages = []
        
        self.default_headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
            "referer": f"{self.base_url}/Account/Login"
        }
        
        self.api_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "referer": f"{self.base_url}/Application"
        }
        
        self.session.headers.update(self.default_headers)
        
        if username and password:
            if self.login(username, password):
                self._fetch_available_domains()
    
    def login(self, username: str, password: str) -> bool:
        try:
            login_url = f"{self.base_url}/Account/Login?returnUrl=/Application"
            login_data = {
                "returnUrlHash": "",
                "usernameOrEmailAddress": username,
                "password": password
            }
            
            response = self.session.post(login_url, data=login_data)
            if response.status_code == 200:
                self.is_logged_in = True
                logger.info(f"Logged in as {username}")
                return True
            return False
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def _fetch_available_domains(self):
        try:
            self.session.headers.update(self.api_headers)
            url = f"{self.base_url}/api/services/app/mail/GetDomainsList"
            response = self.session.post(url, data="{}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('result'):
                    self.available_domains = [
                        d.get('domainName') for d in data['result'] 
                        if isinstance(d, dict) and not d.get('isElite') and not d.get('isDead') and d.get('domainName')
                    ]
                    logger.info(f"Found {len(self.available_domains)} available domains")
        except Exception as e:
            logger.error(f"Failed to fetch domains: {e}")
    
    def generate_random_user(self, length: int = 8) -> str:
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for _ in range(length))
    
    def get_random_domain(self) -> Optional[str]:
        if not self.available_domains:
            logger.error("No available domains")
            return None
        return random.choice(self.available_domains)
    
    def create_email(self, to_address: str, to_domain: str) -> bool:
        if not self.is_logged_in:
            logger.error("Not logged in")
            return False
        
        try:
            url = f"{self.base_url}/Application#/tenant/inbox/{to_address}/{to_domain}"
            response = self.session.get(url)
            
            if response.status_code == 200:
                logger.info(f"Created/accessed email: {to_address}@{to_domain}")
                return True
            else:
                logger.error(f"Failed to create email: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Create email failed: {e}")
            return False
    
    def get_inbox(self, to_domain: str, to_address: str) -> List[Dict]:
        if not self.is_logged_in:
            return []
        
        try:
            self.session.headers.update(self.api_headers)
            url = f"{self.base_url}/api/services/app/mail/GetInbox"
            
            payload = {
                "toDomain": to_domain,
                "toAddress": to_address
            }
            
            response = self.session.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                res = data['result']
                messages = res["emails"]
                return messages
            else:
                logger.error(f"Get inbox failed: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Get inbox failed: {e}")
            return []
    
    def get_email_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        if not self.is_logged_in:
            logger.error("Not logged in")
            return None
        
        try:
            self.session.headers.update(self.api_headers)
            url = f"{self.base_url}/api/services/app/mail/GetLetterById"
            
            payload = {
                "uid": uid
            }
            
            logger.info(f"Fetching email with UID: {uid}")
            response = self.session.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('success') and data.get('result'):
                    email_data = data['result']
                    logger.info(f"Successfully fetched email: {email_data.get('subject', 'No subject')}")
                    return email_data
                else:
                    logger.error(f"API returned error: {data.get('error', 'Unknown error')}")
                    return None
            else:
                logger.error(f"Failed to fetch email: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Get email by UID failed: {e}")
            return None
    
    def get_all_inboxes(self) -> List[Dict]:
        """Get all available inboxes for the account"""
        if not self.is_logged_in:
            return []
        
        try:
            self.session.headers.update(self.api_headers)
            url = f"{self.base_url}/api/services/app/mail/GetInboxes"
            response = self.session.post(url, json={})
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('result'):
                    return data['result']
            return []
        except Exception as e:
            logger.error(f"Get all inboxes failed: {e}")
            return []
    
    def listen_for_mail(self, to_domain: str, to_address: str, fetch_full_body: bool = False, max_iterations: int = 10):
        full_email = f"{to_address}@{to_domain}"
        logger.info(f"📡 Listening for emails at {full_email}")
        
        current_messages = self.get_inbox(to_domain, to_address)
        self.last_message_count = len(current_messages)
        self.received_messages = current_messages.copy()
        
        iteration = 0
        messages_received = False
        
        while iteration < max_iterations:
            try:
                iteration += 1
                logger.info(f"📊 Iteration {iteration}/{max_iterations}")
                
                current_messages = self.get_inbox(to_domain, to_address)
                current_count = len(current_messages)
                
                if current_count > self.last_message_count:
                    messages_received = True
                    new_messages = current_messages[self.last_message_count:]
                    
                    for message in new_messages:
                        if fetch_full_body:
                            uid = message.get('uid')
                            if uid:
                                full_email_data = self.get_email_by_uid(uid)
                                if full_email_data:
                                    yield full_email_data
                                else:
                                    yield message
                            else:
                                yield message
                        else:
                            yield message
                    
                    self.last_message_count = current_count
                
                if iteration >= max_iterations:
                    if not messages_received:
                        raise TimeoutError(f"No messages received within {max_iterations * 20} seconds")
                    else:
                        break
                
                time.sleep(20)
            except KeyboardInterrupt:
                break
            except TimeoutError:
                raise
            except Exception as e:
                logger.error(f"Error while listening: {e}")
                time.sleep(20)
    
    def create_and_listen(self, to_address: str, to_domain: str, fetch_full_body: bool = True, max_iterations: int = 10):
        if not self.create_email(to_address, to_domain):
            logger.error("Failed to create email")
            return None
        
        for message in self.listen_for_mail(to_domain, to_address, fetch_full_body, max_iterations):
            return message
        return None
    
    def create_and_listen_random(self, username: str, fetch_full_body: bool = True, max_iterations: int = 10):
        if not self.available_domains:
            logger.error("No available domains")
            return None, None
        
        random_user = username
        random_domain = self.get_random_domain()
        
        if not random_domain:
            logger.error("Failed to get random domain")
            return None, None
        
        if not self.create_email(random_user, random_domain):
            logger.error("Failed to create email")
            return None, None
        
        for message in self.listen_for_mail(random_domain, random_user, fetch_full_body, max_iterations):
            return f"{random_user}@{random_domain}", message
        
        return None, None
    
    def logout(self):
        try:
            self.session.get(f"{self.base_url}/Account/Logout")
            self.is_logged_in = False
            logger.info("Logged out")
        except:
            pass

class EmailListenerThread(threading.Thread):
    def __init__(self, session_id: str, email_username: str = None, 
                 email_domain: str = None, max_iterations: int = 15):
        super().__init__()
        self.session_id = session_id
        self.email_username = email_username
        self.email_domain = email_domain
        self.max_iterations = max_iterations
        self.is_running = True
        
    def run(self):
        try:
            listener_status[self.session_id] = "initializing"
            
            # Use the global session
            fraud_session = get_global_session()
            
            if not fraud_session.is_logged_in:
                listener_status[self.session_id] = "error"
                listener_results[self.session_id] = {
                    "error": "Failed to authenticate with FraudCat. Check hardcoded credentials."
                }
                return
            
            listener_status[self.session_id] = "getting_domains"
            
            if not fraud_session.available_domains:
                listener_status[self.session_id] = "error"
                listener_results[self.session_id] = {
                    "error": "No available domains found."
                }
                return
            
            listener_status[self.session_id] = "creating_email"
            
            if self.email_username and self.email_domain:
                # Use specified email
                email_address = f"{self.email_username}@{self.email_domain}"
                listener_status[self.session_id] = "listening"
                
                try:
                    # First check if inbox exists and get existing messages
                    existing_messages = fraud_session.get_inbox(self.email_domain, self.email_username)
                    fraud_session.last_message_count = len(existing_messages)
                    
                    # Start listening for new messages
                    for message in fraud_session.listen_for_mail(
                        self.email_domain, self.email_username, 
                        fetch_full_body=True, 
                        max_iterations=self.max_iterations
                    ):
                        listener_results[self.session_id] = {
                            "email": email_address,
                            "message": message,
                            "status": "success"
                        }
                        listener_status[self.session_id] = "completed"
                        return
                        
                except TimeoutError:
                    listener_results[self.session_id] = {
                        "email": email_address,
                        "error": f"No email received within {self.max_iterations * 20} seconds",
                        "status": "timeout"
                    }
                    listener_status[self.session_id] = "timeout"
                    return
            else:
                # Create random email
                try:
                    email_address, message = fraud_session.create_and_listen_random(
                        fraud_session.generate_random_user(),
                        fetch_full_body=True,
                        max_iterations=self.max_iterations
                    )
                    if email_address and message:
                        listener_results[self.session_id] = {
                            "email": email_address,
                            "message": message,
                            "status": "success"
                        }
                        listener_status[self.session_id] = "completed"
                    else:
                        listener_results[self.session_id] = {
                            "error": "No email received",
                            "status": "timeout"
                        }
                        listener_status[self.session_id] = "timeout"
                except TimeoutError:
                    listener_results[self.session_id] = {
                        "error": f"No email received within {self.max_iterations * 20} seconds",
                        "status": "timeout"
                    }
                    listener_status[self.session_id] = "timeout"
            
        except Exception as e:
            logger.error(f"Listener thread error: {e}")
            listener_status[self.session_id] = "error"
            listener_results[self.session_id] = {
                "error": str(e)
            }

# API Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    """Check if FraudCat is connected"""
    fraud_session = get_global_session()
    return jsonify({
        "connected": fraud_session.is_logged_in,
        "domains_available": len(fraud_session.available_domains),
        "domains": fraud_session.available_domains[:10]  # First 10 domains
    })

@app.route('/api/get_inboxes', methods=['GET'])
def get_inboxes():
    """Get all existing inboxes"""
    fraud_session = get_global_session()
    
    if not fraud_session.is_logged_in:
        return jsonify({"error": "Not connected to FraudCat"}), 401
    
    try:
        # This endpoint might not exist, so we'll return domains instead
        inboxes = []
        for domain in fraud_session.available_domains:
            inboxes.append({
                "domain": domain,
                "addresses": []  # We can't list addresses without knowing them
            })
        
        return jsonify({
            "success": True,
            "inboxes": inboxes,
            "domains": fraud_session.available_domains
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/check_inbox', methods=['POST'])
def check_inbox():
    """Check messages for a specific email address"""
    data = request.json
    email_username = data.get('username')
    email_domain = data.get('domain')
    
    if not email_username or not email_domain:
        return jsonify({"error": "Username and domain required"}), 400
    
    fraud_session = get_global_session()
    
    if not fraud_session.is_logged_in:
        return jsonify({"error": "Not connected to FraudCat"}), 401
    
    try:
        messages = fraud_session.get_inbox(email_domain, email_username)
        
        # Fetch full content for each message
        full_messages = []
        for msg in messages:
            uid = msg.get('uid')
            if uid:
                full_msg = fraud_session.get_email_by_uid(uid)
                if full_msg:
                    full_messages.append(full_msg)
                else:
                    full_messages.append(msg)
            else:
                full_messages.append(msg)
        
        return jsonify({
            "success": True,
            "email": f"{email_username}@{email_domain}",
            "message_count": len(full_messages),
            "messages": full_messages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/create_email', methods=['POST'])
def create_email():
    """Create a new email address"""
    data = request.json
    email_username = data.get('username')
    email_domain = data.get('domain')
    
    if not email_username or not email_domain:
        return jsonify({"error": "Username and domain required"}), 400
    
    fraud_session = get_global_session()
    
    if not fraud_session.is_logged_in:
        return jsonify({"error": "Not connected to FraudCat"}), 401
    
    try:
        success = fraud_session.create_email(email_username, email_domain)
        
        if success:
            return jsonify({
                "success": True,
                "email": f"{email_username}@{email_domain}",
                "message": "Email created successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to create email"
            }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/start_listener', methods=['POST'])
def start_listener():
    """Start listening for emails on a specific address"""
    data = request.json
    email_username = data.get('email_username')
    email_domain = data.get('email_domain')
    max_iterations = data.get('max_iterations', 15)
    
    if not email_username or not email_domain:
        return jsonify({"error": "Email username and domain required"}), 400
    
    session_id = str(uuid.uuid4())
    
    listener = EmailListenerThread(
        session_id, email_username, email_domain, max_iterations
    )
    listener.daemon = True
    listener.start()
    
    active_listeners[session_id] = listener
    listener_status[session_id] = "started"
    
    return jsonify({
        "session_id": session_id,
        "email": f"{email_username}@{email_domain}",
        "message": "Listener started"
    })

@app.route('/api/start_random_listener', methods=['POST'])
def start_random_listener():
    """Create a random email and start listening"""
    data = request.json
    max_iterations = data.get('max_iterations', 15)
    
    session_id = str(uuid.uuid4())
    
    listener = EmailListenerThread(
        session_id, None, None, max_iterations
    )
    listener.daemon = True
    listener.start()
    
    active_listeners[session_id] = listener
    listener_status[session_id] = "started"
    
    return jsonify({
        "session_id": session_id,
        "message": "Random email listener started"
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

@app.route('/api/get_message_by_uid', methods=['POST'])
def get_message_by_uid():
    """Get a specific email by UID"""
    data = request.json
    uid = data.get('uid')
    
    if not uid:
        return jsonify({"error": "UID required"}), 400
    
    fraud_session = get_global_session()
    
    if not fraud_session.is_logged_in:
        return jsonify({"error": "Not connected to FraudCat"}), 401
    
    try:
        message = fraud_session.get_email_by_uid(uid)
        if message:
            return jsonify({
                "success": True,
                "message": message
            })
        else:
            return jsonify({
                "success": False,
                "error": "Message not found"
            }), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Initialize the global session on startup
    print("Initializing FraudCat session...")
    get_global_session()
    print(f"Connected: {global_fraud_session.is_logged_in}")
    print(f"Available domains: {len(global_fraud_session.available_domains)}")
    app.run(debug=False, host='0.0.0.0', port=5000)
