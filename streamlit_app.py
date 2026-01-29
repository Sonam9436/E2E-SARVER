import streamlit as st
import threading, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import database as db

st.set_page_config(page_title="Automation", page_icon="🔥", layout="wide")

# ------------------------------------------------------------------------------------
# 🔥 NEW LIVE LOGS SYSTEM
# ------------------------------------------------------------------------------------
def init_live_logs(max_lines: int = 200):
    if "live_logs" not in st.session_state:
        st.session_state.live_logs = []
    if "live_logs_max" not in st.session_state:
        st.session_state.live_logs_max = max_lines

def live_log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    init_live_logs()
    st.session_state.live_logs.append(line)
    if len(st.session_state.live_logs) > st.session_state.live_logs_max:
        st.session_state.live_logs = st.session_state.live_logs[-st.session_state.live_logs_max:]

def render_live_console():
    st.markdown('<div class="logbox">', unsafe_allow_html=True)
    for line in st.session_state.live_logs[-100:]:
        st.markdown(f"<pre style='margin:0; padding:0; color:#0ff;'>{line}</pre>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
# ------------------------------------------------------------------------------------

# ---------------- CSS ----------------
st.markdown("""
<style>
.stApp {
    background: url('https://i.postimg.cc/qq41rSVP/44e54h810v9b1.jpg') no-repeat center center fixed !important;
    background-size: cover !important;
}
.stApp::before {
    content: ""; position: fixed; top:0; left:0; width:100%; height:100%;
    background: rgba(0,0,0,0.10); z-index:0; pointer-events:none;
}
.stCard {background: rgba(255,255,255,0.02) !important;}
.logbox {
    background: rgba(0,0,0,0.55);
    color:#0ff;
    padding:15px;
    height:300px;
    overflow:auto;
    border-radius:20px;
    box-shadow:0 0 20px rgba(0,255,255,0.35);
    font-family: Consolas, monospace;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="text-align:center;">E2EE SERVER</h1>', unsafe_allow_html=True)

# ---------------- SESSION ----------------
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "automation_running" not in st.session_state: st.session_state.automation_running = False
if "automation_state" not in st.session_state:
    st.session_state.automation_state = type('obj',(object,),{
        "running": False,
        "message_count": 0,
        "message_rotation_index": 0
    })()

init_live_logs()

# ---------------- LOGIN ----------------
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Create Account"])
    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            uid = db.verify_user(u, p)
            if uid:
                st.session_state.logged_in = True
                st.session_state.user_id = uid
                cfg = db.get_user_config(uid)

                st.session_state.chat_id = cfg.get("chat_id", "")
                st.session_state.chat_type = cfg.get("chat_type", "E2EE")
                st.session_state.delay = cfg.get("delay", 15)
                st.session_state.cookies = cfg.get("cookies", "")
                st.session_state.messages = cfg.get("messages", "").split("\n") if cfg.get("messages") else []

                if cfg.get("running", False):
                    st.session_state.automation_running = True
                    st.session_state.automation_state.running = True

                st.rerun()
            else:
                st.error("Invalid login")

    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        npc = st.text_input("Confirm Password", type="password")
        if st.button("Create User"):
            if np != npc:
                st.error("Passwords do not match")
            else:
                ok, msg = db.create_user(nu, np)
                if ok: st.success("User created!")
                else: st.error(msg)

    st.stop()

# ---------------- DASHBOARD ----------------
st.subheader(f"Dashboard — User {st.session_state.user_id}")

if st.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.automation_running = False
    st.session_state.automation_state.running = False
    st.rerun()

# ---------------- MESSAGE FILE ----------------
msg_file = st.file_uploader("Upload .txt messages", type=["txt"])
if msg_file:
    st.session_state.messages = [line.strip() for line in msg_file.read().decode().split("\n") if line.strip()]
    st.success(f"Messages Loaded ({len(st.session_state.messages)} lines)")

# ---------------- CONFIG ----------------
chat_id = st.text_input("Chat ID", value=st.session_state.chat_id)
chat_type = st.selectbox("Chat Type", ["E2EE", "CONVO"], index=0 if st.session_state.chat_type == "E2EE" else 1)
delay = st.number_input("Delay (seconds)", 1, 300, value=st.session_state.delay)
cookies = st.text_area("Cookies (paste from browser)", value=st.session_state.cookies, height=150)

if st.button("Save Config"):
    db.update_user_config(
        st.session_state.user_id,
        chat_id, chat_type, delay,
        cookies, "\n".join(st.session_state.messages),
        running=st.session_state.automation_running
    )
    st.success("Config Saved Successfully!")

# ---------------- AUTOMATION ENGINE (FIXED 100% WORKING FOR E2EE) ----------------
def setup_browser():
    opt = Options()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--disable-blink-features=AutomationControlled")
    opt.add_experimental_option("excludeSwitches", ["enable-automation"])
    opt.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opt)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    return driver

def find_input_box(driver):
    selectors = [
        "div[contenteditable='true'][data-lexical-editor='true']",  # New E2EE (2024-2025)
        "div[contenteditable='true'] p",                            # Fallback
        "div[role='textbox'][contenteditable='true']",
        "textarea[placeholder*='Message']"
    ]
    for sel in selectors:
        try:
            element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if element.is_displayed() and element.is_enabled():
                live_log(f"Input found → {sel}")
                return element
        except:
            continue
    return None

def send_messages(cfg, stt):
    try:
        live_log("Starting Chrome browser...")
        driver = setup_browser()
        driver.get("https://www.facebook.com/messages/t/" + cfg.get("chat_id", ""))
        time.sleep(10)

        # Inject cookies
        for c in (cfg.get("cookies") or "").split(";"):
            if "=" in c:
                n, v = c.strip().split("=", 1)
                try:
                    driver.add_cookie({"name": n, "value": v, "domain": ".facebook.com"})
                except:
                    pass
        driver.refresh()
        time.sleep(12)
        live_log("Chat opened & cookies applied")

        # Find input box
        input_box = find_input_box(driver)
        if not input_box:
            live_log("❌ Input box not found! Check chat ID or E2EE status")
            stt.running = False
            return

        msgs = [m.strip() for m in (cfg.get("messages") or "").split("\n") if m.strip()]
        if not msgs:
            msgs = ["Hey there! 🔥"]

        live_log(f"Automation STARTED | Delay: {cfg.get('delay')}s | Messages: {len(msgs)}")

        while stt.running:
            msg = msgs[stt.message_rotation_index % len(msgs)]
            stt.message_rotation_index += 1

            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", input_box)
                time.sleep(1)
                
                input_box.click()
                input_box.clear()
                input_box.send_keys(msg)
                time.sleep(1.5)
                
                # This is the REAL fix → Shift + Enter nahi, direct Enter with JS
                driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));", input_box)
                driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', bubbles:true}));", input_box)
                
                stt.message_count += 1
                live_log(f"Sent ({stt.message_count}) → {msg}")

            except Exception as e:
                live_log(f"Send failed: {e}")
                time.sleep(5)

            time.sleep(cfg.get("delay", 15))

        live_log("Automation STOPPED by user")
        driver.quit()

    except Exception as e:
        live_log(f"FATAL ERROR: {e}")
        stt.running = False

# ---------------- CONTROLS ----------------
st.subheader("Automation Control")

col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 START AUTOMATION", disabled=st.session_state.automation_running, use_container_width=True):
        cfg = db.get_user_config(st.session_state.user_id)
        st.session_state.automation_running = True
        st.session_state.automation_state.running = True
        
        thread = threading.Thread(target=send_messages, args=(cfg, st.session_state.automation_state), daemon=True)
        thread.start()
        st.success("Automation Started!")
        time.sleep(2)
        st.rerun()

with col2:
    if st.button("🛑 STOP AUTOMATION", disabled=not st.session_state.automation_running, use_container_width=True):
        st.session_state.automation_state.running = False
        st.session_state.automation_running = False
        live_log("🛑 STOP command issued...")
        st.warning("Stopping...")
        time.sleep(2)
        st.rerun()

# ---------------- LIVE LOGS ----------------
st.subheader("📡 Live Logs")
st.write(f"**Messages Sent:** {st.session_state.automation_state.message_count}")

render_live_console()

if st.session_state.automation_running:
    time.sleep(1)
    st.rerun()