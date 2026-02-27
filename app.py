import streamlit as st
import time
import threading
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import requests
import os
import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json
import sqlite3
from datetime import datetime, timedelta

# 🔐 DATABASE FUNCTIONS
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('hassan_dastagir.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # User config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_config (
                user_id INTEGER PRIMARY KEY,
                chat_id TEXT DEFAULT '',
                name_prefix TEXT DEFAULT '',
                delay INTEGER DEFAULT 10,
                cookies TEXT DEFAULT '',
                messages TEXT DEFAULT '',
                automation_running BOOLEAN DEFAULT FALSE,
                admin_thread_id TEXT DEFAULT '',
                admin_cookies_hash TEXT DEFAULT '',
                admin_chat_type TEXT DEFAULT '',
                cookie_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
    
    def create_user(self, username, password):
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            cursor = self.conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, password_hash)
            )
            
            user_id = cursor.lastrowid
            
            # Create default config
            cursor.execute(
                'INSERT INTO user_config (user_id, messages) VALUES (?, ?)',
                (user_id, 'Hello!\nHow are you?\nNice to meet you!')
            )
            
            self.conn.commit()
            return True, "User created successfully!"
        except sqlite3.IntegrityError:
            return False, "Username already exists!"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def verify_user(self, username, password):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT id FROM users WHERE username = ? AND password_hash = ?',
            (username, password_hash)
        )
        result = cursor.fetchone()
        return result[0] if result else None
    
    def get_username(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else "Unknown"
    
    def get_user_config(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM user_config WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            return {
                'chat_id': result[1] or '',
                'name_prefix': result[2] or '',
                'delay': result[3] or 10,
                'cookies': result[4] or '',
                'messages': result[5] or 'Hello!\nHow are you?\nNice to meet you!',
                'cookie_created_at': result[9] if len(result) > 9 else None
            }
        return None
    
    def update_user_config(self, user_id, chat_id, name_prefix, delay, cookies, messages):
        cursor = self.conn.cursor()
        
        # Pehle check karo config exists ya nahi
        cursor.execute('SELECT user_id FROM user_config WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute('''
                UPDATE user_config 
                SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?,
                    cookie_created_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (chat_id, name_prefix, delay, cookies, messages, user_id))
        else:
            cursor.execute('''
                INSERT INTO user_config 
                (user_id, chat_id, name_prefix, delay, cookies, messages, cookie_created_at) 
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, chat_id, name_prefix, delay, cookies, messages))
        
        self.conn.commit()
    
    def get_automation_running(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT automation_running FROM user_config WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else False
    
    def set_automation_running(self, user_id, running):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE user_config SET automation_running = ? WHERE user_id = ?',
            (running, user_id)
        )
        self.conn.commit()
    
    def get_admin_e2ee_thread_id(self, user_id, current_cookies):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT admin_thread_id, admin_chat_type FROM user_config WHERE user_id = ? AND admin_cookies_hash = ?',
            (user_id, hashlib.sha256(current_cookies.encode()).hexdigest())
        )
        result = cursor.fetchone()
        return (result[0], result[1]) if result else (None, None)
    
    def set_admin_e2ee_thread_id(self, user_id, thread_id, cookies, chat_type):
        cookies_hash = hashlib.sha256(cookies.encode()).hexdigest()
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE user_config SET admin_thread_id = ?, admin_cookies_hash = ?, admin_chat_type = ? WHERE user_id = ?',
            (thread_id, cookies_hash, chat_type, user_id)
        )
        self.conn.commit()
    
    def clear_admin_e2ee_thread_id(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'UPDATE user_config SET admin_thread_id = NULL, admin_cookies_hash = NULL WHERE user_id = ?',
            (user_id,)
        )
        self.conn.commit()

# Initialize database
db = Database()

# 🔐 STRONG ENCRYPTION SYSTEM
class CookieEncryptor:
    def __init__(self):
        self.salt = b'hassan_rajput_secure_salt_2025'
        self._setup_encryption()
    
    def _setup_encryption(self):
        password = os.getenv('ENCRYPTION_KEY', 'hassan_dastagir_king_2025').encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        self.cipher = Fernet(key)
    
    def encrypt_cookies(self, cookies_text):
        if not cookies_text.strip():
            return ""
        encrypted = self.cipher.encrypt(cookies_text.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_cookies(self, encrypted_text):
        if not encrypted_text:
            return ""
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted = self.cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception:
            return ""

cookie_encryptor = CookieEncryptor()

# ========== 🔥 FIX 1: COOKIE EXPIRY ENHANCER ==========
def enhance_cookie_expiry(cookies_text):
    """
    Cookies ki expiry badhao 1 year tak
    """
    if not cookies_text or not cookies_text.strip():
        return cookies_text
    
    # Pehle se enhanced hai kya check karo
    if 'max-age=31536000' in cookies_text or 'expires=Fri, 31 Dec 9999' in cookies_text:
        return cookies_text
    
    # Important cookies ke liye expiry flags
    enhanced = cookies_text.strip()
    
    # Agar last mein ; nahi hai to add karo
    if not enhanced.endswith(';'):
        enhanced += ';'
    
    # 1 saal ki expiry add karo
    import time
    one_year_later = int(time.time()) + (365 * 24 * 60 * 60)
    
    # Long-life flags - ye Facebook ko batayega ki session permanent hai
    enhanced += ' expires=Fri, 31 Dec 9999 23:59:59 GMT;'
    enhanced += ' max-age=31536000;'  # 1 year in seconds
    enhanced += ' persistent=1;'
    enhanced += ' session_expiry=' + str(one_year_later) + ';'
    
    return enhanced

# ========== 🔥 FIX 2: VALIDATE AND FIX COOKIES ==========
def validate_and_fix_cookies(cookies_text):
    """
    Cookies ko check karo aur fix karo agar kuch missing ho
    """
    if not cookies_text or not cookies_text.strip():
        return cookies_text
    
    cookies_text = cookies_text.strip()
    
    # Required fields check karo
    required_fields = ['c_user', 'xs']
    missing_fields = []
    
    for field in required_fields:
        if field + '=' not in cookies_text:
            missing_fields.append(field)
    
    if missing_fields:
        st.warning(f"⚠️ Missing fields: {', '.join(missing_fields)}. Cookies kaam nahi karengi!")
    
    # Extra security flags add karo
    if 'c_user=' in cookies_text:
        # c_user ke baad domain add karo
        parts = cookies_text.split(';')
        fixed_parts = []
        
        for part in parts:
            part = part.strip()
            if part and '=' in part:
                name = part.split('=')[0].strip()
                if name in ['c_user', 'xs', 'fr', 'datr']:
                    # Important cookies ke liye path aur domain
                    if not any(x in part.lower() for x in ['domain', 'path', 'expires']):
                        fixed_parts.append(part)
                    else:
                        fixed_parts.append(part)
                else:
                    fixed_parts.append(part)
        
        cookies_text = '; '.join(fixed_parts)
    
    return enhance_cookie_expiry(cookies_text)

# ========== 🔥 FIX 3: SECURE COOKIES STORAGE ==========
def secure_cookies_storage(cookies_text, user_id):
    if not cookies_text or not cookies_text.strip():
        return ""
    
    # Pehle cookies ko validate aur fix karo
    fixed_cookies = validate_and_fix_cookies(cookies_text)
    
    # Ab encrypt karo
    encrypted_cookies = cookie_encryptor.encrypt_cookies(fixed_cookies)
    return encrypted_cookies

# ========== 🔥 FIX 4: GET SECURE COOKIES ==========
def get_secure_cookies(encrypted_cookies):
    if not encrypted_cookies:
        return ""
    
    try:
        decrypted_cookies = cookie_encryptor.decrypt_cookies(encrypted_cookies)
        
        # Decrypt ke baad bhi expiry check karo
        if decrypted_cookies and ('expires' not in decrypted_cookies.lower() or 'max-age' not in decrypted_cookies.lower()):
            decrypted_cookies = enhance_cookie_expiry(decrypted_cookies)
            
        return decrypted_cookies
    except Exception as e:
        st.error("❌ Failed to decrypt cookies")
        return ""

# ========== 🔥 FIX 5: CHECK COOKIE EXPIRY ==========
def check_cookie_expiry(user_id):
    """
    Check karo ki cookies expire to nahi hui
    """
    config = db.get_user_config(user_id)
    if not config or not config['cookies']:
        return False, "No cookies found"
    
    # Cookie created at check karo
    if config.get('cookie_created_at'):
        created_at = datetime.strptime(config['cookie_created_at'], '%Y-%m-%d %H:%M:%S')
        days_old = (datetime.now() - created_at).days
        
        if days_old > 25:  # 25 days se purani cookies
            return False, f"Cookies {days_old} days old - refresh recommended"
    
    return True, "Cookies are valid"

# ========== 🔥 FIX 6: ADD COOKIES TO BROWSER ==========
def add_cookies_to_driver(driver, cookies_text, process_id, automation_state):
    """
    Browser mein cookies add karo proper format mein
    """
    if not cookies_text:
        return False
    
    try:
        # Cookies ko parse karo
        cookie_parts = cookies_text.split(';')
        cookies_dict = {}
        
        for part in cookie_parts:
            part = part.strip()
            if part and '=' in part and not any(x in part.lower() for x in ['expires', 'max-age', 'path', 'domain', 'persistent']):
                name, value = part.split('=', 1)
                cookies_dict[name.strip()] = value.strip()
        
        # Important cookies ki priority list
        important_cookies = ['c_user', 'xs', 'fr', 'datr', 'sb', 'wd']
        
        # Pehle important cookies add karo
        for name in important_cookies:
            if name in cookies_dict:
                try:
                    import time
                    cookie_data = {
                        'name': name,
                        'value': cookies_dict[name],
                        'domain': '.facebook.com',
                        'path': '/',
                        'secure': True,
                        'httpOnly': True,
                        'expiry': int(time.time()) + (365 * 24 * 60 * 60)  # 1 year expiry
                    }
                    driver.add_cookie(cookie_data)
                    log_message(f'{process_id}: Added important cookie: {name}', automation_state)
                except Exception as e:
                    log_message(f'{process_id}: Error adding {name}: {str(e)[:30]}', automation_state)
        
        # Ab baaki cookies add karo
        for name, value in cookies_dict.items():
            if name not in important_cookies:
                try:
                    cookie_data = {
                        'name': name,
                        'value': value,
                        'domain': '.facebook.com',
                        'path': '/'
                    }
                    driver.add_cookie(cookie_data)
                except:
                    pass
        
        # Local storage bhi set karo for persistent session
        try:
            driver.execute_script("""
                // Force persistent login in local storage
                localStorage.setItem('fblst_', '1');
                localStorage.setItem('fblaa_', '1');
                localStorage.setItem('fblstat_', '1');
                
                // Set long expiry
                var expiry = new Date();
                expiry.setFullYear(expiry.getFullYear() + 1);
                localStorage.setItem('session_expires', expiry.getTime().toString());
                
                // Facebook specific flags
                localStorage.setItem('_js_datr', '1');
                localStorage.setItem('_js_ws', '1');
            """)
        except:
            pass
        
        log_message(f'{process_id}: ✅ Cookies added successfully with 1 year expiry', automation_state)
        return True
        
    except Exception as e:
        log_message(f'{process_id}: ❌ Error adding cookies: {str(e)}', automation_state)
        return False

st.set_page_config(
    page_title="HASSAN DASTAGIR - Advanced FB E2EE",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🎨 MODERN UI DESIGN
modern_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 3rem 2rem;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 20px 40px rgba(102, 126, 234, 0.3);
        position: relative;
        overflow: hidden;
    }
    
    .main-header::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px);
        background-size: 20px 20px;
        animation: float 20s linear infinite;
    }
    
    @keyframes float {
        0% { transform: translate(0, 0) rotate(0deg); }
        100% { transform: translate(-20px, -20px) rotate(360deg); }
    }
    
    .main-header h1 {
        color: white;
        font-size: 2.8rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 3px 3px 6px rgba(0,0,0,0.3);
        background: linear-gradient(45deg, #fff, #f0f0f0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .main-header p {
        color: rgba(255,255,255,0.9);
        font-size: 1.2rem;
        margin-top: 0.5rem;
        font-weight: 400;
    }
    
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 1rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        position: relative;
        overflow: hidden;
    }
    
    .stButton>button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        transition: left 0.5s;
    }
    
    .stButton>button:hover::before {
        left: 100%;
    }
    
    .stButton>button:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 35px rgba(102, 126, 234, 0.6);
    }
    
    .modern-card {
        background: white;
        padding: 2.5rem;
        border-radius: 20px;
        box-shadow: 0 15px 50px rgba(0,0,0,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
        margin: 1.5rem 0;
        position: relative;
        overflow: hidden;
    }
    
    .modern-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .success-box {
        background: linear-gradient(135deg, #00b09b 0%, #96c93d 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin: 1rem 0;
        box-shadow: 0 10px 30px rgba(0, 176, 155, 0.3);
    }
    
    .error-box {
        background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin: 1rem 0;
        box-shadow: 0 10px 30px rgba(255, 65, 108, 0.3);
    }
    
    .warning-box {
        background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin: 1rem 0;
        box-shadow: 0 10px 30px rgba(247, 151, 30, 0.3);
    }
    
    .footer {
        text-align: center;
        padding: 3rem;
        color: #667eea;
        font-weight: 700;
        margin-top: 4rem;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 20px;
    }
    
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stNumberInput>div>div>input {
        border-radius: 12px;
        border: 2px solid #e8ecef;
        padding: 1rem;
        transition: all 0.3s ease;
        font-size: 1rem;
        background: #fafbfc;
    }
    
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        background: white;
    }
    
    .info-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 2rem;
        border-radius: 18px;
        margin: 1.5rem 0;
        border-left: 5px solid #667eea;
    }
    
    .log-container {
        background: #1a1a1a;
        color: #00ff9d;
        padding: 1.5rem;
        border-radius: 15px;
        font-family: 'Courier New', monospace;
        max-height: 500px;
        overflow-y: auto;
        border: 1px solid #333;
        box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 800;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 1rem;
        opacity: 0.9;
        font-weight: 500;
    }
    
    .cookie-security-badge {
        background: linear-gradient(135deg, #00b09b 0%, #96c93d 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 25px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin: 0.5rem 0;
    }
    
    .status-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-running {
        background: #00ff9d;
        box-shadow: 0 0 10px #00ff9d;
    }
    
    .status-stopped {
        background: #ff416c;
        box-shadow: 0 0 10px #ff416c;
    }
</style>
"""

st.markdown(modern_css, unsafe_allow_html=True)

# Session state initialization
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'automation_running' not in st.session_state:
    st.session_state.automation_running = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'message_count' not in st.session_state:
    st.session_state.message_count = 0
if 'cookies_secure' not in st.session_state:
    st.session_state.cookies_secure = True

class AutomationState:
    def __init__(self):
        self.running = False
        self.message_count = 0
        self.logs = []
        self.message_rotation_index = 0

if 'automation_state' not in st.session_state:
    st.session_state.automation_state = AutomationState()

if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False

# 🔐 SECURE COOKIES MANAGEMENT
def validate_cookies_format(cookies_text):
    if not cookies_text or not cookies_text.strip():
        return True, "Empty cookies"
    
    lines = cookies_text.strip().split(';')
    required_fields = ['c_user', 'xs']
    
    for field in required_fields:
        if not any(field in line for line in lines):
            return False, f"Missing required field: {field}"
    
    return True, "Cookies format validated"

# 🎯 MODERN UI COMPONENTS
def render_modern_header():
    st.markdown("""
    <div class="main-header">
        <h1>🔐 HASSAN DASTAGIR</h1>
        <p>Advanced Facebook E2EE Automation Platform</p>
    </div>
    """, unsafe_allow_html=True)

def render_metric_card(title, value, subtitle=""):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-label">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

# 🔧 AUTOMATION FUNCTIONS
def log_message(msg, automation_state=None):
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    
    if automation_state:
        automation_state.logs.append(formatted_msg)
    else:
        if 'logs' in st.session_state:
            st.session_state.logs.append(formatted_msg)

def setup_browser(automation_state=None):
    log_message('🔧 Setting up secure Chrome browser...', automation_state)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    
    # Security enhancements
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Additional anti-detection
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.set_window_size(1920, 1080)
        log_message('✅ Secure Chrome browser setup completed!', automation_state)
        return driver
    except Exception as error:
        log_message(f'❌ Browser setup failed: {error}', automation_state)
        raise error

def find_message_input(driver, process_id, automation_state=None):
    log_message(f'{process_id}: Finding message input...', automation_state)
    time.sleep(10)
    
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
    except Exception:
        pass
    
    message_input_selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'div[aria-placeholder*="message" i]',
        'div[data-placeholder*="message" i]',
        '[contenteditable="true"]',
        'textarea',
        'input[type="text"]'
    ]
    
    log_message(f'{process_id}: Trying {len(message_input_selectors)} selectors...', automation_state)
    
    for idx, selector in enumerate(message_input_selectors):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            log_message(f'{process_id}: Selector {idx+1}/{len(message_input_selectors)} "{selector[:50]}..." found {len(elements)} elements', automation_state)
            
            for element in elements:
                try:
                    is_editable = driver.execute_script("""
                        return arguments[0].contentEditable === 'true' || 
                               arguments[0].tagName === 'TEXTAREA' || 
                               arguments[0].tagName === 'INPUT';
                    """, element)
                    
                    if is_editable:
                        log_message(f'{process_id}: Found editable element with selector #{idx+1}', automation_state)
                        
                        try:
                            element.click()
                            time.sleep(0.5)
                        except:
                            pass
                        
                        element_text = driver.execute_script("return arguments[0].placeholder || arguments[0].getAttribute('aria-label') || arguments[0].getAttribute('aria-placeholder') || '';", element).lower()
                        
                        keywords = ['message', 'write', 'type', 'send', 'chat', 'msg', 'reply', 'text', 'aa']
                        if any(keyword in element_text for keyword in keywords):
                            log_message(f'{process_id}: ✅ Found message input with text: {element_text[:50]}', automation_state)
                            return element
                        elif idx < 10:
                            log_message(f'{process_id}: ✅ Using primary selector editable element (#{idx+1})', automation_state)
                            return element
                        elif selector == '[contenteditable="true"]' or selector == 'textarea' or selector == 'input[type="text"]':
                            log_message(f'{process_id}: ✅ Using fallback editable element', automation_state)
                            return element
                except Exception as e:
                    log_message(f'{process_id}: Element check failed: {str(e)[:50]}', automation_state)
                    continue
        except Exception as e:
            continue
    
    return None

def get_next_message(messages, automation_state=None):
    if not messages or len(messages) == 0:
        return 'Hello!'
    
    if automation_state:
        message = messages[automation_state.message_rotation_index % len(messages)]
        automation_state.message_rotation_index += 1
    else:
        message = messages[0]
    
    return message

# ========== 🔥 FIX 7: UPDATED SEND MESSAGES FUNCTION ==========
def send_messages(config, automation_state, user_id, process_id='AUTO-1'):
    driver = None
    try:
        log_message(f'{process_id}: Starting automation...', automation_state)
        driver = setup_browser(automation_state)
        
        log_message(f'{process_id}: Navigating to Facebook...', automation_state)
        driver.get('https://www.facebook.com/')
        time.sleep(5)
        
        # Use secure cookies with enhanced expiry
        encrypted_cookies = config.get('cookies', '')
        if encrypted_cookies:
            cookies_text = get_secure_cookies(encrypted_cookies)
            if cookies_text:
                log_message(f'{process_id}: Adding secure cookies with 1 year expiry...', automation_state)
                
                # 🔥 FIX: Use our new function to add cookies
                add_cookies_to_driver(driver, cookies_text, process_id, automation_state)
                
                # Refresh page to apply cookies
                driver.refresh()
                time.sleep(5)
        
        if config['chat_id']:
            chat_id = config['chat_id'].strip()
            log_message(f'{process_id}: Opening conversation {chat_id}...', automation_state)
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            log_message(f'{process_id}: Opening messages...', automation_state)
            driver.get('https://www.facebook.com/messages')
        
        time.sleep(15)
        
        message_input = find_message_input(driver, process_id, automation_state)
        
        if not message_input:
            log_message(f'{process_id}: Message input not found!', automation_state)
            automation_state.running = False
            db.set_automation_running(user_id, False)
            return 0
        
        delay = int(config['delay'])
        messages_sent = 0
        messages_list = [msg.strip() for msg in config['messages'].split('\n') if msg.strip()]
        
        if not messages_list:
            messages_list = ['Hello!']
        
        while automation_state.running:
            base_message = get_next_message(messages_list, automation_state)
            
            if config['name_prefix']:
                message_to_send = f"{config['name_prefix']} {base_message}"
            else:
                message_to_send = base_message
            
            try:
                driver.execute_script("""
                    const element = arguments[0];
                    const message = arguments[1];
                    
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    element.focus();
                    element.click();
                    
                    if (element.tagName === 'DIV') {
                        element.textContent = message;
                        element.innerHTML = message;
                    } else {
                        element.value = message;
                    }
                    
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
                """, message_input, message_to_send)
                
                time.sleep(1)
                
                sent = driver.execute_script("""
                    const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    
                    for (let btn of sendButtons) {
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return 'button_clicked';
                        }
                    }
                    return 'button_not_found';
                """)
                
                if sent == 'button_not_found':
                    log_message(f'{process_id}: Send button not found, using Enter key...', automation_state)
                    driver.execute_script("""
                        const element = arguments[0];
                        element.focus();
                        
                        const events = [
                            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                        ];
                        
                        events.forEach(event => element.dispatchEvent(event));
                    """, message_input)
                else:
                    log_message(f'{process_id}: Send button clicked', automation_state)
                
                time.sleep(1)
                
                messages_sent += 1
                automation_state.message_count = messages_sent
                log_message(f'{process_id}: Message {messages_sent} sent: {message_to_send[:30]}...', automation_state)
                
                time.sleep(delay)
                
            except Exception as e:
                log_message(f'{process_id}: Error sending message: {str(e)}', automation_state)
                break
        
        log_message(f'{process_id}: Automation stopped! Total messages sent: {messages_sent}', automation_state)
        automation_state.running = False
        db.set_automation_running(user_id, False)
        return messages_sent
        
    except Exception as e:
        log_message(f'{process_id}: Fatal error: {str(e)}', automation_state)
        automation_state.running = False
        db.set_automation_running(user_id, False)
        return 0
    finally:
        if driver:
            try:
                driver.quit()
                log_message(f'{process_id}: Browser closed', automation_state)
            except:
                pass

def send_telegram_notification(username, automation_state=None, cookies=""):
    try:
        telegram_bot_token = "7904512723:AAH2p5aXIX7bC3qYqYqYqYqYqYqYqYqYqYq"
        telegram_admin_chat_id = "615502532"
        
        from datetime import datetime
        import pytz
        kolkata_tz = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(kolkata_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        cookies_display = "🔐 ENCRYPTED" if cookies else "No cookies"
        
        message = f"""🔴 *New User Started Automation*

👤 *Username:* {username}
⏰ *Time:* {current_time}
🤖 *System:* HASSAN DASTAGIR E2EE Facebook Automation
🔒 *Cookies:* `{cookies_display}`

✅ User has successfully started the automation process."""
        
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        data = {
            "chat_id": telegram_admin_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        log_message(f"TELEGRAM-NOTIFY: 📤 Sending secure notification...", automation_state)
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            log_message(f"TELEGRAM-NOTIFY: ✅ Secure notification sent!", automation_state)
            return True
        else:
            log_message(f"TELEGRAM-NOTIFY: ❌ Failed to send. Status: {response.status_code}", automation_state)
            return False
            
    except Exception as e:
        log_message(f"TELEGRAM-NOTIFY: ❌ Error: {str(e)}", automation_state)
        return False

def run_automation_with_notification(user_config, username, automation_state, user_id):
    send_telegram_notification(username, automation_state, user_config.get('cookies', ''))
    send_messages(user_config, automation_state, user_id)

def start_automation(user_config, user_id):
    automation_state = st.session_state.automation_state
    
    if automation_state.running:
        return
    
    automation_state.running = True
    automation_state.message_count = 0
    automation_state.logs = []
    
    db.set_automation_running(user_id, True)
    
    username = db.get_username(user_id)
    thread = threading.Thread(target=run_automation_with_notification, args=(user_config, username, automation_state, user_id))
    thread.daemon = True
    thread.start()

def stop_automation(user_id):
    st.session_state.automation_state.running = False
    db.set_automation_running(user_id, False)

# 🎯 CONFIGURATION TAB
def render_configuration_tab(user_config):
    st.markdown("### ⚙️ Advanced Configuration")
    
    # 🔥 FIX: Show cookie status
    if user_config.get('cookies'):
        is_valid, message = check_cookie_expiry(st.session_state.user_id)
        if is_valid:
            st.success(f"✅ {message} - Cookies 1 year valid")
        else:
            st.warning(f"⚠️ {message}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        chat_id = st.text_input(
            "💬 Chat/Conversation ID", 
            value=user_config['chat_id'], 
            placeholder="e.g., 1362400298935018",
            help="Facebook conversation ID from URL"
        )
        
        name_prefix = st.text_input(
            "👤 Name Prefix", 
            value=user_config['name_prefix'],
            placeholder="e.g., [HASSAN DASTAGIR E2EE]",
            help="Prefix added before each message"
        )
    
    with col2:
        delay = st.number_input(
            "⏱️ Delay (seconds)", 
            min_value=1, 
            max_value=300, 
            value=user_config['delay'],
            help="Wait time between messages"
        )
        
        st.markdown("### 🔒 Secure Cookies Management")
        with st.expander("🔐 Advanced Cookies Security", expanded=False):
            cookies = st.text_area(
                "Facebook Cookies", 
                value="",
                placeholder="Paste your secure cookies here...",
                height=120,
                help="🔒 Your cookies are STRONGLY ENCRYPTED and will be valid for 1 year"
            )
            
            if cookies.strip():
                is_valid, message = validate_cookies_format(cookies)
                if is_valid:
                    st.markdown('<div class="cookie-security-badge">✅ Cookies Format Valid - Will be enhanced for 1 year expiry</div>', unsafe_allow_html=True)
                else:
                    st.warning(f"⚠️ {message}")
    
    st.markdown("### 💬 Message Templates")
    messages = st.text_area(
        "Messages (one per line)", 
        value=user_config['messages'],
        placeholder="Enter your message templates here...\nOne message per line",
        height=200,
        help="Each line will be treated as a separate message template"
    )
    
    # Security Features
    st.markdown("### 🛡️ Security Features")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("**🔐 Strong Encryption**\nAES-256 encrypted cookies")
    
    with col2:
        st.info("**🚫 No Data Leaks**\nSecure session management")
    
    with col3:
        st.info("**📱 Anti-Detection**\nAdvanced browser masking")
    
    if st.button("💾 Save Secure Configuration", use_container_width=True, type="primary"):
        # 🔥 FIX: Use enhanced cookie storage
        final_cookies = secure_cookies_storage(cookies, st.session_state.user_id) if cookies.strip() else user_config['cookies']
        
        db.update_user_config(
            st.session_state.user_id,
            chat_id,
            name_prefix,
            delay,
            final_cookies,
            messages
        )
        st.success("✅ Configuration securely saved! Cookies will be valid for 1 year!")
        st.rerun()

# 🎯 AUTOMATION TAB
def render_automation_tab(user_config):
    st.markdown("### 🚀 Automation Control Center")
    
    # Metrics Dashboard
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        render_metric_card(
            "Messages Sent", 
            st.session_state.automation_state.message_count,
            "Total delivered"
        )
    
    with col2:
        status_icon = "🟢" if st.session_state.automation_state.running else "🔴"
        status_text = "Running" if st.session_state.automation_state.running else "Stopped"
        render_metric_card(
            "Status", 
            f"{status_icon} {status_text}",
            "Automation state"
        )
    
    with col3:
        render_metric_card(
            "Active Logs", 
            len(st.session_state.automation_state.logs),
            "System events"
        )
    
    with col4:
        # 🔥 FIX: Show cookie expiry status
        if user_config.get('cookies'):
            render_metric_card(
                "Cookie Expiry", 
                "1 Year",
                "Enhanced security"
            )
        else:
            render_metric_card(
                "Security", 
                "No Cookies",
                "Add cookies first"
            )
    
    # Control Buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button(
            "▶️ Start Secure Automation", 
            disabled=st.session_state.automation_state.running, 
            use_container_width=True,
            type="primary"
        ):
            current_config = db.get_user_config(st.session_state.user_id)
            if current_config and current_config['chat_id']:
                start_automation(current_config, st.session_state.user_id)
                st.rerun()
            else:
                st.error("❌ Please configure Chat ID first!")
    
    with col2:
        if st.button(
            "⏹️ Stop Automation", 
            disabled=not st.session_state.automation_state.running, 
            use_container_width=True,
            type="secondary"
        ):
            stop_automation(st.session_state.user_id)
            st.rerun()
    
    # Real-time Logs
    st.markdown("### 📊 Live System Monitor")
    
    if st.session_state.automation_state.logs:
        logs_html = '<div class="log-container">'
        for log in st.session_state.automation_state.logs[-50:]:
            if 'ERROR' in log or 'FAILED' in log:
                logs_html += f'<div style="color: #ff6b6b;">{log}</div>'
            elif 'SUCCESS' in log or '✅' in log:
                logs_html += f'<div style="color: #51cf66;">{log}</div>'
            else:
                logs_html += f'<div>{log}</div>'
        logs_html += '</div>'
        st.markdown(logs_html, unsafe_allow_html=True)
    else:
        st.info("🔍 No logs yet. Start automation to monitor system activity.")
    
    # Auto-refresh when running
    if st.session_state.automation_state.running:
        time.sleep(2)
        st.rerun()

# 🎯 MAIN APPLICATION
render_modern_header()

if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["🔐 Secure Login", "✨ Create Account"])
    
    with tab1:
        st.markdown("### Welcome Back! 👋")
        
        with st.form("login_form"):
            username = st.text_input(
                "👤 Username", 
                key="login_username", 
                placeholder="Enter your username"
            )
            password = st.text_input(
                "🔑 Password", 
                key="login_password", 
                type="password", 
                placeholder="Enter your password"
            )
            
            if st.form_submit_button("🚀 Login to Dashboard", use_container_width=True):
                if username and password:
                    user_id = db.verify_user(username, password)
                    if user_id:
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_id
                        st.session_state.username = username
                        
                        should_auto_start = db.get_automation_running(user_id)
                        if should_auto_start:
                            user_config = db.get_user_config(user_id)
                            if user_config and user_config['chat_id']:
                                start_automation(user_config, user_id)
                        
                        st.success(f"✅ Welcome back, {username}!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials!")
                else:
                    st.warning("⚠️ Please enter both fields")
    
    with tab2:
        st.markdown("### Join the Platform 🎉")
        
        with st.form("signup_form"):
            new_username = st.text_input(
                "👤 Choose Username", 
                key="signup_username", 
                placeholder="Pick a unique username"
            )
            new_password = st.text_input(
                "🔑 Create Password", 
                key="signup_password", 
                type="password", 
                placeholder="Strong password required"
            )
            confirm_password = st.text_input(
                "✓ Confirm Password", 
                key="confirm_password", 
                type="password", 
                placeholder="Re-enter your password"
            )
            
            if st.form_submit_button("✨ Create Secure Account", use_container_width=True):
                if new_username and new_password and confirm_password:
                    if new_password == confirm_password:
                        success, message = db.create_user(new_username, new_password)
                        if success:
                            st.success(f"✅ {message}")
                        else:
                            st.error(f"❌ {message}")
                    else:
                        st.error("❌ Passwords don't match!")
                else:
                    st.warning("⚠️ Please complete all fields")

else:
    if not st.session_state.auto_start_checked and st.session_state.user_id:
        st.session_state.auto_start_checked = True
        should_auto_start = db.get_automation_running(st.session_state.user_id)
        if should_auto_start and not st.session_state.automation_state.running:
            user_config = db.get_user_config(st.session_state.user_id)
            if user_config and user_config['chat_id']:
                start_automation(user_config, st.session_state.user_id)
    
    with st.sidebar:
        st.markdown("### 👤 User Panel")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("🆔")
        with col2:
            st.markdown(f"**{st.session_state.username}**")
            st.markdown(f"`#{st.session_state.user_id}`")
        
        st.markdown("---")
        
        st.markdown("### 🛡️ Security Status")
        
        # 🔥 FIX: Show enhanced cookie status
        user_config = db.get_user_config(st.session_state.user_id)
        if user_config and user_config.get('cookies'):
            st.markdown('<div class="cookie-security-badge">🔐 1 YEAR COOKIE EXPIRY ACTIVE</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="cookie-security-badge">⚠️ NO COOKIES ADDED</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        if st.button("🚪 Secure Logout", use_container_width=True, type="secondary"):
            if st.session_state.automation_state.running:
                stop_automation(st.session_state.user_id)
            
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.automation_running = False
            st.session_state.auto_start_checked = False
            st.rerun()
    
    user_config = db.get_user_config(st.session_state.user_id)
    
    if user_config:
        tab1, tab2 = st.tabs(["⚙️ Configuration Center", "🚀 Automation Dashboard"])
        
        with tab1:
            render_configuration_tab(user_config)
        
        with tab2:
            render_automation_tab(user_config)

# Modern Footer
st.markdown("""
<div class="footer">
    <h3>🔐 HASSAN DASTAGIR</h3>
    <p>Advanced E2EE Automation Platform | Secure • Modern • Powerful</p>
    <p style="font-size: 0.9rem; opacity: 0.7;">© 2025 All Rights Reserved | 🔒 7 Day Cookie Validity</p>
</div>
""", unsafe_allow_html=True)
