import telebot
from telebot import types

TOKEN = 'YOUR_BOT_TOKEN'
bot = telebot.TeleBot(8820254769:AAFg8Dy89XVd5UvLc7vMejbRN6P2fFYSapw)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_offers = types.InlineKeyboardButton("🎁 العروض والأسعار", callback_data='offers')
    btn_support = types.InlineKeyboardButton("💬 التواصل والدعم", callback_data='support')
    markup.add(btn_offers, btn_support)
    
    bot.send_message(
        message.chat.id,
        "مرحباً بك في بوت **القناوي ستور**! 🛒\nاختر من القائمة بالأسفل:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    if call.data == 'offers':
        bot.send_message(call.message.chat.id, "📦 باقات وعروض القناوي ستور متوفرة الآن بأفضل الأسعار!")
    elif call.data == 'support':
        bot.send_message(call.message.chat.id, "للتواصل مع الدعم الفني وخدمة العملاء يرجى إرسال رسالتك هنا.")

bot.infinity_polling()
