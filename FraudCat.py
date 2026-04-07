import requests
import time
import json
import logging
import random
import string
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                    if self.available_domains:
                        logger.info(f"Domains: {', '.join(self.available_domains[:5])}")
        except Exception as e:
            logger.error(f"Failed to fetch domains: {e}")
    
    def generate_random_user(self, length: int = 8) -> str:
        """
        Generate a random username
        """
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for _ in range(length))
    
    def get_random_domain(self) -> Optional[str]:
        """
        Get a random domain from available domains
        """
        if not self.available_domains:
            logger.error("No available domains")
            return None
        return random.choice(self.available_domains)
    
    def create_email(self, to_address: str, to_domain: str) -> bool:
        """
        Create an email by making a GET request to the inbox URL
        Returns True if successful
        """
        if not self.is_logged_in:
            logger.error("Not logged in")
            return False
        
        try:
            # Make GET request to create the email inbox
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
        """Get inbox messages using POST request"""
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
        """
        Fetch full email content by UID using the GetLetterById API endpoint
        """
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
    
    def get_email_body_by_uid(self, uid: str) -> Optional[str]:
        """
        Convenience method to get just the full email body text
        """
        email_data = self.get_email_by_uid(uid)
        if email_data:
            # Try different possible field names for the body
            body = (email_data.get('body') or 
                    email_data.get('content') or 
                    email_data.get('htmlBody') or 
                    email_data.get('textBody') or 
                    '')
            
            if body:
                logger.info(f"Retrieved {len(body)} characters of email body")
                return body
            else:
                logger.warning("Email has no body content")
                return ''
        return None
    
    def listen_for_mail(self, to_domain: str, to_address: str, fetch_full_body: bool = False, max_iterations: int = 10):
        """
        Continuously listen for new emails (checks every 20 seconds)
        Yields new messages as they arrive
        
        Args:
            to_domain: Email domain
            to_address: Email username
            fetch_full_body: If True, fetch complete email body using UID
            max_iterations: Maximum number of check iterations (each iteration = 20 seconds)
                           After max_iterations, raises TimeoutError
        
        Yields:
            New email messages as they arrive
        
        Raises:
            TimeoutError: When max_iterations is reached without receiving any messages
        """
        full_email = f"{to_address}@{to_domain}"
        logger.info(f"📡 Listening for emails at {full_email}")
        logger.info(f"Checking inbox every 20 seconds for a maximum of {max_iterations} iterations...")
        
        if fetch_full_body:
            logger.info("Will fetch full email body for each message")
        
        # Get initial message count
        current_messages = self.get_inbox(to_domain, to_address)
        self.last_message_count = len(current_messages)
        self.received_messages = current_messages.copy()
        
        logger.info(f"Initial message count: {self.last_message_count}")
        
        iteration = 0
        messages_received = False
        
        while iteration < max_iterations:
            try:
                iteration += 1
                logger.info(f"📊 Iteration {iteration}/{max_iterations}")
                
                # Fetch current inbox
                current_messages = self.get_inbox(to_domain, to_address)
                current_count = len(current_messages)
                
                # Check for new messages
                if current_count > self.last_message_count:
                    messages_received = True
                    new_messages = current_messages[self.last_message_count:]
                    
                    for message in new_messages:
                        logger.info(f"✨ New message received!")
                        
                        if fetch_full_body:
                            uid = message.get('uid')
                            if uid:
                                # Fetch FULL email content using the UID
                                logger.info(f"Fetching full content for UID: {uid}")
                                full_email_data = self.get_email_by_uid(uid)
                                
                                if full_email_data:
                                    # self._display_full_email_content(full_email_data)
                                    self.received_messages.append(full_email_data)
                                    yield full_email_data
                                else:
                                    logger.error(f"Failed to fetch full content for UID: {uid}")
                                    # self._display_message(message)
                                    self.received_messages.append(message)
                                    yield message
                            else:
                                logger.warning("Message has no UID, can't fetch full content")
                                # self._display_message(message)
                                self.received_messages.append(message)
                                yield message
                        else:
                            self._display_message(message)
                            self.received_messages.append(message)
                            yield message
                    
                    self.last_message_count = current_count
                
                # Check if we've reached max iterations (after the last iteration, don't sleep)
                if iteration >= max_iterations:
                    if not messages_received:
                        error_msg = f"⚠️ Maximum iterations ({max_iterations}) reached without receiving any messages. Timeout after {max_iterations * 20} seconds."
                        logger.error(error_msg)
                        raise TimeoutError(error_msg)
                    else:
                        logger.info(f"Listener terminated after {iteration} iterations")
                        break
                
                # Wait 20 seconds before next check
                logger.info(f"Waiting 20 seconds before next check...")
                time.sleep(20)
                
            except KeyboardInterrupt:
                logger.info("\nStopped listening")
                break
            except TimeoutError:
                # Re-raise TimeoutError to be handled by caller
                raise
            except Exception as e:
                logger.error(f"Error while listening: {e}")
                if iteration >= max_iterations:
                    if not messages_received:
                        error_msg = f"⚠️ Maximum iterations ({max_iterations}) reached with errors. Timeout after {max_iterations * 20} seconds."
                        logger.error(error_msg)
                        raise TimeoutError(error_msg) from e
                    break
                time.sleep(20)
    
    def _display_message(self, message: Dict[str, Any]):
        """Display message details (partial)"""
        print("\n" + "="*70)
        print(f"📧 NEW EMAIL RECEIVED")
        print("="*70)
        print(f"From: {message.get('from', 'Unknown')}")
        print(f"Subject: {message.get('subject', 'No subject')}")
        print(f"Date: {message.get('date', message.get('receivedAt', 'Unknown'))}")
        print(f"UID: {message.get('uid', 'N/A')}")
        
        # Display attachments if any
        attachments = message.get('attachments', [])
        if attachments:
            print(f"\n📎 Attachments: {', '.join(attachments)}")
        
        print("="*70 + "\n")
    
    def _display_full_email_content(self, email_data: Dict[str, Any]):
        """Display complete email content with full body"""
        print("\n" + "="*80)
        print(f"📧 FULL EMAIL CONTENT")
        print("="*80)
        print(f"UID: {email_data.get('uid', 'Unknown')}")
        print(f"From: {email_data.get('from', 'Unknown')}")
        print(f"To: {email_data.get('to', 'Unknown')}")
        print(f"Subject: {email_data.get('subject', 'No subject')}")
        print(f"Date: {email_data.get('date', email_data.get('receivedAt', 'Unknown'))}")
        
        # Display full body
        body = (email_data.get('body') or 
                email_data.get('content') or 
                email_data.get('htmlBody') or 
                email_data.get('textBody') or 
                '')
        
        if body:
            print(f"\n📝 FULL BODY:")
            print("-"*80)
            print(body)  # Print the ENTIRE body
            print("-"*80)
            print(f"Total characters: {len(body)}")
        else:
            print("\n📝 No body content")
        
        # Display attachments if any
        attachments = email_data.get('attachments', [])
        if attachments:
            print(f"\n📎 ATTACHMENTS ({len(attachments)}):")
            for attachment in attachments:
                name = attachment.get('fileName', attachment.get('name', 'Unknown'))
                size = attachment.get('size', 'Unknown')
                print(f"   - {name} ({size} bytes)")
        
        print("="*80 + "\n")
    
    def fetch_and_display_email_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Directly fetch and display email content using UID
        """
        print(f"\n🔍 Fetching email with UID: {uid}")
        full_email = self.get_email_by_uid(uid)
        
        if full_email:
            self._display_full_email_content(full_email)
            return full_email
        else:
            print(f"❌ Failed to fetch email with UID: {uid}")
            return None
    
    def create_and_listen(self, to_address: str, to_domain: str, fetch_full_body: bool = True, max_iterations: int = 10):
        """
        Create email with specific address and start listening for messages
        
        Args:
            to_address: Email username
            to_domain: Email domain
            fetch_full_body: If True, fetch complete email body using UID
            max_iterations: Maximum number of check iterations (each iteration = 20 seconds)
        
        Returns:
            The first message received
        
        Raises:
            TimeoutError: When max_iterations is reached without receiving any messages
        """
        # Create the email
        if not self.create_email(to_address, to_domain):
            logger.error("Failed to create email")
            return None
        
        print(f"\n✅ Email ready: {to_address}@{to_domain}")
        print(f"📡 Listening for incoming emails for {max_iterations * 20} seconds maximum...\n")
        
        # Listen for messages
        try:
            for message in self.listen_for_mail(to_domain, to_address, fetch_full_body, max_iterations):
                # Return the first message received
                return message
        except TimeoutError as e:
            logger.error(f"Timeout: {e}")
            raise  # Re-raise the exception to the caller
        except StopIteration:
            # Generator exhausted without yielding any messages
            error_msg = f"No messages received within {max_iterations * 20} seconds"
            logger.error(error_msg)
            raise TimeoutError(error_msg)
        except KeyboardInterrupt:
            print("\nStopped listening")
            raise
    
    def create_and_listen_random(self, username: str, fetch_full_body: bool = True, max_iterations: int = 10):
        """
        Create email with random user and random domain, then start listening
        
        Args:
            username: The username to use
            fetch_full_body: If True, fetch complete email body using UID
            max_iterations: Maximum number of check iterations (each iteration = 20 seconds)
        
        Returns:
            Tuple of (email_address, message)
        
        Raises:
            TimeoutError: When max_iterations is reached without receiving any messages
        """
        # Check if domains are available
        if not self.available_domains:
            logger.error("No available domains. Make sure you're logged in.")
            return None, None
        
        # Generate random user and get random domain
        random_user = username
        random_domain = self.get_random_domain()
        
        if not random_domain:
            logger.error("Failed to get random domain")
            return None, None
        
        print(f"\n🎲 Randomly generated:")
        print(f"   User: {random_user}")
        print(f"   Domain: {random_domain}")
        
        # Create the email
        if not self.create_email(random_user, random_domain):
            logger.error("Failed to create email")
            return None, None
        
        print(f"\n✅ Email ready: {random_user}@{random_domain}")
        print(f"📡 Listening for incoming emails for {max_iterations * 20} seconds maximum...\n")
        
        # Listen for messages
        try:
            for message in self.listen_for_mail(random_domain, random_user, fetch_full_body, max_iterations):
                # Return the email address and message
                return f"{random_user}@{random_domain}", message
        except TimeoutError as e:
            logger.error(f"Timeout: {e}")
            raise  # Re-raise the exception to the caller
        except StopIteration:
            # Generator exhausted without yielding any messages
            error_msg = f"No messages received within {max_iterations * 20} seconds"
            logger.error(error_msg)
            raise TimeoutError(error_msg)
        except KeyboardInterrupt:
            print("\nStopped listening")
            raise
    
    def get_received_messages(self) -> List[Dict]:
        """Get all received messages"""
        return self.received_messages
    
    def logout(self):
        try:
            self.session.get(f"{self.base_url}/Account/Logout")
            self.is_logged_in = False
            logger.info("Logged out")
        except:
            pass
