import sqlite3
import asyncio
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = "8769920545:AAHXd0IvGHnQvu1Hpb_frtR1_gB_N0ZkhfM"
ADMIN_IDS = [81469723]
SUPPORT_ID="@hesamyaghoubii"
# ================= DB =================

db = sqlite3.connect("sedora.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
ref_by INTEGER DEFAULT NULL,
ref_count INTEGER DEFAULT 0,
test_used INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS plans(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
price INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
plan_id INTEGER,
status TEXT,
receipt TEXT,
created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS configs(
id INTEGER PRIMARY KEY AUTOINCREMENT,
config TEXT,
used INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS test_configs(
id INTEGER PRIMARY KEY AUTOINCREMENT,
config TEXT,
used INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings(
key TEXT PRIMARY KEY,
value TEXT
)
""")

db.commit()

# ================= DEFAULT SETTINGS =================

def get_setting(key, default=""):
    r = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def set_setting(key, value):
    cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    db.commit()

set_setting("welcome", "✨ Welcome to SedoraNet")
set_setting("rules", "📜 Rules: No abuse allowed")

# ================= UI =================

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ خرید اشتراک", callback_data="buy")],
        [InlineKeyboardButton("🎁 تست رایگان", callback_data="test")],
        [InlineKeyboardButton("📜 قوانین", callback_data="rules")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="profile")],
        [InlineKeyboardButton("🎁 دعوت دوستان", callback_data="ref")],
        [InlineKeyboardButton("🛠 پشتیبانی", callback_data="support")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="stats")],
        [InlineKeyboardButton("➕ افزودن پلن", callback_data="addplan")],
        [InlineKeyboardButton("📦 کانفیگ", callback_data="configs")],
        [InlineKeyboardButton("🧪 تست‌ها", callback_data="tests")],
        [InlineKeyboardButton("🔙 خروج", callback_data="home")]
    ])

# ================= CORE =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cur.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (user.id,))
    db.commit()

    await update.message.reply_text(
        get_setting("welcome"),
        reply_markup=main_menu()
    )

# ================= BUY FLOW =================

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    plans = cur.execute("SELECT * FROM plans").fetchall()

    buttons = [
        [InlineKeyboardButton(f"{p[1]} - {p[2]} تومان", callback_data=f"plan_{p[0]}")]
        for p in plans
    ]

    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])

    await q.message.edit_text("💎 انتخاب پلن:", reply_markup=InlineKeyboardMarkup(buttons))

async def select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    plan_id = int(q.data.split("_")[1])

    cur.execute(
        "INSERT INTO orders(user_id,plan_id,status,created_at) VALUES(?,?,?,?)",
        (q.from_user.id, plan_id, "pending", str(datetime.now()))
    )
    db.commit()

    await q.message.reply_text("📤 لطفاً رسید پرداخت را ارسال کنید")

# ================= RECEIPT =================

async def receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    order = cur.execute("""
        SELECT id FROM orders
        WHERE user_id=? AND status='pending'
        ORDER BY id DESC LIMIT 1
    """, (user.id,)).fetchone()

    if not order:
        return

    file_id = update.message.photo[-1].file_id

    cur.execute("UPDATE orders SET receipt=? WHERE id=?", (file_id, order[0]))
    db.commit()

    await update.message.reply_text("⏳ در حال بررسی توسط ادمین...")

# ================= ADMIN APPROVE =================

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != "@hesamyaghoubii":
        return

    order = cur.execute("""
        SELECT user_id FROM orders WHERE status='pending'
        ORDER BY id ASC LIMIT 1
    """).fetchone()

    if not order:
        await update.message.reply_text("سفارشی نیست")
        return

    config = cur.execute("SELECT id,config FROM configs WHERE used=0 LIMIT 1").fetchone()

    if not config:
        await update.message.reply_text("❌ کانفیگ نداریم")
        return

    cur.execute("UPDATE configs SET used=1 WHERE id=?", (config[0],))
    cur.execute("UPDATE orders SET status='done' WHERE user_id=?", (order[0],))
    db.commit()

    await context.bot.send_message(order[0], f"🎉 کانفیگ شما:\n\n{config[1]}")

# ================= TEST =================

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id

    user = cur.execute("SELECT test_used FROM users WHERE id=?", (user_id,)).fetchone()

    if user[0] == 1:
        await q.message.reply_text("❌ قبلاً تست گرفتی")
        return

    config = cur.execute("SELECT id,config FROM test_configs WHERE used=0 LIMIT 1").fetchone()

    if not config:
        await q.message.reply_text("❌ تست نداریم")
        return

    cur.execute("UPDATE test_configs SET used=1 WHERE id=?", (config[0],))
    cur.execute("UPDATE users SET test_used=1 WHERE id=?", (user_id,))
    db.commit()

    await q.message.reply_text(f"🎁 تست شما:\n\n{config[1]}")

# ================= ADMIN =================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("⚙️ پنل ادمین", reply_markup=admin_menu())

# ================= ROUTER =================

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    data = q.data

    if data == "buy":
        await buy(update, context)

    elif data.startswith("plan_"):
        await select_plan(update, context)

    elif data == "test":
        await test(update, context)

    elif data == "home":
        await q.message.edit_text("🏠", reply_markup=main_menu())

# ================= APP =================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(CallbackQueryHandler(router))
app.add_handler(MessageHandler(filters.PHOTO, receipt))

app.run_polling()
