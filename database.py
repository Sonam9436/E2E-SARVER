# database.py  →  FULLY IN-MEMORY (WORKS ON STREAMLIT CLOUD + LOCAL + KALI + ANYWHERE)

users = {}      # {username: {"password": hashed_pass, "id": 1}}
configs = {}    # {user_id: {config_dict}}
next_user_id = 1

import hashlib

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def create_user(username, password):
    global next_user_id
    if any(u.lower() == username.lower() for u in users):
        return False, "Username already exists!"
    
    user_id = next_user_id
    next_user_id += 1
    users[username] = {"password": hash_password(password), "id": user_id}
    configs[user_id] = {
        "chat_id": "",
        "chat_type": "E2EE",
        "delay": 15,
        "cookies": "",
        "messages": "",
        "running": False
    }
    print(f"[+] USER CREATED → {username} (ID: {user_id})")
    return True, "User created bro!"

def verify_user(username, password):
    user = next((u for u in users.values() if users.get(list(users.keys())[list(users.values()).index(u)], {}).get("password") == hash_password(password) and list(users.keys())[list(users.values()).index(u)].lower() == username.lower()), None)
    if user:
        return user["id"]
    for usr, data in users.items():
        if usr.lower() == username.lower() and data["password"] == hash_password(password):
            return data["id"]
    return None

def get_user_config(user_id):
    return configs.get(user_id, {
        "chat_id": "",
        "chat_type": "E2EE",
        "delay": 15,
        "cookies": "",
        "messages": "",
        "running": False
    })

def update_user_config(user_id, chat_id, chat_type, delay, cookies, messages, running=False):
    if user_id not in configs:
        configs[user_id] = {}
    configs[user_id].update({
        "chat_id": chat_id,
        "chat_type": chat_type,
        "delay": int(delay),
        "cookies": cookies,
        "messages": messages,
        "running": running
    })

# Default admin user (optional - remove if you don't want)
# create_user("waleedxd", "waleed123")

print("WALEED XD IN-MEMORY DATABASE LOADED — STREAMLIT CLOUD READY 🔥💀")
