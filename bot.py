"""
Telegram Bot - Vendor/Buyer Report Number Tracker
--------------------------------------------------
- /find      : vendor + buyer দিয়ে সরাসরি রিপোর্ট নাম্বার খোঁজা
- /buyer     : শুধু buyer দিয়ে খুঁজলে vendor অনুযায়ী ভাগ করে দেখাবে
- /number    : একটা রিপোর্ট নাম্বার দিলে তার ID ও ভেন্ডর/বায়ার দেখাবে
- /edit      : (শুধু এডমিন) নির্দিষ্ট ID-এর রিপোর্ট নাম্বার এডিট করা
- /add /delete /list : (শুধু এডমিন) এন্ট্রি ম্যানেজমেন্ট
- ডেটা SQLite ফাইলে (reports.db) সেভ থাকে, বট বন্ধ করলেও হারায় না
"""

import os
import sqlite3
import logging
import asyncio
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================== কনফিগারেশন ====================
# আগে environment variable থেকে নেওয়ার চেষ্টা করবে (Railway-এর জন্য),
# না পেলে নিচের ডিফল্ট মান ব্যবহার করবে (নিজের PC-তে চালানোর জন্য)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

_admin_ids_env = os.environ.get("ADMIN_IDS", "")
if _admin_ids_env:
    # Railway Variables-এ ADMIN_IDS = 123456789,987654321 এভাবে দিলে এটা পার্স করবে
    ADMIN_IDS = [int(x.strip()) for x in _admin_ids_env.split(",") if x.strip()]
else:
    ADMIN_IDS = [123456789]  # নিজের PC-তে চালালে এখানে সরাসরি নিজের ID বসান

# DB ফাইলের পাথ environment variable থেকে নেবে (Railway Volume-এর জন্য),
# না পেলে বর্তমান ফোল্ডারে reports.db ব্যবহার করবে (নিজের PC-তে চালানোর জন্য)
DB_FILE = os.environ.get("DB_FILE", "reports.db")
# ======================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def init_db():
    """ডাটাবেস ও টেবিল তৈরি করে (না থাকলে)"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            buyer TEXT NOT NULL,
            report_number TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==================== হেল্প / স্বাগত মেসেজ ====================

def welcome_text(user_id: int) -> str:
    """সুন্দরভাবে সাজানো স্বাগত মেসেজ ও ব্যবহারবিধি (HTML ফরম্যাট)"""
    text = (
        "👋 <b>স্বাগতম!</b>\n"
        "এই বট দিয়ে Vendor ও Buyer-এর রিপোর্ট নাম্বার খুঁজে পাবেন।\n\n"
        "━━━━━━━━━━━━━━━\n"
        "🔎 <b>সবার জন্য কমান্ড</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "1️⃣ <b>Vendor + Buyer দিয়ে খোঁজা</b>\n"
        "<code>/find vendor | buyer</code>\n"
        "উদাহরণ:\n<code>/find ABC Textiles | XYZ Buyer</code>\n\n"
        "2️⃣ <b>শুধু Buyer দিয়ে খোঁজা</b> (vendor অনুযায়ী ভাগ করে দেখাবে)\n"
        "<code>/buyer buyer name</code>\n"
        "উদাহরণ:\n<code>/buyer XYZ Buyer</code>\n\n"
        "3️⃣ <b>রিপোর্ট নাম্বার দিয়ে ID খোঁজা</b>\n"
        "<code>/number report number</code>\n"
        "উদাহরণ:\n<code>/number INT-2026-00123</code>\n"
    )
    if is_admin(user_id):
        text += (
            "\n━━━━━━━━━━━━━━━\n"
            "👤 <b>শুধু এডমিনের জন্য</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "4️⃣ <b>নতুন এন্ট্রি যোগ করা</b>\n"
            "<code>/add vendor | buyer | report number</code>\n\n"
            "5️⃣ <b>এন্ট্রি এডিট করা</b> (নতুন রিপোর্ট নাম্বার বসানো)\n"
            "<code>/edit id | new report number</code>\n"
            "উদাহরণ:\n<code>/edit 5 | INT-2026-00999</code>\n\n"
            "6️⃣ <b>এন্ট্রি ডিলিট করা</b>\n"
            "<code>/delete id</code>\n\n"
            "7️⃣ <b>সব এন্ট্রি দেখা</b>\n"
            "<code>/list</code>\n"
        )
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        welcome_text(update.effective_user.id), parse_mode=ParseMode.HTML
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/find, /add ইত্যাদি ছাড়া অন্য যেকোনো লেখা (যেমন 'hi') পাঠালে স্বাগত মেসেজ দেখাবে"""
    await update.message.reply_text(
        welcome_text(update.effective_user.id), parse_mode=ParseMode.HTML
    )


# ==================== ১. Vendor + Buyer দিয়ে খোঁজা ====================

async def find_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সবাই ব্যবহার করতে পারবে: /find vendor | buyer"""
    raw = " ".join(context.args)
    if "|" not in raw:
        await update.message.reply_text(
            "সঠিক ফরম্যাটে লিখুন:\n/find <vendor> | <buyer>\n\nউদাহরণ:\n/find ABC Textiles | XYZ Buyer Ltd"
        )
        return

    vendor, buyer = [p.strip() for p in raw.split("|", 1)]
    if not vendor or not buyer:
        await update.message.reply_text("Vendor এবং Buyer দুটোই লিখতে হবে।")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT report_number FROM reports
        WHERE LOWER(vendor) = LOWER(?) AND LOWER(buyer) = LOWER(?)
        """,
        (vendor, buyer),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            f"❌ কোনো রিপোর্ট নাম্বার পাওয়া যায়নি।\nVendor: {vendor}\nBuyer: {buyer}"
        )
        return

    numbers = "\n".join(f"• {r[0]}" for r in rows)
    await update.message.reply_text(
        f"✅ Vendor: {vendor}\n✅ Buyer: {buyer}\n\nরিপোর্ট নাম্বার:\n{numbers}"
    )


# ==================== ২. শুধু Buyer দিয়ে খোঁজা (vendor-wise ভাগ করে) ====================

async def find_by_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সবাই ব্যবহার করতে পারবে: /b <buyer name>"""
    buyer = " ".join(context.args).strip()
    if not buyer:
        await update.message.reply_text(
            "সঠিক ফরম্যাটে লিখুন:\n/b <buyer name>\n\nউদাহরণ:\n/b XYZ Buyer Ltd"
        )
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT vendor, report_number FROM reports
        WHERE LOWER(buyer) = LOWER(?)
        ORDER BY vendor
        """,
        (buyer,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"❌ এই Buyer-এর কোনো এন্ট্রি পাওয়া যায়নি।\nBuyer: {buyer}")
        return

    # vendor অনুযায়ী গ্রুপ করা
    grouped = {}
    for vendor, report_number in rows:
        grouped.setdefault(vendor, []).append(report_number)

    lines = [f"🔎 <b>Buyer:</b> {html.escape(buyer)}\n"]
    for vendor, numbers in grouped.items():
        lines.append(f"\n🏭 <b>{html.escape(vendor)}</b>")
        for num in numbers:
            lines.append(f"   • <code>{html.escape(num)}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ==================== ৩. রিপোর্ট নাম্বার দিয়ে ID খোঁজা ====================

async def find_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সবাই ব্যবহার করতে পারবে: /number <report number>"""
    report_number = " ".join(context.args).strip()
    if not report_number:
        await update.message.reply_text(
            "সঠিক ফরম্যাটে লিখুন:\n/number <report number>\n\nউদাহরণ:\n/number INT-2026-00123"
        )
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, vendor, buyer FROM reports
        WHERE LOWER(report_number) = LOWER(?)
        """,
        (report_number,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"❌ এই রিপোর্ট নাম্বার খুঁজে পাওয়া যায়নি।\nReport #: {report_number}")
        return

    lines = [f"✅ Report #: {report_number}\n"]
    for entry_id, vendor, buyer in rows:
        lines.append(f"\n🆔 ID: {entry_id}\nVendor: {vendor}\nBuyer: {buyer}")

    await update.message.reply_text("\n".join(lines))


# ==================== এডমিন কমান্ড ====================

async def add_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """শুধু এডমিন: /add vendor | buyer | report_number"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ড শুধুমাত্র এডমিনের জন্য।")
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3 or not all(parts):
        await update.message.reply_text(
            "সঠিক ফরম্যাটে লিখুন:\n/add <vendor> | <buyer> | <report_number>\n\n"
            "উদাহরণ:\n/add ABC Textiles | XYZ Buyer Ltd | INT-2026-00123"
        )
        return

    vendor, buyer, report_number = parts
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reports (vendor, buyer, report_number) VALUES (?, ?, ?)",
        (vendor, buyer, report_number),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    await update.message.reply_text(
        f"✅ যোগ করা হয়েছে (ID: {new_id})\nVendor: {vendor}\nBuyer: {buyer}\nReport #: {report_number}"
    )


async def edit_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """শুধু এডমিন: /edit <id> | <new_report_number>"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ড শুধুমাত্র এডমিনের জন্য।")
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 2 or not all(parts) or not parts[0].isdigit():
        await update.message.reply_text(
            "সঠিক ফরম্যাটে লিখুন:\n/edit <id> | <new_report_number>\n\n"
            "উদাহরণ:\n/edit 5 | INT-2026-00999\n\n"
            "(ID জানতে /list অথবা /number ব্যবহার করুন)"
        )
        return

    entry_id = int(parts[0])
    new_report_number = parts[1]

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT vendor, buyer, report_number FROM reports WHERE id = ?", (entry_id,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text(f"❌ ID {entry_id} খুঁজে পাওয়া যায়নি।")
        conn.close()
        return

    old_number = row[2]
    cur.execute("UPDATE reports SET report_number = ? WHERE id = ?", (new_report_number, entry_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✏️ আপডেট করা হয়েছে (ID: {entry_id})\n"
        f"Vendor: {row[0]}\nBuyer: {row[1]}\n"
        f"পুরনো Report #: {old_number}\n"
        f"নতুন Report #: {new_report_number}"
    )


async def delete_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """শুধু এডমিন: /delete <id>"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ড শুধুমাত্র এডমিনের জন্য।")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("সঠিক ফরম্যাটে লিখুন:\n/delete <id>\n\n(ID জানতে /list ব্যবহার করুন)")
        return

    entry_id = int(context.args[0])
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT vendor, buyer, report_number FROM reports WHERE id = ?", (entry_id,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text(f"❌ ID {entry_id} খুঁজে পাওয়া যায়নি।")
        conn.close()
        return

    cur.execute("DELETE FROM reports WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🗑️ মুছে ফেলা হয়েছে:\nVendor: {row[0]}\nBuyer: {row[1]}\nReport #: {row[2]}"
    )


async def list_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """শুধু এডমিন: /list - সব এন্ট্রি দেখায়"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ড শুধুমাত্র এডমিনের জন্য।")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, vendor, buyer, report_number FROM reports ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("এখনো কোনো এন্ট্রি নেই।")
        return

    lines = [f"#{r[0]} | {r[1]} | {r[2]} | {r[3]}" for r in rows]
    text = "সর্বশেষ ৫০টি এন্ট্রি:\n\n" + "\n".join(lines)

    # টেলিগ্রাম মেসেজ লিমিট (৪০৯৬ ক্যারেক্টার) মাথায় রেখে ভাগ করে পাঠানো
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])


def main():
    # Python 3.14-এ implicit event loop তৈরি হওয়া বন্ধ হয়ে গেছে,
    # তাই ম্যানুয়ালি একটা event loop তৈরি করে সেট করে দেওয়া হচ্ছে
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_report))
    app.add_handler(CommandHandler("buyer", find_by_buyer))
    app.add_handler(CommandHandler("number", find_by_number))
    app.add_handler(CommandHandler("add", add_report))
    app.add_handler(CommandHandler("edit", edit_report))
    app.add_handler(CommandHandler("delete", delete_report))
    app.add_handler(CommandHandler("list", list_reports))
    # কমান্ড নয় এমন যেকোনো লেখা (যেমন "hi", "hello") এলে স্বাগত মেসেজ দেখাবে
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("বট চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()