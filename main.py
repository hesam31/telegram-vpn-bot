import sqlite3
import logging
import random
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
    ContextTypes,
    MessageHandler,
    filters
)

BOT_TOKEN = "8769920545:AAHXd0IvGHnQvu1Hpb_frtR1_gB_N0ZkhfM"
ADMIN_IDS = [81469723]
SUPPORT_ID="@hesamyaghoubii"
logging.basicConfig(level=logging.INFO)

# ================= DATABASE =================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
name TEXT,
ref_by INTEGER,
ref_count INTEGER DEFAULT 0,
gifted INTEGER DEFAULT 0
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
amount INTEGER,
status TEXT,
receipt TEXT,
date TEXT
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
CREATE TABLE IF NOT EXISTS discounts(
id INTEGER PRIMARY KEY AUTOINCREMENT,
code TEXT,
percent INTEGER,
max_use INTEGER,
used INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS logs(
id INTEGER PRIMARY KEY AUTOINCREMENT,
type TEXT,
data TEXT,
date TEXT
)
""")

conn.commit()

# ================= UTIL =================

def log_event(t, d):
    cur.execute(
        "INSERT INTO logs(type,data,date) VALUES (?,?,?)",
        (t, d, str(datetime.now()))
    )
    conn.commit()


def add_user(uid, name, ref=None):
    cur.execute(
        "INSERT OR IGNORE INTO users(id,name,ref_by) VALUES (?,?,?)",
        (uid, name, ref)
    )
    conn.commit()


def get_config():
    c = cur.execute(
        "SELECT id,config FROM configs WHERE used=0 LIMIT 1"
    ).fetchone()

    if not c:
        return None

    cur.execute("UPDATE configs SET used=1 WHERE id=?", (c[0],))
    conn.commit()

    return c[1]


def apply_discount(code, price):
    d = cur.execute(
        "SELECT percent,max_use,used FROM discounts WHERE code=?",
        (code,)
    ).fetchone()

    if not d:
        return price

    percent, max_use, used = d

    if used >= max_use:
        return price

    cur.execute(
        "UPDATE discounts SET used = used + 1 WHERE code=?",
        (code,)
    )

    conn.commit()

    return price - (price * percent // 100)


# ================= UI =================

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 خرید سرویس", callback_data="buy")],
        [InlineKeyboardButton("👤 پروفایل", callback_data="profile")]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="admin_stats")],
        [InlineKeyboardButton("🛒 سفارشات", callback_data="admin_orders")],
        [InlineKeyboardButton("📦 کانفیگ ها", callback_data="admin_configs")],
        [InlineKeyboardButton("🎟 کد تخفیف", callback_data="admin_discount")]
    ])


# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    ref = None

    if context.args:
        ref = int(context.args[0])

    add_user(user.id, user.first_name, ref)

    await update.message.reply_text(
        "✨ به ربات خوش آمدید",
        reply_markup=main_menu()
    )


# ================= BUY =================

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    plans = cur.execute("SELECT * FROM plans").fetchall()

    kb = []

    for p in plans:
        kb.append([
            InlineKeyboardButton(
                f"{p[1]} | {p[2]} تومان",
                callback_data=f"plan_{p[0]}"
            )
        ])

    await q.message.edit_text(
        "پلن مورد نظر را انتخاب کنید",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def choose_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    q = update.callback_query
    await q.answer()

    plan_id = int(q.data.split("_")[1])

    price = cur.execute(
        "SELECT price FROM plans WHERE id=?",
        (plan_id,)
    ).fetchone()[0]

    amount = price + random.randint(100, 999)

    cur.execute("""
    INSERT INTO orders(user_id,plan_id,amount,status,date)
    VALUES (?,?,?,?,?)
    """, (
        q.from_user.id,
        plan_id,
        amount,
        "pending",
        str(datetime.now())
    ))

    conn.commit()

    log_event("order", f"{q.from_user.id}|{plan_id}|{amount}")

    await q.message.reply_text(
        f"💳 مبلغ پرداخت:\n{amount}\n\nرسید را ارسال کنید."
    )


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

    cur.execute(
        "UPDATE orders SET receipt=? WHERE id=?",
        (file_id, order[0])
    )

    conn.commit()

    await update.message.reply_text(
        "⏳ رسید ثبت شد\nمنتظر تایید ادمین باشید"
    )


# ================= ADMIN APPROVE =================

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    uid = int(context.args[0])

    config = get_config()

    if not config:
        await update.message.reply_text("کانفیگ موجود نیست")
        return

    await context.bot.send_message(
        uid,
        f"🚀 کانفیگ شما:\n\n{config}"
    )

    cur.execute(
        "UPDATE orders SET status='approved' WHERE user_id=? AND status='pending'",
        (uid,)
    )

    conn.commit()

    cur.execute(
        "SELECT ref_by FROM users WHERE id=?",
        (uid,)
    )

    ref = cur.fetchone()

    if ref and ref[0]:

        cur.execute(
            "UPDATE users SET ref_count = ref_count + 1 WHERE id=?",
            (ref[0],)
        )

        conn.commit()

        rcount = cur.execute(
            "SELECT ref_count FROM users WHERE id=?",
            (ref[0],)
        ).fetchone()[0]

        if rcount >= 10:

            cfg = get_config()

            if cfg:
                await context.bot.send_message(
                    ref[0],
                    f"🎁 جایزه دعوت:\n\n{cfg}"
                )

    await update.message.reply_text("ارسال شد")


# ================= ADMIN TOOLS =================

async def add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    title = context.args[0]
    price = int(context.args[1])

    cur.execute(
        "INSERT INTO plans(title,price) VALUES (?,?)",
        (title, price)
    )

    conn.commit()

    await update.message.reply_text("پلن اضافه شد")


async def add_config(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    text = " ".join(context.args)

    cur.execute(
        "INSERT INTO configs(config) VALUES (?)",
        (text,)
    )

    conn.commit()

    await update.message.reply_text("کانفیگ ذخیره شد")


async def add_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    code = context.args[0]
    percent = int(context.args[1])
    max_use = int(context.args[2])

    cur.execute(
        "INSERT INTO discounts(code,percent,max_use) VALUES (?,?,?)",
        (code, percent, max_use)
    )

    conn.commit()

    await update.message.reply_text("کد تخفیف ساخته شد")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        return

    users = cur.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    orders = cur.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    configs = cur.execute(
        "SELECT COUNT(*) FROM configs WHERE used=0"
    ).fetchone()[0]

    await update.message.reply_text(
        f"""
📊 آمار ربات

👥 کاربران: {users}
🛒 سفارشات: {orders}
📦 کانفیگ باقی مانده: {configs}
"""
    )


# ================= APP =================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buy, pattern="buy"))
app.add_handler(CallbackQueryHandler(choose_plan, pattern="plan_"))

app.add_handler(MessageHandler(filters.PHOTO, receipt))

app.add_handler(CommandHandler("approve", approve))
app.add_handler(CommandHandler("addplan", add_plan))
app.add_handler(CommandHandler("addconfig", add_config))
app.add_handler(CommandHandler("adddiscount", add_discount))
app.add_handler(CommandHandler("stats", stats))

print("Bot Started")

app.run_polling()
