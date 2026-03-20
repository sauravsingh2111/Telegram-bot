#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot for Render - Webhook Version
Yeh tumhara bot2.py ka Render-ready version hai
"""

import os
import logging
import random
import string
import sqlite3
import datetime
import time
import asyncio
import requests
from typing import Optional, Dict

# Web server ke liye
from starlette.applications import Starlette
from starlette.responses import Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
import uvicorn

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

# ------------------- CONFIGURATION -------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
PORT = int(os.environ.get("PORT", 8000))

# Tumhare channel aur group
REQUIRED_CHANNEL = "sauravsingh2109"
REQUIRED_GROUP = "sauravsingh211"

# Admin IDs - apne ID daalo
ADMIN_IDS = [7878291627]

# Conversation states
ASK_USER_ID, ASK_AMOUNT, ASK_BROADCAST_MSG = range(3)

# ------------------- SETUP -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database - SQLite (Render par chalega)
conn = sqlite3.connect("bot.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
              coins INTEGER DEFAULT 0, daily_last TEXT, referrals INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS notes
             (user_id INTEGER, note_id INTEGER PRIMARY KEY AUTOINCREMENT,
              note_text TEXT, created_at TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS referral_log
             (referrer_id INTEGER, referred_id INTEGER, date TEXT)''')
conn.commit()

# ------------------- DATABASE FUNCTIONS -------------------
def get_user(user_id: int) -> Optional[Dict]:
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        return {"user_id": row[0], "username": row[1], "first_name": row[2],
                "coins": row[3], "daily_last": row[4], "referrals": row[5]}
    return None

def create_user(user_id: int, username: str, first_name: str, referred_by: int = None):
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, coins) VALUES (?,?,?,?)",
              (user_id, username, first_name, 0))
    conn.commit()
    if referred_by:
        c.execute("INSERT INTO referral_log (referrer_id, referred_id, date) VALUES (?,?,?)",
                  (referred_by, user_id, datetime.datetime.now().isoformat()))
        c.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (referred_by,))
        update_coins(referred_by, 50)
        update_coins(user_id, 25)
        conn.commit()

def update_coins(user_id: int, amount: int) -> int:
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    c.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    return result[0] if result else 0

# ------------------- MEMBERSHIP CHECK -------------------
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        if REQUIRED_CHANNEL:
            member = await context.bot.get_chat_member(chat_id=f"@{REQUIRED_CHANNEL}", user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        if REQUIRED_GROUP:
            member = await context.bot.get_chat_member(chat_id=f"@{REQUIRED_GROUP}", user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        return True
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        return True

# ------------------- MAIN MENU -------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    if user_id is None:
        user_id = update.effective_user.id

    is_admin = user_id in ADMIN_IDS

    keyboard = [
        [InlineKeyboardButton("🎮 Games", callback_data="menu_games"),
         InlineKeyboardButton("🛠️ Utilities", callback_data="menu_utils")],
        [InlineKeyboardButton("😂 Fun", callback_data="menu_fun"),
         InlineKeyboardButton("💰 My Balance", callback_data="menu_balance")],
        [InlineKeyboardButton("📢 Channel", url=f"https://t.me/{REQUIRED_CHANNEL}"),
         InlineKeyboardButton("👥 Group", url=f"https://t.me/{REQUIRED_GROUP}")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🎉 **Welcome back!**\n\nChoose an option below:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🎉 **Welcome!**\n\nChoose an option below:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

# ------------------- START COMMAND -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = context.args[0] if context.args else None
    create_user(user.id, user.username or "", user.first_name or "", referred_by)

    if not await check_membership(user.id, context):
        keyboard = []
        if REQUIRED_CHANNEL:
            keyboard.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL}")])
        if REQUIRED_GROUP:
            keyboard.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{REQUIRED_GROUP}")])
        keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
        await update.message.reply_text(
            "🚫 **Access Denied!**\n\nPlease join our channel and group to use this bot:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await show_main_menu(update, context)

# ------------------- HELP COMMAND -------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    help_text = (
        "🎮 **Games**\n"
        "/dice [1-6] - Roll dice, win 10 coins if correct\n"
        "/lucky7 - Roll two dice, win 20 if total 7\n"
        "/spin - Spin wheel for random coins\n"
        "/daily - Claim 25 daily bonus\n"
        "/top - Top 10 leaderboard\n"
        "/referral - Get your referral link\n"
        "/balance - Check your coins\n\n"
        "🛠️ **Utilities**\n"
        "/calc [expr] - Calculator (e.g., /calc 25*4+10)\n"
        "/pass [len] - Generate password (default 12)\n"
        "/addnote [text] - Save a note\n"
        "/mynotes - View your notes\n"
        "/short [url] - Shorten URL (TinyURL)\n"
        "/weather [city] - Get weather (wttr.in)\n"
        "/translate [text] - English to Hindi\n"
        "/crypto [coin] - Crypto price (bitcoin, etc.)\n\n"
        "😂 **Fun**\n"
        "/joke - Random joke\n"
        "/fact - Random fact\n"
        "/quote - Random quote\n\n"
        "👨‍💼 **Admin**\n"
        "/stats - Bot statistics\n"
        "/add_coins [user] [amt] - Add coins\n"
        "/broadcast [msg] - Send message to all users"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    user = update.effective_user
    data = get_user(user.id)
    coins = data["coins"] if data else 0
    await update.message.reply_text(f"💰 **Your Balance:** {coins} coins", parse_mode=ParseMode.MARKDOWN)

# ------------------- GAMES -------------------
async def dice_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("🎲 Usage: /dice [1-6]")
        return
    guess = int(args[0])
    if guess < 1 or guess > 6:
        await update.message.reply_text("Number must be 1-6")
        return
    roll = random.randint(1, 6)
    if guess == roll:
        coins = 10
        msg = f"🎲 **{roll}**! You win +{coins} coins! 🎉"
    else:
        coins = -2
        msg = f"🎲 **{roll}** came. You lose {abs(coins)} coins. 😢"
    balance = update_coins(update.effective_user.id, coins)
    await update.message.reply_text(f"{msg}\n💰 Balance: {balance}")

async def lucky7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    d1, d2 = random.randint(1,6), random.randint(1,6)
    total = d1 + d2
    if total == 7:
        coins = 20
        msg = f"🎲🎲 **{d1}+{d2}=7**! Lucky 7! +{coins} coins! 🎉"
    else:
        coins = -5
        msg = f"🎲🎲 **{d1}+{d2}={total}**. Not 7. You lose {abs(coins)} coins."
    balance = update_coins(update.effective_user.id, coins)
    await update.message.reply_text(f"{msg}\n💰 Balance: {balance}")

async def spin_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    outcomes = [(100,0.05), (50,0.1), (20,0.2), (10,0.25), (5,0.25), (0,0.15)]
    r = random.random()
    cum = 0
    for coins, prob in outcomes:
        cum += prob
        if r <= cum:
            break
    if coins > 0:
        balance = update_coins(update.effective_user.id, coins)
        msg = f"🎡 **{coins} coins!** Congratulations!"
    else:
        balance = get_user(update.effective_user.id)["coins"]
        msg = "🎡 Better luck next time!"
    await update.message.reply_text(f"{msg}\n💰 Balance: {balance}")

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    user = update.effective_user
    today = datetime.datetime.now().date().isoformat()
    user_data = get_user(user.id)
    if user_data and user_data["daily_last"] == today:
        await update.message.reply_text("❌ You already claimed today's bonus! Come back tomorrow.")
        return
    coins = 25
    update_coins(user.id, coins)
    c.execute("UPDATE users SET daily_last=? WHERE user_id=?", (today, user.id))
    conn.commit()
    balance = get_user(user.id)["coins"]
    await update.message.reply_text(f"🎁 **Daily Bonus: +{coins} coins!**\n💰 Balance: {balance}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    c.execute("SELECT first_name, coins FROM users ORDER BY coins DESC LIMIT 10")
    top = c.fetchall()
    if not top:
        await update.message.reply_text("No users yet.")
        return
    text = "🏆 **TOP 10 USERS**\n"
    for i, (name, coins) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        name = name or f"User{i}"
        text += f"{medal} {i}. {name[:15]} - {coins} coins\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    bot_user = await context.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start={update.effective_user.id}"
    c.execute("SELECT COUNT(*) FROM referral_log WHERE referrer_id=?", (update.effective_user.id,))
    refs = c.fetchone()[0]
    await update.message.reply_text(
        f"🔗 **Your Referral Link:**\n`{link}`\n\n"
        f"👥 **Total Referrals:** {refs}\n"
        "🎁 **Bonus:** 50 coins for you + 25 for your friend!",
        parse_mode=ParseMode.MARKDOWN
    )

# ------------------- UTILITIES -------------------
async def calculator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    expr = " ".join(context.args)
    if not expr:
        await update.message.reply_text("🔢 Usage: /calc [expr] e.g., /calc 25*4+10")
        return
    allowed = set("0123456789+-*/(). ")
    if not all(c in allowed for c in expr):
        await update.message.reply_text("❌ Only numbers and + - * / ( ) allowed")
        return
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        await update.message.reply_text(f"🔢 **{expr} = {result}**", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def password_generator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    length = 12
    if context.args and context.args[0].isdigit():
        length = int(context.args[0])
        if length < 4: length = 4
        if length > 30: length = 30
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    pwd = ''.join(random.choice(chars) for _ in range(length))
    await update.message.reply_text(f"🔐 **Generated Password:**\n`{pwd}`\nLength: {length}", parse_mode=ParseMode.MARKDOWN)

async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    note = " ".join(context.args)
    if not note:
        await update.message.reply_text("📝 Usage: /addnote [text]")
        return
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO notes (user_id, note_text, created_at) VALUES (?,?,?)",
              (update.effective_user.id, note, now))
    conn.commit()
    await update.message.reply_text("✅ Note saved!")

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    c.execute("SELECT note_text FROM notes WHERE user_id=? ORDER BY note_id DESC LIMIT 10",
              (update.effective_user.id,))
    notes = c.fetchall()
    if not notes:
        await update.message.reply_text("📝 No notes. Use /addnote to add one.")
        return
    text = "📝 **Your recent notes:**\n"
    for i, (note,) in enumerate(notes, 1):
        text += f"{i}. {note[:50]}{'...' if len(note)>50 else ''}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def url_shortener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    url = " ".join(context.args)
    if not url:
        await update.message.reply_text("🔗 Usage: /short [url] e.g., /short https://example.com")
        return
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        r = requests.get(f"http://tinyurl.com/api-create.php?url={url}")
        if r.status_code == 200:
            await update.message.reply_text(f"🔗 **Shortened URL:**\n{r.text}")
        else:
            await update.message.reply_text("❌ Failed to shorten")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def weather_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    city = " ".join(context.args)
    if not city:
        await update.message.reply_text("🌤️ Usage: /weather [city] e.g., /weather Delhi")
        return
    try:
        r = requests.get(f"https://wttr.in/{city}?format=%t+%c+%w+%h&m")
        if r.status_code == 200:
            weather = r.text.strip()
            await update.message.reply_text(f"🌤️ **Weather in {city}:**\n{weather}")
        else:
            await update.message.reply_text("❌ City not found")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("🌐 Usage: /translate [text] e.g., /translate Hello")
        return
    try:
        r = requests.get(f"https://api.mymemory.translated.net/get?q={text}&langpair=en|hi")
        if r.status_code == 200:
            translated = r.json()["responseData"]["translatedText"]
            await update.message.reply_text(f"🌐 **Translation (English → Hindi):**\n{translated}")
        else:
            await update.message.reply_text("❌ Translation failed")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def crypto_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    coin = " ".join(context.args).lower() or "bitcoin"
    coin_map = {"btc":"bitcoin","eth":"ethereum","doge":"dogecoin","sol":"solana","xrp":"ripple"}
    coin = coin_map.get(coin, coin)
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd,inr")
        if r.status_code == 200 and coin in r.json():
            data = r.json()[coin]
            await update.message.reply_text(
                f"💰 **{coin.upper()} Price**\n"
                f"🇺🇸 USD: ${data['usd']}\n"
                f"🇮🇳 INR: ₹{data['inr']}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Coin not found or API limit")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ------------------- FUN COMMANDS -------------------
async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    jokes = [
        "👨‍🏫 Teacher: What is the opposite of 'I'?\n👦 Student: 'I' itself!\n👨‍🏫 Teacher: How?\n👦 Student: 'I eat' becomes 'eat I'! 😂",
        "👨‍⚕️ Doctor: Walk 10 min daily.\n🧔 Patient: I wake at 11 AM!\n👨‍⚕️ Doctor: Walk at 11 then!\n🧔 Patient: Everyone's back by then! 😂",
        "👩 Wife: You never listen!\n🧔 Husband: I listen... I just don't remember! 😂",
        "🔬 Why don't scientists trust atoms? Because they make up everything! 😂"
    ]
    await update.message.reply_text(random.choice(jokes))

async def fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    facts = [
        "🧠 Human brain thinks 50,000 thoughts daily!",
        "🍌 Bananas are slightly radioactive!",
        "😴 Koalas sleep 22 hours a day!",
        "🐝 Bees dance to tell where flowers are!",
        "🌊 80% of ocean is unexplored!",
        "🦷 Snails have 25,000 teeth!"
    ]
    await update.message.reply_text(random.choice(facts))

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update.effective_user.id, context):
        await start(update, context)
        return
    quotes = [
        "💪 **Success** is not final, **failure** is not fatal. It's the **courage to continue** that counts.",
        "✨ Do what you can, with what you have, where you are.",
        "🚀 Dreams are not what you see in sleep, dreams are things that do not let you sleep.",
        "😊 Happiness is when you make others happy.",
        "🌟 Believe in yourself! You are braver than you think."
    ]
    await update.message.reply_text(random.choice(quotes), parse_mode=ParseMode.MARKDOWN)

# ------------------- ADMIN COMMANDS -------------------
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(coins) FROM users")
    total_coins = c.fetchone()[0] or 0
    c.execute("SELECT AVG(coins) FROM users")
    avg_coins = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM notes")
    notes = c.fetchone()[0]
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Users: {users}\n"
        f"💰 Total Coins: {total_coins}\n"
        f"📈 Avg Coins: {avg_coins:.2f}\n"
        f"📝 Notes: {notes}",
        parse_mode=ParseMode.MARKDOWN
    )

async def add_coins_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add_coins [user_id] [amount]")
        return
    try:
        user_id, amount = int(args[0]), int(args[1])
        balance = update_coins(user_id, amount)
        await update.message.reply_text(f"✅ Added {amount} coins. New balance: {balance}")
        try:
            await context.bot.send_message(chat_id=user_id, text=f"🎁 You received {amount} coins from admin!")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: /broadcast [message]")
        return
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Announcement:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {sent}/{len(users)} users")

# ------------------- ADMIN PANEL -------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ You are not authorized to access this panel.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
         InlineKeyboardButton("➕ Add Coins", callback_data="admin_add_coins")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "👑 **Admin Panel**\n\nChoose an option:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        return

    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(coins) FROM users")
    total_coins = c.fetchone()[0] or 0
    c.execute("SELECT AVG(coins) FROM users")
    avg_coins = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM notes")
    notes = c.fetchone()[0]

    text = (
        f"📊 **Bot Statistics**\n\n"
        f"👥 Users: {users}\n"
        f"💰 Total Coins: {total_coins}\n"
        f"📈 Avg Coins: {avg_coins:.2f}\n"
        f"📝 Notes: {notes}"
    )

    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def admin_add_coins_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        return

    await query.edit_message_text(
        "➕ **Add Coins**\n\nPlease enter the user ID:",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_USER_ID

async def admin_add_coins_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        context.user_data['target_user'] = user_id
        await update.message.reply_text("Now enter the amount of coins to add:")
        return ASK_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please enter a number.")
        return ASK_USER_ID

async def admin_add_coins_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        user_id = context.user_data['target_user']
        balance = update_coins(user_id, amount)
        await update.message.reply_text(f"✅ Added {amount} coins to user {user_id}. New balance: {balance}")

        try:
            await context.bot.send_message(chat_id=user_id, text=f"🎁 You received {amount} coins from admin!")
        except:
            pass

        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
             InlineKeyboardButton("➕ Add Coins", callback_data="admin_add_coins")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
             InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ]
        await update.message.reply_text(
            "👑 **Admin Panel**\n\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a number.")
        return ASK_AMOUNT

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        return

    await query.edit_message_text(
        "📢 **Broadcast**\n\nPlease enter the message to send to all users:",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_BROADCAST_MSG

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    await update.message.reply_text(f"📢 Broadcasting message to all users...")

    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Announcement:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass

    await update.message.reply_text(f"✅ Broadcast sent to {sent}/{len(users)} users")

    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
         InlineKeyboardButton("➕ Add Coins", callback_data="admin_add_coins")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    await update.message.reply_text(
        "👑 **Admin Panel**\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# ------------------- CALLBACK HANDLERS -------------------
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not await check_membership(user_id, context):
        keyboard = []
        if REQUIRED_CHANNEL:
            keyboard.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL}")])
        if REQUIRED_GROUP:
            keyboard.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{REQUIRED_GROUP}")])
        keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
        await query.edit_message_text(
            "🚫 **Access Denied!**\n\nPlease join our channel and group first:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    data = query.data
    if data == "menu_games":
        text = (
            "🎮 **Games Menu**\n\n"
            "/dice [1-6] - Roll dice\n"
            "/lucky7 - Lucky 7\n"
            "/spin - Spin wheel\n"
            "/daily - Daily bonus\n"
            "/top - Leaderboard\n"
            "/referral - Referral link"
        )
    elif data == "menu_utils":
        text = (
            "🛠️ **Utilities Menu**\n\n"
            "/calc [expr] - Calculator\n"
            "/pass [len] - Password\n"
            "/addnote [text] - Add note\n"
            "/mynotes - View notes\n"
            "/short [url] - URL shortener\n"
            "/weather [city] - Weather\n"
            "/translate [text] - Translate\n"
            "/crypto [coin] - Crypto"
        )
    elif data == "menu_fun":
        text = (
            "😂 **Fun Menu**\n\n"
            "/joke - Random joke\n"
            "/fact - Random fact\n"
            "/quote - Random quote"
        )
    elif data == "menu_balance":
        user = get_user(user_id)
        coins = user["coins"] if user else 0
        text = f"💰 **Your Balance:** {coins} coins"
    else:
        return

    keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not await check_membership(user_id, context):
        await start(query.message, context)
        return

    await show_main_menu(update, context, user_id)

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if await check_membership(user_id, context):
        await show_main_menu(update, context, user_id)
    else:
        keyboard = []
        if REQUIRED_CHANNEL:
            keyboard.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL}")])
        if REQUIRED_GROUP:
            keyboard.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{REQUIRED_GROUP}")])
        keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
        await query.edit_message_text(
            "❌ You still haven't joined. Please join both and then click 'I've Joined':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ------------------- MAIN ASYNC FUNCTION -------------------
async def main():
    """Main function to start the bot with webhook"""
    print("="*50)
    print("BOT STARTING ON RENDER...")
    print("="*50)
    print(f"Channel: @{REQUIRED_CHANNEL}")
    print(f"Group: @{REQUIRED_GROUP}")
    print(f"Admin IDs: {ADMIN_IDS}")
    print("="*50)

    # Create application
    app = Application.builder().token(BOT_TOKEN).updater(None).build()

    # Add all command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("dice", dice_game))
    app.add_handler(CommandHandler("lucky7", lucky7))
    app.add_handler(CommandHandler("spin", spin_wheel))
    app.add_handler(CommandHandler("daily", daily_bonus))
    app.add_handler(CommandHandler("top", leaderboard))
    app.add_handler(CommandHandler("referral", referral_link))
    app.add_handler(CommandHandler("calc", calculator))
    app.add_handler(CommandHandler("pass", password_generator))
    app.add_handler(CommandHandler("addnote", add_note))
    app.add_handler(CommandHandler("mynotes", my_notes))
    app.add_handler(CommandHandler("short", url_shortener))
    app.add_handler(CommandHandler("weather", weather_info))
    app.add_handler(CommandHandler("translate", translate_text))
    app.add_handler(CommandHandler("crypto", crypto_price))
    app.add_handler(CommandHandler("joke", joke))
    app.add_handler(CommandHandler("fact", fact))
    app.add_handler(CommandHandler("quote", quote_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("add_coins", add_coins_admin))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Admin conversation handlers
    add_coins_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_coins_start, pattern="^admin_add_coins$")],
        states={
            ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_coins_get_user)],
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_coins_get_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            ASK_BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Callback handlers
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(add_coins_conv)
    app.add_handler(broadcast_conv)

    # Set webhook
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/telegram"
        await app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
        logger.info(f"✅ Webhook set to {webhook_url}")
        print(f"✅ Webhook URL: {webhook_url}")
    else:
        logger.error("❌ RENDER_EXTERNAL_URL not set!")
        print("❌ ERROR: RENDER_EXTERNAL_URL environment variable not found!")

    # Starlette app for webhook handling
    async def telegram_webhook(request: Request) -> Response:
        """Handle incoming Telegram updates"""
        await app.update_queue.put(Update.de_json(await request.json(), app.bot))
        return Response()

    async def health_check(request: Request) -> PlainTextResponse:
        """Health check endpoint for Render"""
        return PlainTextResponse("OK")

    starlette_app = Starlette(routes=[
        Route("/telegram", telegram_webhook, methods=["POST"]),
        Route("/healthcheck", health_check, methods=["GET"]),
        Route("/", health_check, methods=["GET"]),
    ])

    print(f"✅ Bot configured, starting server on port {PORT}...")

    # Start the server
    server = uvicorn.Server(
        uvicorn.Config(
            app=starlette_app,
            host="0.0.0.0",
            port=PORT,
            log_level="info"
        )
    )

    async with app:
        await app.start()
        logger.info(f"🚀 Bot started on port {PORT}")
        print(f"🚀 Bot is live! Press Ctrl+C to stop")
        await server.serve()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
