import os
import json
import random
import uuid
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

TOKEN = '8864331106:AAHE8PDCmCl69JAzI3Gjm-ynFh2N7iOZUdQ'
ADMIN_ID = 8187614600
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

DB_FILE = './db.json'

db = {
    'users': [],
    'companies': [],
    'packages': [],
    'orders': [],
    'coupons': [],
    'suggestions': [],
    'twist_settings': {'is_paid': False, 'subscriptions': [], 'monthly_limit': 2000},
    'twist_subscriptions': [],
    'twist_accounts': {},
    'settings': {
        'forced_channel': '@elqanawistore',
        'extra_channels': [],
        'welcome_message': '🎉 أهلاً بك في QENAWWY STORE\n\n🏪 متجرك الموثوق لشحن الباقات\n📱 فودافون | اتصالات | اورنج | وي\n\nاختر من القائمة أدناه:',
        'ai_bot_enabled': True,
        'maintenance_mode': False,
        'maintenance_message': '🛠️ البوت في حالة صيانة حالياً، يرجى المحاولة لاحقاً.',
        'cash_number': '01151931160',
        'loyalty_to_balance_rate': 5,
        'daily_bonus_enabled': True,
        'daily_bonus_min': 1,
        'daily_bonus_max': 5,
        'referral_reward_points': 10,
        'buttons_control': {}
    }
}

user_states = {}
user_sessions = {}

def load_db():
    global db
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
            if 'settings' not in db: db['settings'] = {}
            if 'twist_settings' not in db: db['twist_settings'] = {'is_paid': False, 'subscriptions': [], 'monthly_limit': 2000}
            if db['twist_settings'].get('monthly_limit') is None: db['twist_settings']['monthly_limit'] = 2000
            if not db['settings'].get('forced_channel'): db['settings']['forced_channel'] = '@elqanawistore'
            if not db['settings'].get('cash_number'): db['settings']['cash_number'] = '01151931160'
            if db['settings'].get('loyalty_to_balance_rate') is None: db['settings']['loyalty_to_balance_rate'] = 5
            if db['settings'].get('daily_bonus_enabled') is None: db['settings']['daily_bonus_enabled'] = True
            if db['settings'].get('daily_bonus_min') is None: db['settings']['daily_bonus_min'] = 1
            if db['settings'].get('daily_bonus_max') is None: db['settings']['daily_bonus_max'] = 5
            if db['settings'].get('referral_reward_points') is None: db['settings']['referral_reward_points'] = 10
            if 'coupons' not in db: db['coupons'] = []
            if 'suggestions' not in db: db['suggestions'] = []
            if 'twist_subscriptions' not in db: db['twist_subscriptions'] = []
            if 'twist_accounts' not in db: db['twist_accounts'] = {}
            if db['settings'].get('ai_bot_enabled') is None: db['settings']['ai_bot_enabled'] = True
            if not db['settings'].get('welcome_message'): db['settings']['welcome_message'] = '🎉 أهلاً بك في QENAWWY STORE'
            if db['settings'].get('maintenance_mode') is None: db['settings']['maintenance_mode'] = False
            if not db['settings'].get('maintenance_message'): db['settings']['maintenance_message'] = '🛠️ البوت في حالة صيانة حالياً، يرجى المحاولة لاحقاً.'
            if 'companies' not in db: db['companies'] = []
            if 'packages' not in db: db['packages'] = []
            if 'orders' not in db: db['orders'] = []
        else:
            save_db()
    except Exception:
        save_db()

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

load_db()

def is_admin(user_id):
    return user_id == ADMIN_ID

def add_user(user, referrer_id=None):
    user_id = user.id
    user_obj = next((u for u in db['users'] if u['user_id'] == user_id), None)
    if not user_obj:
        new_user = {
            'user_id': user_id,
            'username': user.username or 'none',
            'first_name': user.first_name or 'none',
            'balance': 0,
            'loyalty_points': 0,
            'last_daily_bonus': None,
            'referred_by': referrer_id if referrer_id and referrer_id != user_id else None,
            'is_banned': False,
            'joined_date': datetime.now(timezone.utc).isoformat()
        }
        db['users'].append(new_user)
        if referrer_id and referrer_id != user_id:
            referrer = next((u for u in db['users'] if u['user_id'] == referrer_id), None)
            if referrer:
                reward = db['settings'].get('referral_reward_points', 10)
                referrer['loyalty_points'] = referrer.get('loyalty_points', 0) + reward
        save_db()
    elif user_obj.get('is_banned', False):
        return False
    return True

def has_active_twist_sub(user_id):
    if is_admin(user_id): return True
    now = datetime.now(timezone.utc)
    active_sub = next((s for s in db['twist_subscriptions'] if s['user_id'] == user_id and datetime.fromisoformat(s['expiry_date']) > now and s['operations_left'] > 0), None)
    return bool(active_sub)

async def check_subscription(bot, user_id):
    if is_admin(user_id): return True
    channels = [db['settings'].get('forced_channel')] + (db['settings'].get('extra_channels') or [])
    for ch in channels:
        if not ch or not ch.strip() or 'إضافة قناة' in ch or len(ch) < 3: continue
        clean_channel = ch.strip()
        if 't.me/' in clean_channel:
            clean_channel = '@' + clean_channel.split('t.me/')[1].replace('/', '')
        elif not clean_channel.startswith('@') and not clean_channel.startswith('-100'):
            clean_channel = '@' + clean_channel
        try:
            chat_member = await bot.get_chat_member(clean_channel, user_id)
            if chat_member.status not in ['creator', 'administrator', 'member']:
                return False
        except Exception:
            return False
    return True

async def send_force_sub_message(update: Update):
    channels = [c for c in [db['settings'].get('forced_channel')] + (db['settings'].get('extra_channels') or []) if c and c.strip() and 'إضافة قناة' not in c and len(c) >= 3]
    inline_keyboard = []
    for idx, ch in enumerate(channels):
        clean_channel = ch.strip()
        channel_url = clean_channel if 't.me/' in clean_channel else 'https://t.me/' + clean_channel.replace('@', '')
        inline_keyboard.append([InlineKeyboardButton(f"📢 انضم للقناة ({idx + 1})", url=channel_url)])
    inline_keyboard.append([InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data='check_sub')])
    await update.message.reply_text(
        '⚠️ عذراً، يجب عليك الاشتراك في جميع قنوات المتجر الإجبارية لتتمكن من استخدام البوت.\n\nبعد الانضمام للجميع، اضغط على زر "تحقق من الاشتراك" بالأسفل 👇',
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )

async def ask_ai(user_text):
    if not db['settings'].get('ai_bot_enabled', True): return None
    if not GEMINI_API_KEY:
        return "أهلاً بيك يا غالي! أنا مساعد المتجر الذكي. تقدر تختار الشركات أو الباقات المتاحة من القائمة تحت، ولو محتاج أي مساعدة أنا معاك! 🤖🔥"
    prompt = 'أنت مساعد ذكي لمتجر شحن باقات مصري اسمه QENAWWY STORE. تكلم باللهجة المصرية الودودة والواضحة. ساعد الزبون في معرفة الباقات أو الشركات المتاحة فقط. ممنوع منعاً باتاً ذكر أي معلومات تقنية أو أكواد أو سيرفرات أو كلمات سر أو أدوات حماية تخص البوت. سؤال الزبون هو: ' + user_text
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
    except Exception:
        pass
    return "منور المتجر يا غالي! اختر من القائمة أسفل لاختيار باقتك المفضلة 📱🔥"

class TwistMusicAPI:
    def __init__(self, user_id=None):
        self.base_url = "https://api.twistmena.com/music"
        self.device_id = "android_" + uuid.uuid4().hex[:16]
        self.session_id = str(uuid.uuid4())
        self.token = None
        self.access_token = None
        self.tg_token = None
        self.refresh_token = None
        self.balance = 0
        self.phone = None
        self.monthly_used = 0
        self.user_id = user_id

    def get_headers(self, extra=None):
        headers = {
            "user-agent": "Twist-Mobile/11.2.10 (Android; 14; Infinix X6885; music; ar-EG)",
            "app_version": "11.2.10",
            "channel": "mobileapp",
            "platform": "android",
            "accept": "application/json",
            "accept-language": "ar-EG",
            "content-type": "application/json",
            "device_id": self.device_id,
            "sessionid": self.session_id,
            "host": "api.twistmena.com",
            "connection": "keep-alive"
        }
        if self.token: headers["Authorization"] = "Bearer " + self.token
        if self.access_token: headers["access-token"] = self.access_token
        if self.tg_token: headers["tg-token"] = self.tg_token
        if self.refresh_token: headers["tg-refresh-token"] = self.refresh_token
        if extra: headers.update(extra)
        return headers

    def format_phone(self, phone):
        phone = phone.strip().replace(" ", "").replace("+", "")
        if phone.startswith("0"): return "20" + phone[1:]
        if phone.startswith("20"): return phone
        return "20" + phone

    async def send_otp(self, phone):
        formatted_phone = self.format_phone(phone)
        url = self.base_url + "/Dlogin/sendCode"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"dial": formatted_phone}, headers=self.get_headers(), timeout=30) as resp:
                    if resp.status == 200:
                        self.phone = formatted_phone
                        return [True, "✅ تم إرسال كود التحقق بنجاح!"]
                    return [False, "❌ فشل الإرسال"]
        except Exception as e:
            return [False, f"❌ خطأ من السيرفر: {e}"]

    async def verify_otp(self, code):
        if not self.phone: return [False, "❌ لم يتم إرسال كود بعد!"]
        url = self.base_url + "/Dlogin/verify"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"dial": self.phone, "verifyCode": code, "socialServiceName": "", "socialServiceToken": ""}, headers=self.get_headers(), timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.token = data.get("token")
                        self.access_token = data.get("accessToken")
                        self.tg_token = data.get("tgToken")
                        self.refresh_token = data.get("refreshToken")
                        await self.get_balance()
                        if self.user_id:
                            if str(self.user_id) not in db['twist_accounts']: db['twist_accounts'][str(self.user_id)] = []
                            db['twist_accounts'][str(self.user_id)] = [acc for acc in db['twist_accounts'][str(self.user_id)] if acc['phone'] != self.phone]
                            db['twist_accounts'][str(self.user_id)].append({
                                "phone": self.phone, "token": self.token, "access_token": self.access_token,
                                "tg_token": self.tg_token, "refresh_token": self.refresh_token,
                                "balance": self.balance, "monthly_used": self.monthly_used
                            })
                            save_db()
                        return [True, "✅ تم تسجيل الدخول بنجاح!"]
                    return [False, "❌ كود غير صحيح!"]
        except Exception as e:
            return [False, f"❌ خطأ التحقق: {e}"]

    async def get_balance(self):
        if not self.token: return 0
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + "/user/loyalty/balance/details", headers=self.get_headers(), timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.balance = data.get("balance", 0)
                        return self.balance
        except Exception:
            pass
        return 0

    async def complete_tasks(self):
        if not self.token: return [False, "❌ يجب تسجيل الدخول أولاً!"]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url + "/user/loyalty/achievements/v2", headers=self.get_headers(), timeout=30) as resp:
                    if resp.status != 200: return [False, "❌ فشل جلب المهام"]
                    data = await resp.json()
                    completed, points = 0, 0
                    for category in (data.get("badges") or []):
                        for task in (category.get("badges") or []):
                            if not task.get("rewarded"):
                                try:
                                    async with session.post(self.base_url + "/loyalty/action/" + str(task["id"]), json={}, headers=self.get_headers(), timeout=30):
                                        pass
                                except Exception:
                                    pass
                                completed += 1
                                points += (task.get("reward") or {}).get("points", 0)
                    await self.get_balance()
                    return [True, f"✅ تم إنجاز {completed} مهمة\n💰 ربحت {points} كوينز\n📊 رصيدك: {self.balance} كوينز"]
        except Exception:
            return [False, "❌ خطأ أثناء إنجاز المهام"]

    async def redeem_units(self, package_id):
        if not self.token: return [False, "❌ يجب تسجيل الدخول أولاً!"]
        packages = {
            "1": "EAND_50_UNITS_ID_9", "2": "EAND_100_UNITS_ID_10", "3": "EAND_150_UNITS_ID_11",
            "4": "EAND_300_UNITS_ID_12", "5": "EAND_500_UNITS_ID_13", "6": "EAND_750_UNITS_ID_14", "7": "EAND_1000_UNITS_ID_15"
        }
        costs = {"1": 100, "2": 200, "3": 300, "4": 600, "5": 1000, "6": 1500, "7": 2000}
        units = {"1": 50, "2": 100, "3": 150, "4": 300, "5": 500, "6": 750, "7": 1000}
        if package_id not in packages: return [False, "❌ باقة غير معروفة"]
        if self.balance < costs[package_id]: return [False, f"⚠️ رصيدك غير كافٍ! تحتاج {costs[package_id]} كوينز."]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url + "/loyalty/redeem/" + packages[package_id], json={}, headers=self.get_headers(), timeout=30) as resp:
                    if resp.status == 200:
                        self.monthly_used += units[package_id]
                        await self.get_balance()
                        return [True, f"✅ تم استبدال {units[package_id]} وحدة بنجاح!"]
                    return [False, "❌ فشل الاستبدال"]
        except Exception as e:
            return [False, f"❌ خطأ الاستبدال: {e}"]

async def show_twist_packages(chat_id, api, context):
    monthly_limit = db['twist_settings'].get('monthly_limit', 2000)
    remaining = monthly_limit - api.monthly_used
    text = f"📊 <b>رصيدك الحالي:</b> {api.balance} كوينز\n📉 <b>الحد الشهري المتبقي:</b> {remaining} وحدة\n\n🎁 <b>اختر الباقة التي تريد استبدالها:</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 50 وحدة (100 كوينز)", callback_data="twist_redeem_1")],
        [InlineKeyboardButton("🎁 100 وحدة (200 كوينز)", callback_data="twist_redeem_2")],
        [InlineKeyboardButton("🎁 150 وحدة (300 كوينز)", callback_data="twist_redeem_3")],
        [InlineKeyboardButton("🎁 300 وحدة (600 كوينز)", callback_data="twist_redeem_4")],
        [InlineKeyboardButton("🎁 500 وحدة (1000 كوينز)", callback_data="twist_redeem_5")],
        [InlineKeyboardButton("🎁 750 وحدة (1500 كوينز)", callback_data="twist_redeem_6")],
        [InlineKeyboardButton("🎁 1000 وحدة (2000 كوينز)", callback_data="twist_redeem_7")]
    ])
    await context.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton('🔥 🎵 Twist Music 🎵 🔥')],
    [KeyboardButton('🏢 الشركات المتاحة'), KeyboardButton('📦 الباقات المتاحة')],
    [KeyboardButton('🎁 كسب نقاط الولاء مجاناً'), KeyboardButton('📋 طلباتي')],
    [KeyboardButton('💡 اقتراحات وشكاوي'), KeyboardButton('👤 حسابي')],
    [KeyboardButton('❓ الأسئلة الشائعة'), KeyboardButton('📞 تواصل معنا')],
    [KeyboardButton('❤️ صلي على سيدنا محمد'), KeyboardButton('💰 شحن المحفظة')]
], resize_keyboard=True)

admin_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton('🏢 إدارة الشركات'), KeyboardButton('📦 إدارة الباقات')],
    [KeyboardButton('🤖 إدارة خدمة تويست'), KeyboardButton('🎟 إدارة الكوبونات')],
    [KeyboardButton('🛠 إدارة وضع الصيانة'), KeyboardButton('⚙️ إعدادات المتجر')],
    [KeyboardButton('💡 عرض الاقتراحات'), KeyboardButton('🤖 حالة الذكاء الاصطناعي')],
    [KeyboardButton('📋 الطلبات'), KeyboardButton('📊 إحصائيات')],
    [KeyboardButton('👥 المستخدمين'), KeyboardButton('📢 بث عام')],
    [KeyboardButton('🔙 رجوع')]
], resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    
    referrer_id = None
    if context.args:
        ref_text = context.args[0].strip()
        if ref_text.startswith('ref_'):
            try:
                referrer_id = int(ref_text.replace('ref_', ''))
            except ValueError:
                pass

    if db['settings'].get('maintenance_mode') and not is_admin(user_id):
        await update.message.reply_text(db['settings'].get('maintenance_message'))
        return
    if not await check_subscription(context.bot, user_id):
        await send_force_sub_message(update)
        return
    allowed = add_user(user, referrer_id)
    if not allowed:
        await update.message.reply_text('⛔ عذراً، تم حظرك من استخدام البوت.')
        return
    
    await update.message.reply_text(db['settings'].get('welcome_message'), reply_markup=main_keyboard)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text('⛔ غير مصرح لك')
        return
    await update.message.reply_text('🔐 لوحة تحكم المتجر الشاملة', reply_markup=admin_keyboard)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    text = update.message.text

    if db['settings'].get('maintenance_mode') and not is_admin(user_id):
        await update.message.reply_text(db['settings'].get('maintenance_message'))
        return

    if user_id in user_states:
        st = user_states[user_id]['step']
        
        if st == 'set_twist_monthly_limit':
            try:
                limit_val = int(text.strip())
                if limit_val <= 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقماً صحيحاً وموجباً للحد الشهري.')
                return
            db['twist_settings']['monthly_limit'] = limit_val
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f'✅ تم تحديث الحد الشهري لتويست بنجاح إلى: <b>{limit_val} وحدة</b>', parse_mode='HTML')
            return

        if st == 'set_new_cash_number':
            db['settings']['cash_number'] = text.strip() if text else '01151931160'
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f'✅ تم تحديث رقم الكاش بنجاح إلى: <code>{db["settings"]["cash_number"]}</code>', parse_mode='HTML')
            return

        if st == 'set_loyalty_rate':
            try:
                rate = int(text.strip())
                if rate <= 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقماً صحيحاً وموجباً.')
                return
            db['settings']['loyalty_to_balance_rate'] = rate
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f'✅ تم تحديث معدل نقاط الولاء: كل {rate} نقاط تساوي 1 جنيه.')
            return

        if st == 'set_daily_bonus_min':
            try:
                val = int(text.strip())
                if val <= 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقماً صحيحاً.')
                return
            user_states[user_id]['dailyMin'] = val
            user_states[user_id]['step'] = 'set_daily_bonus_max'
            await update.message.reply_text('📈 أرسل الحد الأقصى لنقاط الهدية اليومية (مثال: 5):')
            return

        if st == 'set_daily_bonus_max':
            try:
                val = int(text.strip())
                if val <= 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقماً صحيحاً.')
                return
            db['settings']['daily_bonus_min'] = user_states[user_id]['dailyMin']
            db['settings']['daily_bonus_max'] = val
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f"✅ تم تحديث نطاق الهدية اليومية بنجاح (من {db['settings']['daily_bonus_min']} إلى {db['settings']['daily_bonus_max']} نقطة).")
            return

        if st == 'set_referral_reward':
            try:
                val = int(text.strip())
                if val < 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقماً صحيحاً.')
                return
            db['settings']['referral_reward_points'] = val
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f'✅ تم تحديث نقاط مكافأة دعوة الأصدقاء إلى {val} نقطة.')
            return

        if st == 'wallet_deposit_amount':
            try:
                amount = float(text.strip())
                if amount <= 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ أدخل مبلغاً صحيحاً.')
                return
            user_states[user_id]['depositAmount'] = amount
            user_states[user_id]['step'] = 'wallet_deposit_wallet_phone'
            current_cash_num = db['settings'].get('cash_number', '01151931160')
            await update.message.reply_text(f'💳 تفاصيل شحن المحفظة:\n\nقم بالتحويل بمبلغ <b>{amount} جنيه</b> إلى رقم الكاش التالي:\n<code>{current_cash_num}</code>\n\n📱 أرسل الآن رقم المحفظة التي قمت بالتحويل منها:', parse_mode='HTML')
            return

        if st == 'wallet_deposit_wallet_phone':
            user_states[user_id]['walletPhone'] = text.strip() if text else ''
            user_states[user_id]['step'] = 'wallet_deposit_receipt'
            await update.message.reply_text('📸 أرسل الآن صورة الإيصال (سكرين شوت التحويل) لتأكيد عملية الشحن للإدارة:', parse_mode='HTML')
            return

        if st == 'wallet_deposit_receipt':
            receipt_proof = update.message.photo[-1].file_id if update.message.photo else (text.strip() if text else 'بدون إيصال')
            state = user_states[user_id]
            user_mention = f"@{user.username}" if user.username else (user.first_name or str(user_id))
            
            new_order = {
                'id': max([o['id'] for o in db['orders']], default=0) + 1,
                'user_id': user_id,
                'user_mention': user_mention,
                'package_id': 'شحن رصيد المحفظة الداخلية',
                'phone': state['walletPhone'],
                'wallet_phone': state['walletPhone'],
                'final_price': state['depositAmount'],
                'receipt': receipt_proof,
                'status': 'pending',
                'is_wallet_deposit': True,
                'created_date': datetime.now(timezone.utc).isoformat()
            }
            db['orders'].append(new_order)
            save_db()
            del user_states[user_id]

            await update.message.reply_text('✅ تم إرسال طلب شحن المحفظة والإيصال بنجاح للإدارة، في انتظار المراجعة والتأكيد!')
            admin_text = f"🔔 **طلب شحن محفظة جديد!**\n\n👤 العميل: {user_mention} (<code>{user_id}</code>)\n💰 المبلغ المطلوب: {state['depositAmount']} جنيه\n💳 رقم المحفظة المحول منها: {state['walletPhone']}"
            admin_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ قبول وشحن المحفظة', callback_data=f"approve_order_{new_order['id']}"), InlineKeyboardButton('❌ رفض', callback_data=f"reject_order_{new_order['id']}")]
            ])
            if update.message.photo:
                await context.bot.send_photo(ADMIN_ID, receipt_proof, caption=admin_text, reply_markup=admin_markup, parse_mode='HTML')
            else:
                await context.bot.send_message(ADMIN_ID, admin_text + f"\n📸 الإيصال: {receipt_proof}", reply_markup=admin_markup, parse_mode='HTML')
            return

        if st == 'add_twist_sub_days':
            try:
                days = int(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقم صحيح للأيام.')
                return
            user_states[user_id]['days'] = days
            user_states[user_id]['step'] = 'add_twist_sub_ops'
            await update.message.reply_text('⚙️ أرسل عدد العمليات المتاحة (مثال: 10):')
            return

        if st == 'add_twist_sub_ops':
            try:
                ops = int(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ أدخل رقم صحيح للعمليات.')
                return
            user_states[user_id]['ops'] = ops
            user_states[user_id]['step'] = 'add_twist_sub_price'
            await update.message.reply_text('💰 أرسل سعر الباقة بالجنيه (مثال: 30):')
            return

        if st == 'add_twist_sub_price':
            try:
                price = float(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ أدخل سعر صحيح.')
                return
            state = user_states[user_id]
            db['twist_settings']['subscriptions'].append({
                'days': state['days'], 'operations': state['ops'], 'price': price
            })
            save_db()
            del user_states[user_id]
            await update.message.reply_text('✅ تمت إضافة باقة تويست المدفوعة بنجاح!', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('🔄 تبديل نظام تويست (مجاني/مدفوع)')],
                [KeyboardButton('➕ إضافة باقة تويست'), KeyboardButton('📋 عرض باقات تويست')],
                [KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return

        if st == 'company_name':
            user_states[user_id]['name'] = text.strip() if text else ''
            user_states[user_id]['step'] = 'company_logo'
            await update.message.reply_text('🖼 أرسل لوجو الشركة (رابط صورة، إيموجي، أو اكتب "تخطي"):')
            return

        if st == 'company_logo':
            logo = '📱' if text and text.strip() == 'تخطي' else (text.strip() if text else '📱')
            db['companies'].append({
                'id': max([c['id'] for c in db['companies']], default=0) + 1,
                'name': user_states[user_id]['name'],
                'logo': logo,
                'is_active': True,
                'created_date': datetime.now(timezone.utc).isoformat()
            })
            save_db()
            del user_states[user_id]
            await update.message.reply_text('✅ تمت إضافة الشركة بنجاح!', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة شركة'), KeyboardButton('❌ حذف شركة')],
                [KeyboardButton('📋 قائمة الشركات'), KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return

        if st == 'pkg_name':
            user_states[user_id]['pkgName'] = text.strip() if text else ''
            user_states[user_id]['step'] = 'pkg_price'
            await update.message.reply_text('💰 أرسل سعر الباقة بالجنيه:')
            return

        if st == 'pkg_price':
            try:
                price = float(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ يرجى كتابة رقم صحيح لسعر الباقة.')
                return
            user_states[user_id]['pkgPrice'] = price
            user_states[user_id]['step'] = 'pkg_reward_points'
            await update.message.reply_text('🎁 أرسل عدد نقاط الولاء التي يكسبها العميل عند طلب هذه الباقة (مثال: 5):')
            return

        if st == 'pkg_reward_points':
            try:
                reward = int(text.strip())
                if reward < 0: raise ValueError()
            except ValueError:
                await update.message.reply_text('⚠️ يرجى كتابة رقم صحيح للنقاط.')
                return
            state = user_states[user_id]
            db['packages'].append({
                'id': max([p['id'] for p in db['packages']], default=0) + 1,
                'company_id': state['companyId'],
                'name': state['pkgName'],
                'price': state['pkgPrice'],
                'reward_points': reward,
                'is_active': True,
                'created_date': datetime.now(timezone.utc).isoformat()
            })
            save_db()
            del user_states[user_id]
            await update.message.reply_text(f'✅ تمت إضافة باقة "{state["pkgName"]}" بسعر {state["pkgPrice"]} جنيه ومكافأة {reward} نقطة بنجاح!', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة باقة'), KeyboardButton('❌ حذف باقة')],
                [KeyboardButton('📋 قائمة الباقات'), KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return

        if st == 'add_coupon_code':
            user_states[user_id]['code'] = text.strip().upper() if text else ''
            user_states[user_id]['step'] = 'add_coupon_discount'
            await update.message.reply_text('📉 أرسل قيمة الخصم بالجنيه (مثال: 10):')
            return

        if st == 'add_coupon_discount':
            try:
                discount = float(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ يرجى كتابة رقم صحيح لقيمة الخصم.')
                return
            user_states[user_id]['discount'] = discount
            user_states[user_id]['step'] = 'add_coupon_max_uses'
            await update.message.reply_text('⚙️ أرسل أقصى عدد عمليات/استخدامات مسموحة لهذا الكوبون (مثال: 50):')
            return

        if st == 'add_coupon_max_uses':
            try:
                max_uses = int(text.strip())
            except ValueError:
                await update.message.reply_text('⚠️ يرجى كتابة رقم صحيح لعدد العمليات.')
                return
            state = user_states[user_id]
            db['coupons'].append({
                'code': state['code'], 'discount': state['discount'], 'max_uses': max_uses, 'uses_count': 0
            })
            save_db()
            del user_states[user_id]
            await update.message.reply_text('✅ تم إضافة الكوبون بنجاح!', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة كوبون خصم'), KeyboardButton('📋 قائمة الكوبونات')],
                [KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return

        if st == 'set_maintenance_msg':
            db['settings']['maintenance_message'] = text.strip() if text else ''
            save_db()
            del user_states[user_id]
            await update.message.reply_text('✅ تم تحديث رسالة الصيانة بنجاح.')
            return

        if st == 'send_suggestion':
            user_mention = f"@{user.username}" if user.username else (user.first_name or str(user_id))
            db['suggestions'].append({
                'id': len(db['suggestions']) + 1, 'user_id': user_id, 'user_mention': user_mention,
                'content': text, 'status': 'pending', 'created_date': datetime.now(timezone.utc).isoformat()
            })
            save_db()
            del user_states[user_id]
            await update.message.reply_text('✅ شكراً لك! تم إرسال اقتراحك للإدارة.')
            await context.bot.send_message(ADMIN_ID, f"💡 **اقتراح جديد من {user_mention} (ID: {user_id}):**\n\n{text}")
            return

        if st == 'broadcast':
            for u in db['users']:
                try:
                    await context.bot.send_message(u['user_id'], f"📢 {text}")
                except Exception:
                    pass
            del user_states[user_id]
            await update.message.reply_text(f"✅ تم بث الرسالة إلى {len(db['users'])} مستخدم.")
            return

        if st == 'twist_phone':
            api = user_sessions.get(chat_id)
            res = await api.send_otp(text)
            if res[0]:
                user_states[user_id]['step'] = 'twist_otp'
                await update.message.reply_text('🔑 أدخل كود التحقق المرسل لرقمك:')
            else:
                await update.message.reply_text(res[1])
            return

        if st == 'twist_otp':
            api = user_sessions.get(chat_id)
            res = await api.verify_otp(text)
            if res[0]:
                phone_num = api.phone
                del user_states[user_id]
                await update.message.reply_text(res[1])
                if str(user_id) not in db['twist_accounts']: db['twist_accounts'][str(user_id)] = []
                db['twist_accounts'][str(user_id)] = [acc for acc in db['twist_accounts'][str(user_id)] if acc['phone'] != phone_num]
                db['twist_accounts'][str(user_id)].append({
                    'phone': phone_num, 'token': api.token, 'access_token': api.access_token,
                    'balance': api.balance or 0, 'monthly_used': api.monthly_used or 0
                })
                save_db()
                task_res = await api.complete_tasks()
                await update.message.reply_text(task_res[1])
                await show_twist_packages(chat_id, api, context)
            else:
                await update.message.reply_text(res[1])
            return

        if st == 'order_phone':
            user_states[user_id]['phone'] = text.strip() if text else ''
            user_states[user_id]['step'] = 'order_coupon'
            await update.message.reply_text('🎟 هل لديك كوبون خصم؟ أرسل الكود أو اكتب (تخطي):')
            return

        if st == 'order_coupon':
            code = text.strip().upper() if text else 'تخطي'
            user_states[user_id]['discount'] = 0
            if code != 'تخطي':
                found = next((c for c in db['coupons'] if c['code'] == code), None)
                if found:
                    if found.get('max_uses') is not None and found.get('uses_count', 0) >= found['max_uses']:
                        await update.message.reply_text('⚠️ عذراً، هذا الكوبون استنفد الحد الأقصى! تم المتابعة بدون خصم.')
                    else:
                        user_states[user_id]['discount'] = found['discount']
                        found['uses_count'] = found.get('uses_count', 0) + 1
                        save_db()
                        await update.message.reply_text(f"✅ تم تطبيق الكوبون بنجاح! خصم {found['discount']} جنيه.")
                else:
                    await update.message.reply_text('⚠️ الكوبون غير صحيح، تم المتابعة بدون خصم.')
            
            state = user_states[user_id]
            pkg = next((p for p in db['packages'] if p['id'] == state['packageId']), None)
            original_price = pkg['price'] if pkg else 0
            final_price = max(0.0, original_price - state.get('discount', 0))
            user_states[user_id]['finalPrice'] = final_price
            
            user_obj = next((u for u in db['users'] if u['user_id'] == user_id), {'balance': 0})
            user_balance = user_obj.get('balance', 0)

            if user_balance >= final_price:
                user_obj['balance'] -= final_price
                save_db()
                user_mention = f"@{user.username}" if user.username else (user.first_name or str(user_id))
                reward_points = pkg.get('reward_points', 5) if pkg else 5
                new_order = {
                    'id': max([o['id'] for o in db['orders']], default=0) + 1,
                    'user_id': user_id, 'user_mention': user_mention,
                    'package_id': pkg['name'] if pkg else 'خدمة',
                    'phone': state['phone'], 'wallet_phone': 'محفظة البوت الداخلية',
                    'final_price': final_price, 'reward_points': reward_points,
                    'receipt': 'مدفوع من المحفظة الداخلية', 'status': 'pending',
                    'paid_from_balance': True, 'created_date': datetime.now(timezone.utc).isoformat()
                }
                db['orders'].append(new_order)
                save_db()
                del user_states[user_id]
                await update.message.reply_text(f"✅ تم خصم مبلغ {final_price} جنيه من رصيدك الداخلي وإرسال طلبك للإدارة بنجاح!\n💰 رصيدك المتبقي: {user_obj['balance']} جنيه.")
                await context.bot.send_message(ADMIN_ID, f"🔔 **طلب جديد مدفوع من رصيد المحفظة #{new_order['id']}**\n\n👤 العميل: {user_mention} (<code>{user_id}</code>)\n📦 الباقة: {pkg['name'] if pkg else ''}\n📱 الرقم: {state['phone']}\n💰 السعر: {final_price} جنيه", parse_mode='HTML')
                return

            current_cash_num = db['settings'].get('cash_number', '01151931160')
            user_states[user_id]['step'] = 'order_wallet_phone'
            await update.message.reply_text(f"💳 رصيدك الداخلي ({user_balance} جنيه) لا يكفي.\n\nقم بالتحويل بمبلغ <b>{final_price} جنيه</b> إلى رقم فودافون كاش / اتصالات كاش التالي:\n<code>{current_cash_num}</code>\n\n📱 أرسل الآن رقم المحفظة التي قمت بالتحويل منها:", parse_mode='HTML')
            return

        if st == 'order_wallet_phone':
            user_states[user_id]['walletPhone'] = text.strip() if text else ''
            user_states[user_id]['step'] = 'order_receipt'
            await update.message.reply_text('📸 أرسل الآن صورة الإيصال (سكرين شوت التحويل) لتأكيد طلبك للإدارة:', parse_mode='HTML')
            return

        if st == 'order_receipt':
            receipt_proof = update.message.photo[-1].file_id if update.message.photo else (text.strip() if text else 'بدون إيصال')
            state = user_states[user_id]
            pkg = next((p for p in db['packages'] if p['id'] == state['packageId']), None)
            final_price = state.get('finalPrice', pkg['price'] if pkg else 0)
            user_mention = f"@{user.username}" if user.username else (user.first_name or str(user_id))
            reward_points = pkg.get('reward_points', 5) if pkg else 5
            
            new_order = {
                'id': max([o['id'] for o in db['orders']], default=0) + 1,
                'user_id': user_id, 'user_mention': user_mention,
                'package_id': pkg['name'] if pkg else 'خدمة',
                'phone': state['phone'], 'wallet_phone': state['walletPhone'],
                'final_price': final_price, 'reward_points': reward_points,
                'receipt': receipt_proof, 'status': 'pending',
                'created_date': datetime.now(timezone.utc).isoformat()
            }
            db['orders'].append(new_order)
            save_db()
            del user_states[user_id]
            
            await update.message.reply_text('✅ تم إرسال طلبك ورقم التحويل والإيصال بنجاح للإدارة، في انتظار المراجعة والتأكيد!')
            admin_text = f"🔔 **طلب شحن جديد متكامل!**\n\n👤 العميل: {user_mention} (<code>{user_id}</code>)\n📦 الباقة: {new_order['package_id']}\n📱 رقم الشحن: {state['phone']}\n💳 رقم محفظة التحويل: {state['walletPhone']}\n💰 السعر النهائي: {final_price} جنيه"
            admin_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ قبول وتأكيد', callback_data=f"approve_order_{new_order['id']}"), InlineKeyboardButton('❌ رفض', callback_data=f"reject_order_{new_order['id']}")]
            ])
            if update.message.photo:
                await context.bot.send_photo(ADMIN_ID, receipt_proof, caption=admin_text, reply_markup=admin_markup, parse_mode='HTML')
            else:
                await context.bot.send_message(ADMIN_ID, admin_text + f"\n📸 الإيصال: {receipt_proof}", reply_markup=admin_markup, parse_mode='HTML')
            return

    if text and not text.startswith('/'):
        if text in ['❤️ صلي على سيدنا محمد']:
            await update.message.reply_text('عليه الصلاة والسلام ❤️❤️❤️\n✨ جزاك الله خيراً وجعلها في ميزان حسناتك!')
            return
        if text in ['🔥 🎵 Twist Music 🎵 🔥']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            if db['twist_settings'].get('is_paid') and not has_active_twist_sub(user_id):
                subs = db['twist_settings'].get('subscriptions', [])
                if not subs:
                    await update.message.reply_text('⚠️ عذراً، خدمة تويست مدفوعة حالياً ولم يتم إعداد باقات اشتراك لها من الإدارة بعد.')
                    return
                inline_keyboard = [[InlineKeyboardButton(f"⏳ اشتراك {sub['days']} يوم ({sub['operations']} عملية) - {sub['price']} جنيه", callback_data=f"buy_twist_sub_{idx}")] for idx, sub in enumerate(subs)]
                await update.message.reply_text('💳 <b>خدمة تويست المدفوعة</b>\n\nعذراً ليس لديك اشتراك نشط. اختر باقة الاشتراك المناسبة لك وللعمليات:', parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard))
                return
            saved_accounts = db['twist_accounts'].get(str(user_id), [])
            inline_keyboard = [[InlineKeyboardButton(f"📱 {acc['phone']} (رصيد: {acc.get('balance', 0)} كوينز)", callback_data=f"twist_use_saved_{idx}")] for idx, acc in enumerate(saved_accounts)]
            inline_keyboard.append([InlineKeyboardButton('➕ إدخال رقم جديد', callback_data='twist_add_new')])
            await update.message.reply_text('🔄✨ <b>تجميع نقاط تويست (Twist Music)</b>\nاختر أحد أرقامك المحفوظة أو أضف رقم جديد:', parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard))
            return
        if text in ['🎁 كسب نقاط الولاء مجاناً']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            await update.message.reply_text('🎁 **قائمة كسب نقاط الولاء مجاناً:**\n\nاختر الطريقة المناسبة لك لجعل رصيدك من النقاط يرتفع:', parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🎁 هدية اليوم (كل 24 ساعة)', callback_data='claim_daily_bonus')],
                [InlineKeyboardButton('👥 دعوة الأصدقاء (رابط ريفيرال)', callback_data='get_referral_link')]
            ]))
            return
        if text in ['❓ الأسئلة الشائعة']:
            msg_txt = "❓ **الأسئلة الشائعة والإجابات:**\n\n"
            msg_txt += "1️⃣ **إزاي أشحن باقة من المتجر؟**\n- اختر (الباقات المتاحة)، اضغط على طلب الباقة، اكتب رقمك، وادفع عبر فودافون أو اتصالات كاش.\n\n"
            msg_txt += "2️⃣ **إزاي أستخدم المحفظة الداخلية؟**\n- تقدر تشحن محفظتك الداخلية بضغط (شحن المحفظة) ورفع الإيصال، وبعدين تشتري بيها بضغطة زر فوراً!\n\n"
            msg_txt += "3️⃣ **إزاي أستفيد من نقاط الولاء؟**\n- كل طلب ناجح بيضيف لك نقاط ولاء، وتقدر تحولها لرصيد في حسابك من قسم (حسابي).\n\n"
            msg_txt += "4️⃣ **خدمة تويست بتشتغل إزاي؟**\n- ادخل على (Twist Music) وسجل رقمك واستمتع بتجميع الكوينز واستبدال الوحدات."
            await update.message.reply_text(msg_txt, parse_mode='Markdown')
            return
        if text in ['💰 شحن المحفظة']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            user_states[user_id] = {'step': 'wallet_deposit_amount'}
            await update.message.reply_text('💰 **شحن رصيد المحفظة الداخلية**\n\nأرسل الآن المبلغ بالجنيه الذي تريد شحنه في محفظتك (مثال: 50):', parse_mode='HTML')
            return
        if text in ['🏢 الشركات المتاحة']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            companies = [c for c in db['companies'] if c.get('is_active', True)]
            if not companies:
                await update.message.reply_text('⚠️ لا توجد شركات متاحة حالياً')
                return
            msg_txt = '🏢 الشركات المتاحة:\n\n'
            for i, c in enumerate(companies):
                msg_txt += f"{i + 1}. {c.get('logo', '📱')} {c['name']}\n"
            await update.message.reply_text(msg_txt)
            return
        if text in ['📦 الباقات المتاحة']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            packages = [p for p in db['packages'] if p.get('is_active', True)]
            if not packages:
                await update.message.reply_text('⚠️ لا توجد باقات متاحة حالياً')
                return
            msg_txt = '📦 الباقات المتاحة:\n\n'
            inline_keyboard = []
            for p in packages:
                company = next((c for c in db['companies'] if c['id'] == p['company_id']), None)
                reward_points = p.get('reward_points', 5)
                msg_txt += f"{company.get('logo', '📱') if company else '📱'} {company['name'] if company else ''} - {p['name']}\n"
                msg_txt += f"💰 السعر: {p['price']} جنيه | 🎁 نقاط الهدية: {reward_points} نقطة\n"
                if p.get('description'): msg_txt += f"📝 {p['description']}\n"
                msg_txt += '➖➖➖➖➖➖➖\n'
                inline_keyboard.append([InlineKeyboardButton('🛒 طلب: ' + p['name'], callback_data=f"order_{p['id']}")])
            await update.message.reply_text(msg_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard))
            return
        if text in ['💡 اقتراحات وشكاوي']:
            if not await check_subscription(context.bot, user_id):
                await send_force_sub_message(update)
                return
            user_states[user_id] = {'step': 'send_suggestion'}
            await update.message.reply_text('💡 <b>أرسل الآن اقتراحك أو شكواك وسنقوم بمراجعتها بعناية:</b>', parse_mode='HTML')
            return
        if text in ['👤 حسابي']:
            user = next((u for u in db['users'] if u['user_id'] == user_id), {'balance': 0, 'loyalty_points': 0})
            rate = db['settings'].get('loyalty_to_balance_rate', 5)
            msg_txt = f"👤 **بيانات حسابك الشخصي:**\n\n🆔 الآيدي: <code>{user_id}</code>\n💰 رصيد المحفظة: {user.get('balance', 0)} جنيه\n🎁 نقاط الولاء: {user.get('loyalty_points', 0)} نقطة\n\n💱 معدل الاستبدال الحالي: كل {rate} نقاط = 1 جنيه"
            await update.message.reply_text(msg_txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎁 استبدال نقاط الولاء لرصيد', callback_data='convert_loyalty')]]))
            return
        if text in ['📋 طلباتي']:
            user_orders = [o for o in db['orders'] if o['user_id'] == user_id]
            if not user_orders:
                await update.message.reply_text('📦 ليس لديك أي طلبات سابقة حتى الآن.')
                return
            msg_txt = '📋 **سجل طلباتك الأخيرة:**\n\n'
            for o in user_orders[-5:]:
                st_txt = '⏳ قيد المراجعة' if o['status'] == 'pending' else ('✅ مقبولة' if o['status'] == 'approved' else '❌ مرفوضة')
                msg_txt += f"📦 طلب #{o['id']} | الباقة: {o['package_id']}\n💰 السعر: {o['final_price']} جنيه | الحالة: {st_txt}\n➖➖➖➖➖➖➖\n"
            await update.message.reply_text(msg_txt, parse_mode='Markdown')
            return
        if text in ['📞 تواصل معنا']:
            await update.message.reply_text('📞 للتواصل مع الدعم الفني للمتجر:', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('💬 تواصل مباشر مع المطور', url='https://t.me/elqanawistore')]]))
            return
        if text in ['🏢 إدارة الشركات']:
            if not is_admin(user_id): return
            await update.message.reply_text('🏢 **إدارة الشركات**', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة شركة'), KeyboardButton('❌ حذف شركة')],
                [KeyboardButton('📋 قائمة الشركات'), KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return
        if text in ['➕ إضافة شركة']:
            if not is_admin(user_id): return
            user_states[user_id] = {'step': 'company_name'}
            await update.message.reply_text('📝 أرسل اسم الشركة الجديدة:')
            return
        if text in ['❌ حذف شركة']:
            if not is_admin(user_id): return
            comps = db['companies']
            if not comps:
                await update.message.reply_text('⚠️ لا توجد شركات للحذف.')
                return
            inline = [[InlineKeyboardButton(f"🗑 حذف: {c['name']}", callback_data=f"delete_company_{c['id']}")] for c in comps]
            await update.message.reply_text('🗑 اختر الشركة المراد حذفها:', reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['📋 قائمة الشركات']:
            if not is_admin(user_id): return
            comps = db['companies']
            if not comps:
                await update.message.reply_text('⚠️ لا توجد شركات مسجلة.')
                return
            msg_txt = '📋 **قائمة الشركات الحالية:**\n\n'
            for c in comps:
                msg_txt += f"🆔 ID: {c['id']}\nالاسم: {c['name']}\nاللوجو: {c.get('logo', '📱')}\n➖➖➖➖➖➖➖\n"
            await update.message.reply_text(msg_txt)
            return
        if text in ['📦 إدارة الباقات']:
            if not is_admin(user_id): return
            await update.message.reply_text('📦 **إدارة الباقات**', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة باقة'), KeyboardButton('❌ حذف باقة')],
                [KeyboardButton('🔄 تفعيل/إيقاف باقة'), KeyboardButton('📋 قائمة الباقات')],
                [KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return
        if text in ['➕ إضافة باقة']:
            if not is_admin(user_id): return
            comps = db['companies']
            if not comps:
                await update.message.reply_text('⚠️ يجب إضافة شركة أولاً قبل إضافة الباقات!')
                return
            inline = [[InlineKeyboardButton(c['name'], callback_data=f"select_comp_pkg_{c['id']}")] for c in comps]
            await update.message.reply_text('🏢 اختر الشركة التابعة لها الباقة:', reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['❌ حذف باقة']:
            if not is_admin(user_id): return
            pkgs = db['packages']
            if not pkgs:
                await update.message.reply_text('⚠️ لا توجد باقات للحذف.')
                return
            inline = [[InlineKeyboardButton(f"🗑 حذف: {p['name']}", callback_data=f"delete_pkg_{p['id']}")] for p in pkgs]
            await update.message.reply_text('🗑 اختر الباقة المراد حذفها:', reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['🔄 تفعيل/إيقاف باقة']:
            if not is_admin(user_id): return
            pkgs = db['packages']
            if not pkgs:
                await update.message.reply_text('⚠️ لا توجد باقات مضافة.')
                return
            inline = [[InlineKeyboardButton(f"{'🟢 مفعلة (اضغط للإيقاف)' if p.get('is_active', True) else '🔴 متوقفة (اضغط للتفعيل)'}: {p['name']}", callback_data=f"toggle_pkg_{p['id']}")] for p in pkgs]
            await update.message.reply_text('🔄 اختر الباقة لتغيير حالتها (تفعيل أو إيقاف مؤقت):', reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['📋 قائمة الباقات']:
            if not is_admin(user_id): return
            pkgs = db['packages']
            if not pkgs:
                await update.message.reply_text('⚠️ لا توجد باقات مسجلة.')
                return
            msg_txt = '📋 **قائمة الباقات الحالية:**\n\n'
            for p in pkgs:
                comp = next((c for c in db['companies'] if c['id'] == p['company_id']), None)
                status = '🟢 مفعلة' if p.get('is_active', True) else '🔴 متوقفة'
                reward = p.get('reward_points', 5)
                msg_txt += f"🆔 ID: {p['id']}\nالشركة: {comp['name'] if comp else 'غير معروف'}\nالباقة: {p['name']}\nالسعر: {p['price']} جنيه\nنقاط الهدية: {reward} نقطة\nالحالة: {status}\n➖➖➖➖➖➖➖\n"
            await update.message.reply_text(msg_txt)
            return
        if text in ['🤖 إدارة خدمة تويست']:
            if not is_admin(user_id): return
            status = '🔴 مدفوع' if db['twist_settings'].get('is_paid') else '🟢 مجاني'
            monthly_limit = db['twist_settings'].get('monthly_limit', 2000)
            await update.message.reply_text(f"🤖 **إدارة خدمة تويست**\nالحالة الحالية: {status}\n📉 الحد الشهري الحالي: {monthly_limit} وحدة", reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('🔄 تبديل نظام تويست (مجاني/مدفوع)')],
                [KeyboardButton('✏️ تعديل الحد الشهري لتويست')],
                [KeyboardButton('➕ إضافة باقة تويست'), KeyboardButton('📋 عرض باقات تويست')],
                [KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return
        if text in ['🔄 تبديل نظام تويست (مجاني/مدفوع)']:
            if not is_admin(user_id): return
            db['twist_settings']['is_paid'] = not db['twist_settings'].get('is_paid', False)
            save_db()
            status = '🔴 مدفوع' if db['twist_settings']['is_paid'] else '🟢 مجاني'
            await update.message.reply_text(f"✅ تم تبديل نظام تويست بنجاح!\nالحالة الآن: {status}")
            return
        if text in ['✏️ تعديل الحد الشهري لتويست']:
            if not is_admin(user_id): return
            user_states[user_id] = {'step': 'set_twist_monthly_limit'}
            monthly_limit = db['twist_settings'].get('monthly_limit', 2000)
            await update.message.reply_text(f"📉 الحد الشهري الحالي هو: {monthly_limit} وحدة\n\nأرسل الآن الرقم الجديد الذي تريد اعتماده كحد شهري جديد (مثال: 3000 أو 5000):")
            return
        if text in ['➕ إضافة باقة تويست']:
            if not is_admin(user_id): return
            user_states[user_id] = {'step': 'add_twist_sub_days'}
            await update.message.reply_text('⏳ أرسل عدد الأيام للباقة (مثال: 3):')
            return
        if text in ['📋 عرض باقات تويست']:
            if not is_admin(user_id): return
            subs = db['twist_settings'].get('subscriptions', [])
            if not subs:
                await update.message.reply_text('⚠️ لا توجد باقات تويست مدفوعة مضافة حالياً.')
                return
            msg_txt = '📋 **باقات تويست المدفوعة الحالية:**\n\n'
            inline = []
            for idx, s in enumerate(subs):
                msg_txt += f"{idx + 1}. اشتراك {s['days']} يوم | {s['operations']} عملية - السعر: {s['price']} جنيه\n"
                inline.append([InlineKeyboardButton(f"🗑 حذف باقة {idx + 1} ({s['price']} جنيه)", callback_data=f"delete_twist_sub_{idx}")])
            await update.message.reply_text(msg_txt, reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['🎟 إدارة الكوبونات']:
            if not is_admin(user_id): return
            await update.message.reply_text('🎟 **إدارة كوبونات الخصم**', reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton('➕ إضافة كوبون خصم'), KeyboardButton('📋 قائمة الكوبونات')],
                [KeyboardButton('🔙 رجوع')]
            ], resize_keyboard=True))
            return
        if text in ['➕ إضافة كوبون خصم']:
            if not is_admin(user_id): return
            user_states[user_id] = {'step': 'add_coupon_code'}
            await update.message.reply_text('🎟 أرسل كود الكوبون الجديد (مثال: QENA50):')
            return
        if text in ['📋 قائمة الكوبونات']:
            if not is_admin(user_id): return
            coupons = db['coupons']
            if not coupons:
                await update.message.reply_text('⚠️ لا توجد كوبونات خصم مسجلة حالياً.')
                return
            msg_txt = '🎟 **قائمة كوبونات الخصم الحالية:**\n\n'
            inline = []
            for idx, c in enumerate(coupons):
                max_ops = c.get('max_uses', 'غير محدود')
                used_count = c.get('uses_count', 0)
                msg_txt += f"{idx + 1}. الكود: <code>{c['code']}</code>\n- الخصم: {c['discount']} جنيه\n- العمليات: {used_count} / {max_ops}\n➖➖➖➖➖➖➖\n"
                inline.append([InlineKeyboardButton(f"🗑 حذف الكوبون: {c['code']}", callback_data=f"delete_coupon_{idx}")])
            await update.message.reply_text(msg_txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['🛠 إدارة وضع الصيانة']:
            if not is_admin(user_id): return
            is_maint = db['settings'].get('maintenance_mode', False)
            await update.message.reply_text(f"🛠 **إدارة وضع الصيانة**\nالحالة: {'🔴 مفعل' if is_maint else '🟢 معطل'}", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🟢 إلغاء وضع الصيانة' if is_maint else '🔴 تفعيل وضع الصيانة', callback_data='toggle_maintenance')],
                [InlineKeyboardButton('✏️ تعديل رسالة الصيانة', callback_data='edit_maintenance_msg')]
            ]))
            return
        if text in ['⚙️ إعدادات المتجر']:
            if not is_admin(user_id): return
            bonus_status = '🟢 مفعلة' if db['settings'].get('daily_bonus_enabled', True) else '🔴 متوقفة'
            msg_txt = "⚙️ **إعدادات المتجر الشاملة:**\n\n"
            msg_txt += f"📱 رقم الكاش الحالي: <code>{db['settings'].get('cash_number', '01151931160')}</code>\n"
            msg_txt += f"🎁 معدل الاستبدال: كل {db['settings'].get('loyalty_to_balance_rate', 5)} نقاط = 1 جنيه\n"
            msg_txt += f"🎁 هدية اليوم: {bonus_status} (الحد الأدنى: {db['settings'].get('daily_bonus_min', 1)} - الحد الأقصى: {db['settings'].get('daily_bonus_max', 5)})\n"
            msg_txt += f"👥 نقاط دعوة الأصدقاء: {db['settings'].get('referral_reward_points', 10)} نقطة\n\nاختر من الأزرار أدناه للتعديل:"
            await update.message.reply_text(msg_txt, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📱 تغيير رقم الكاش', callback_data='change_cash_num')],
                [InlineKeyboardButton('🎁 تعديل معدل نقاط الولاء', callback_data='change_loyalty_rate')],
                [InlineKeyboardButton('🎁 تعديل قيم الهدية اليومية', callback_data='change_daily_bonus_limits')],
                [InlineKeyboardButton('🔴 إيقاف هدية اليوم' if 'مفعلة' in bonus_status else '🟢 تفعيل هدية اليوم', callback_data='toggle_daily_bonus_status')],
                [InlineKeyboardButton('👥 تعديل نقاط دعوة الأصدقاء', callback_data='change_referral_reward')]
            ]))
            return
        if text in ['🤖 حالة الذكاء الاصطناعي']:
            if not is_admin(user_id): return
            db['settings']['ai_bot_enabled'] = not db['settings'].get('ai_bot_enabled', True)
            save_db()
            await update.message.reply_text(f"🤖 حالة الذكاء الاصطناعي أصبحت: {'✅ مفعل' if db['settings']['ai_bot_enabled'] else '❌ معطل'}")
            return
        if text in ['👥 المستخدمين']:
            if not is_admin(user_id): return
            users = db['users']
            if not users:
                await update.message.reply_text('⚠️ لا توجد مستخدمين مسجلين.')
                return
            inline = [[InlineKeyboardButton(f"{'🔴 فك حظر' if u.get('is_banned') else '🟢 حظر'} | ID: {u['user_id']} ({u.get('first_name', 'مستخدم')})", callback_data=f"toggle_ban_{u['user_id']}")] for u in users[-10:]]
            await update.message.reply_text(f"👥 إجمالي المستخدمين: {len(users)}\nاختر مستخدم لتعديل حالته (حظر / فك حظر):", reply_markup=InlineKeyboardMarkup(inline))
            return
        if text in ['📊 إحصائيات']:
            if not is_admin(user_id): return
            await update.message.reply_text(f"📊 إحصائيات المتجر:\n- المستخدمين: {len(db['users'])}\n- الطلبات: {len(db['orders'])}\n- الشركات: {len(db['companies'])}\n- الباقات: {len(db['packages'])}")
            return
        if text in ['📢 بث عام']:
            if not is_admin(user_id): return
            user_states[user_id] = {'step': 'broadcast'}
            await update.message.reply_text('📢 أرسل الآن الرسالة التي تريد بثها لكل المستخدمين:')
            return
        if text in ['💡 عرض الاقتراحات']:
            if not is_admin(user_id): return
            suggestions = db['suggestions']
            if not suggestions:
                await update.message.reply_text('⚠️ لا توجد اقتراحات أو شكاوى حالياً.')
                return
            msg_txt = '💡 **قائمة الاقتراحات والشكاوى:**\n\n'
            for s in suggestions[-10:]:
                msg_txt += f"👤 من: {s['user_mention']} (ID: {s['user_id']})\n💬 النص: {s['content']}\n📅 التاريخ: {datetime.fromisoformat(s['created_date']).strftime('%Y-%m-%d %H:%M')}\n➖➖➖➖➖➖➖\n"
            await update.message.reply_text(msg_txt)
            return
        if text in ['📋 الطلبات']:
            if not is_admin(user_id): return
            orders = [o for o in db['orders'] if o['status'] == 'pending']
            if not orders:
                await update.message.reply_text('⚠️ لا توجد طلبات معلقة حالياً.')
                return
            for o in orders:
                order_text = f"🔔 **طلب جديد معلق #{o['id']}**\n\n👤 العميل: {o['user_mention']} (<code>{o['user_id']}</code>)\n📦 الخدمة/الباقة: {o['package_id']}\n📱 الهاتف/المحفظة: {o.get('phone') or o.get('wallet_phone')}\n💰 القيمة: {o['final_price']} جنيه"
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton('✅ قبول وتأكيد', callback_data=f"approve_order_{o['id']}"), InlineKeyboardButton('❌ رفض', callback_data=f"reject_order_{o['id']}")]
                ])
                if o.get('receipt') and o['receipt'] != 'بدون إيصال' and len(o['receipt']) > 20:
                    try:
                        await context.bot.send_photo(chat_id, o['receipt'], caption=order_text, reply_markup=markup, parse_mode='HTML')
                        continue
                    except Exception:
                        pass
                await context.bot.send_message(chat_id, order_text + f"\n📸 الإيصال: {o.get('receipt')}", reply_markup=markup, parse_mode='HTML')
            return
        if text in ['🔙 رجوع']:
            if chat_id in user_states: del user_states[chat_id]
            if is_admin(chat_id):
                await update.message.reply_text('🔐 لوحة التحكم الرئيسية', reply_markup=admin_keyboard)
            else:
                await update.message.reply_text('القائمة الرئيسية:', reply_markup=main_keyboard)
            return

        if len(text) == 1 and text in ['1', '2', '3', '4', '5']:
            await update.message.reply_text(f"⭐ شكراً لك على تقييمك بـ ({text} نجوم)! رأيك يهمني ويسعدنا دائماً تقديم أفضل خدمة لك.")
            return

        if user_id not in user_states and not is_admin(user_id):
            ai_reply = await ask_ai(text)
            if ai_reply: await update.message.reply_text(ai_reply)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data

    if data == 'check_sub':
        if await check_subscription(context.bot, user_id):
            await query.answer('✅ تم التحقق من اشتراكك بنجاح!')
            await context.bot.send_message(chat_id, '🎉 شكراً لاشتراكك! يمكنك استخدام البوت الآن.')
        else:
            await query.answer('❌ لم تشترك في القنوات الإجبارية بعد!', show_alert=True)
        return

    if data == 'claim_daily_bonus':
        if db['settings'].get('daily_bonus_enabled', True) is False:
            await query.answer('⚠️ خدمة هدية اليوم متوقفة مؤقتاً من الإدارة!', show_alert=True)
            return
        user = next((u for u in db['users'] if u['user_id'] == user_id), None)
        if not user:
            add_user(query.from_user)
            user = next((u for u in db['users'] if u['user_id'] == user_id), None)

        now = datetime.now(timezone.utc)
        if user.get('last_daily_bonus'):
            last_date = datetime.fromisoformat(user['last_daily_bonus'])
            if last_date.date() == now.date():
                await query.answer('⏳ لقد استلمت هدية اليوم بالفعل! تجدد الهدية يومياً.', show_alert=True)
                return

        min_v = db['settings'].get('daily_bonus_min', 1)
        max_v = db['settings'].get('daily_bonus_max', 5)
        reward = random.randint(min_v, max_v)

        user['loyalty_points'] = user.get('loyalty_points', 0) + reward
        user['last_daily_bonus'] = now.isoformat()
        save_db()

        await query.answer(f"🎉 مبروك! ربحت {reward} نقطة ولاء")
        await context.bot.send_message(chat_id, f"🎉 مبروك يا غالي!\nحصلت على هدية اليوم: **{reward} نقطة ولاء** إضافية 🎁\nرصيدك الحالي: {user['loyalty_points']} نقطة.", parse_mode='Markdown')
        return

    if data == 'get_referral_link':
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        await query.answer()
        await context.bot.send_message(chat_id, f"👥 **نظام دعوة الأصدقاء (ريفيرال):**\n\nشارك الرابط أدناه مع أصدقائك، وكل شخص يدخل ويسجل في البوت سيتم منحك مكافأة نقاط ولاء فورية:\n\n<code>{ref_link}</code>", parse_mode='HTML')
        return

    if data == 'change_cash_num':
        if not is_admin(user_id): return
        user_states[user_id] = {'step': 'set_new_cash_number'}
        await query.answer()
        await context.bot.send_message(chat_id, '📱 أرسل رقم الكاش الجديد (مثال: 01151931160):')
        return

    if data == 'change_loyalty_rate':
        if not is_admin(user_id): return
        user_states[user_id] = {'step': 'set_loyalty_rate'}
        await query.answer()
        await context.bot.send_message(chat_id, '🎁 أرسل معدل نقاط الولاء الجديد (مثال: كل كم نقطة تساوي 1 جنيه؟ اكتب الرقم فقط):')
        return

    if data == 'change_daily_bonus_limits':
        if not is_admin(user_id): return
        user_states[user_id] = {'step': 'set_daily_bonus_min'}
        await query.answer()
        await context.bot.send_message(chat_id, '📉 أرسل الحد الأدنى لنقاط الهدية اليومية (مثال: 1):')
        return

    if data == 'toggle_daily_bonus_status':
        if not is_admin(user_id): return
        db['settings']['daily_bonus_enabled'] = not db['settings'].get('daily_bonus_enabled', True)
        save_db()
        await query.answer('✅ تم تغيير حالة الهدية اليومية')
        await context.bot.send_message(chat_id, f"🔄 أصبحت هدية اليوم الآن: {'🟢 مفعلة' if db['settings']['daily_bonus_enabled'] else '🔴 متوقفة'}.")
        return

    if data == 'change_referral_reward':
        if not is_admin(user_id): return
        user_states[user_id] = {'step': 'set_referral_reward'}
        await query.answer()
        await context.bot.send_message(chat_id, '👥 أرسل عدد نقاط المكافأة لدعوة الأصدقاء (مثال: 10):')
        return

    if data == 'convert_loyalty':
        user = next((u for u in db['users'] if u['user_id'] == user_id), None)
        rate = db['settings'].get('loyalty_to_balance_rate', 5)
        if not user or user.get('loyalty_points', 0) < rate:
            await query.answer(f"⚠️ نقاط الولاء غير كافية! الحد الأدنى للتحويل هو {rate} نقطة.", show_alert=True)
            return
        transferable_points = (user['loyalty_points'] // rate) * rate
        added_balance = transferable_points / rate

        user['loyalty_points'] -= transferable_points
        user['balance'] = user.get('balance', 0) + added_balance
        save_db()

        await query.answer(f"✅ تم تحويل {transferable_points} نقطة إلى {added_balance} جنيه بنجاح!")
        await context.bot.send_message(chat_id, f"🎉 مبروك! تم خصم {transferable_points} نقطة ولاء وإضافة **{added_balance} جنيه** إلى رصيد محفظتك الداخلية.\n💰 رصيدك الحالي: {user['balance']} جنيه.", parse_mode='Markdown')
        return

    if data.startswith('toggle_ban_'):
        if not is_admin(user_id): return
        target_id = int(data.split('_')[2])
        target_user = next((u for u in db['users'] if u['user_id'] == target_id), None)
        if target_user:
            target_user['is_banned'] = not target_user.get('is_banned', False)
            save_db()
            await query.answer('✅ تم تغيير حالة المستخدم بنجاح')
            await query.edit_message_text(f"👥 تم تحديث حالة المستخدم (ID: {target_id}): أصبح {'🔴 محظور' if target_user['is_banned'] else '🟢 غير محظور'}.")
        return

    if data.startswith('toggle_pkg_'):
        if not is_admin(user_id): return
        pkg_id = int(data.split('_')[2])
        pkg = next((p for p in db['packages'] if p['id'] == pkg_id), None)
        if pkg:
            pkg['is_active'] = not pkg.get('is_active', True)
            save_db()
            await query.answer('✅ تم تغيير حالة الباقة')
            await context.bot.send_message(chat_id, f"🔄 أصبحت باقة \"{pkg['name']}\" الآن: {'🟢 مفعلة' if pkg['is_active'] else '🔴 متوقفة مؤقتاً'}.")
        return

    if data == 'toggle_maintenance':
        if not is_admin(user_id): return
        db['settings']['maintenance_mode'] = not db['settings'].get('maintenance_mode', False)
        save_db()
        await query.answer('✅ تم التبديل')
        await query.edit_message_text(f"🛠 وضع الصيانة أصبح: {'مفعل' if db['settings']['maintenance_mode'] else 'معطل'}")
        return

    if data == 'edit_maintenance_msg':
        if not is_admin(user_id): return
        user_states[user_id] = {'step': 'set_maintenance_msg'}
        await query.answer()
        await context.bot.send_message(chat_id, '✏️ أرسل رسالة الصيانة الجديدة:')
        return

    if data.startswith('delete_twist_sub_'):
        if not is_admin(user_id): return
        idx = int(data.split('_')[3])
        if idx < len(db['twist_settings']['subscriptions']):
            db['twist_settings']['subscriptions'].pop(idx)
            save_db()
            await query.answer('✅ تم حذف باقة تويست بنجاح')
            await context.bot.send_message(chat_id, '🗑 تم حذف باقة تويست المدفوعة بنجاح.')
        return

    if data.startswith('delete_coupon_'):
        if not is_admin(user_id): return
        idx = int(data.split('_')[3])
        if idx < len(db['coupons']):
            removed = db['coupons'].pop(idx)
            save_db()
            await query.answer('✅ تم حذف الكوبون بنجاح')
            await context.bot.send_message(chat_id, f"🗑 تم حذف الكوبون ({removed['code']}) بنجاح.")
        return

    if data.startswith('buy_twist_sub_'):
        idx = int(data.split('_')[3])
        subs = db['twist_settings'].get('subscriptions', [])
        if idx >= len(subs):
            await query.answer('⚠️ الباقة غير موجودة!', show_alert=True)
            return
        sub = subs[idx]
        
        new_order = {
            'id': max([o['id'] for o in db['orders']], default=0) + 1,
            'user_id': user_id,
            'user_mention': f"@{query.from_user.username}" if query.from_user.username else (query.from_user.first_name or str(user_id)),
            'package_id': f"اشتراك تويست ({sub['days']} يوم - {sub['operations']} عملية)",
            'phone': 'اشتراك تويست',
            'wallet_phone': 'تحويل كاش',
            'final_price': sub['price'],
            'receipt': 'بانتظار الإيصال',
            'status': 'pending',
            'twist_sub_data': sub,
            'created_date': datetime.now(timezone.utc).isoformat()
        }
        db['orders'].append(new_order)
        save_db()

        user_states[user_id] = {'step': 'order_wallet_phone', 'packageId': 99999, 'finalPrice': sub['price']}
        await query.answer()
        current_cash_num = db['settings'].get('cash_number', '01151931160')
        await context.bot.send_message(chat_id, f"💳 تفاصيل دفع اشتراك تويست:\n\nقم بالتحويل بمبلغ <b>{sub['price']} جنيه</b> إلى رقم الكاش التالي:\n<code>{current_cash_num}</code>\n\n📱 أرسل الآن رقم المحفظة التي قمت بالتحويل منها:", parse_mode='HTML')
        return

    if data == 'twist_add_new':
        user_sessions[chat_id] = TwistMusicAPI(user_id)
        user_states[user_id] = {'step': 'twist_phone'}
        await query.answer()
        await context.bot.send_message(chat_id, '📱 أدخل رقم هاتف تويست (مثال: 011XXXXXXXX):')
        return

    if data.startswith('twist_use_saved_'):
        index = int(data.split('_')[3])
        saved = db['twist_accounts'].get(str(user_id), [])
        if index < len(saved):
            acc = saved[index]
            api = TwistMusicAPI(user_id)
            api.phone = acc['phone']
            api.token = acc['token']
            api.access_token = acc['access_token']
            api.balance = acc.get('balance', 0)
            user_sessions[chat_id] = api
            await query.answer('✅ تم استخدام الحساب المحفوظ')
            res = await api.complete_tasks()
            await context.bot.send_message(chat_id, res[1])
            await show_twist_packages(chat_id, api, context)
        return

    if data.startswith('twist_redeem_'):
        pkg_id = data.split('_')[2]
        api = user_sessions.get(chat_id)
        if not api or not api.token:
            await query.answer('⚠️ انتهت الجلسة، اختر الرقم من جديد!', show_alert=True)
            return
        await query.answer('⏳ جاري استبدال الوحدات...')
        res = await api.redeem_units(pkg_id)
        await context.bot.send_message(chat_id, res[1])
        if res[0]:
            await show_twist_packages(chat_id, api, context)
        return

    if data.startswith('delete_company_'):
        comp_id = int(data.split('_')[2])
        db['companies'] = [c for c in db['companies'] if c['id'] != comp_id]
        save_db()
        await query.answer('✅ تم حذف الشركة')
        await context.bot.send_message(chat_id, '✅ تم حذف الشركة بنجاح.')
        return

    if data.startswith('select_comp_pkg_'):
        comp_id = int(data.split('_')[3])
        user_states[user_id] = {'step': 'pkg_name', 'companyId': comp_id}
        await query.answer()
        await context.bot.send_message(chat_id, '📝 أرسل اسم الباقة الجديدة:')
        return

    if data.startswith('delete_pkg_'):
        pkg_id = int(data.split('_')[2])
        db['packages'] = [p for p in db['packages'] if p['id'] != pkg_id]
        save_db()
        await query.answer('✅ تم حذف الباقة')
        await context.bot.send_message(chat_id, '✅ تم حذف الباقة بنجاح.')
        return

    if data.startswith('order_'):
        pkg_id = int(data.split('_')[1])
        pkg = next((p for p in db['packages'] if p['id'] == pkg_id), None)
        if not pkg or not pkg.get('is_active', True):
            await query.answer('⚠️ عذراً، هذه الباقة غير متوفرة حالياً!', show_alert=True)
            return
        
        user_states[user_id] = {'step': 'order_phone', 'packageId': pkg_id}
        await query.answer()
        await context.bot.send_message(chat_id, f"📱 أدخل رقم الهاتف المراد الشحن له لباقة ({pkg['name']} - السعر: {pkg['price']} جنيه):")
        return

    if data.startswith('approve_order_'):
        order_id = int(data.split('_')[2])
        order = next((o for o in db['orders'] if o['id'] == order_id), None)
        if order:
            order['status'] = 'approved'
            save_db()
            
            if order.get('is_wallet_deposit'):
                user_obj = next((u for u in db['users'] if u['user_id'] == order['user_id']), None)
                if user_obj:
                    user_obj['balance'] = user_obj.get('balance', 0) + order['final_price']
                    save_db()
                await context.bot.send_message(order['user_id'], f"🎉 مبروك! تم قبول إيصال شحن المحفظة وتم إضافة {order['final_price']} جنيه إلى رصيدك الداخلي بنجاح.")
            elif order.get('twist_sub_data'):
                sub_data = order['twist_sub_data']
                days = int(sub_data.get('days', 1))
                ops = int(sub_data.get('operations', 10))
                expiry = datetime.now(timezone.utc).replace(microsecond=0)
                expiry += timedelta(days=days)
                db['twist_subscriptions'].append({
                    'user_id': order['user_id'],
                    'expiry_date': expiry.isoformat(),
                    'operations_left': ops
                })
                save_db()
                await context.bot.send_message(order['user_id'], f"🎉 مبروك! تم قبول طلبك وتفعيل اشتراك تويست لمدة {days} يوم ({ops} عملية) بنجاح.")
            else:
                user_obj = next((u for u in db['users'] if u['user_id'] == order['user_id']), None)
                reward = order.get('reward_points', 5)
                if user_obj:
                    user_obj['loyalty_points'] = user_obj.get('loyalty_points', 0) + reward
                    save_db()
                await context.bot.send_message(order['user_id'], f"🎉 مبروك! تم قبول طلبك وتأكيد الشحن بنجاح وتم إضافة {reward} نقطة ولاء لحسابك.\n\n⭐ نود معرفة رأيك في الخدمة، أرسل تقييمك من 1 إلى 5 نجوم في رسالة.")

            await query.answer('✅ تم القبول والتفعيل')
            await context.bot.send_message(chat_id, f"✅ تم قبول الطلب #{order_id} بنجاح.")
        return

    if data.startswith('reject_order_'):
        order_id = int(data.split('_')[2])
        order = next((o for o in db['orders'] if o['id'] == order_id), None)
        if order:
            order['status'] = 'rejected'
            save_db()
            
            user_obj = next((u for u in db['users'] if u['user_id'] == order['user_id']), None)
            if user_obj:
                if order.get('paid_from_balance') or order.get('final_price'):
                    user_obj['balance'] = user_obj.get('balance', 0) + order.get('final_price', 0)
                reward_to_deduct = order.get('reward_points', 5)
                user_obj['loyalty_points'] = max(0, user_obj.get('loyalty_points', 0) - reward_to_deduct)
                save_db()

            await query.answer('❌ تم الرفض واسترجاع الرصيد وخصم النقاط')
            await context.bot.send_message(order['user_id'], f"❌ عذراً، تم رفض طلبك من الإدارة وتم استرجاع مبلغ {order['final_price']} جنيه إلى محفظتك وخصم نقاط الولاء المرتبطة بالطلب.")
            await context.bot.send_message(chat_id, f"❌ تم رفض الطلب #{order_id} بنجاح، واسترجاع الرصيد للعميل وخصم نقاط الولاء.")
        return

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, text_handler))

    print('✅ QENAWWY STORE Bot is running...')
    app.run_polling()

if __name__ == '__main__':
    main()
