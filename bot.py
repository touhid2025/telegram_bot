"""
Telegram Bot - Vendor/Buyer Report Number Tracker
--------------------------------------------------
- যেকোনো ইউজার /find কমান্ড দিয়ে vendor ও buyer লিখলে সংশ্লিষ্ট রিপোর্ট নাম্বার(গুলো) পাবে
- শুধুমাত্র ADMIN_IDS তালিকায় থাকা Telegram ID /add এবং /delete ব্যবহার করতে পারবে
- ডেটা SQLite ফাইলে (reports.db) সেভ থাকে, বট বন্ধ করলেও হারায় না
"""

import sqlite3
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ==================== কনফিগারেশন ====================
BOT_TOKEN = "8860673369:AAG_rOSkjzljf0nxSMQsSx5Ms0u0e2u9gTA"      # @BotFather থেকে পাওয়া টোকেন বসান
ADMIN_IDS = [1621149302]                 # @userinfobot থেকে পাওয়া আপনার Telegram ID বসান (একাধিক হলে কমা দিয়ে যোগ করুন)
DB_FILE = "reports.db"
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


# ==================== কমান্ড হ্যান্ডলার ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "স্বাগতম! এই বট দিয়ে Vendor ও Buyer দিলে রিপোর্ট নাম্বার খুঁজে পাবেন।\n\n"
        "📌 কমান্ড তালিকা:\n"
        "/find <vendor> | <buyer> - রিপোর্ট নাম্বার খুঁজুন\n"
    )
    if is_admin(update.effective_user.id):
        text += (
            "/add <vendor> | <buyer> | <report_number> - নতুন এন্ট্রি যোগ করুন (শুধু এডমিন)\n"
            "/delete <id> - এন্ট্রি মুছুন (শুধু এডমিন)\n"
            "/list - সব এন্ট্রি দেখুন (শুধু এডমিন)\n"
        )
    await update.message.reply_text(text)


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
    app.add_handler(CommandHandler("add", add_report))
    app.add_handler(CommandHandler("delete", delete_report))
    app.add_handler(CommandHandler("list", list_reports))

    logger.info("বট চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()