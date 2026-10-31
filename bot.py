import os
import re
import html
import json
import random
import asyncio
from datetime import datetime, timedelta
import urllib.parse
import aiohttp
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

def parse_target(val: str):
    if not val:
        return ""
    val = str(val).strip()
    if val.startswith("-100") or val.startswith("-") or val.isdigit():
        try:
            return int(val)
        except ValueError:
            return val
    if not val.startswith("@"):
        return f"@{val}"
    return val

# =========================================================
# CONFIGURATIONS
# =========================================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
FILE_BOT_TOKEN = os.environ.get("FILE_BOT_TOKEN", BOT_TOKEN).strip()
FILE_BOT_USERNAME = os.environ.get("FILE_BOT_USERNAME", "").replace("@", "").strip()

MONGO_URI = os.environ.get("MONGO_URI", "").strip()

STORAGE_CHANNEL_RAW = os.environ.get("STORAGE_CHANNEL", "-1004413765578").strip()
STORAGE_CHANNEL = parse_target(STORAGE_CHANNEL_RAW)
VIP_CHANNEL_RAW = os.environ.get("VIP_CHANNEL", "-1004387584375").strip()
VIP_CHANNEL = parse_target(VIP_CHANNEL_RAW)
MAIN_CHANNEL = parse_target(os.environ.get("MAIN_CHANNEL", "@cinexlk"))
BACKUP_CHANNEL_RAW = os.environ.get("BACKUP_CHANNEL", "-1003901762623").strip()
BACKUP_CHANNEL = parse_target(BACKUP_CHANNEL_RAW)
BACKUP_CHANNEL_LINK = os.environ.get("BACKUP_CHANNEL_LINK", "").strip()

ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "0"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").replace("@", "").strip()

VIP_PLANS = {
    "1d": {"label": "1 Day Trial", "days": 1, "price": int(os.environ.get("VIP_PRICE_1D", "99"))},
    "1m": {"label": "1 Month", "days": 30, "price": int(os.environ.get("VIP_PRICE_1M", "399"))},
    "3m": {"label": "3 Months", "days": 90, "price": int(os.environ.get("VIP_PRICE_3M", "999"))},
    "6m": {"label": "6 Months", "days": 180, "price": int(os.environ.get("VIP_PRICE_6M", "1999"))},
    "12m": {"label": "1 Year (12 Months)", "days": 365, "price": int(os.environ.get("VIP_PRICE_12M", "3999"))}
}

DEFAULT_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1000&auto=format&fit=crop"

BANK_DETAILS = os.environ.get(
    "BANK_DETAILS",
    "🏦 <b>Bank:</b> Commercial Bank\n"
    "👤 <b>Name:</b> Cinex LK Admin\n"
    "💳 <b>Account No:</b> 8001234567\n"
    "🏢 <b>Branch:</b> Colombo"
)

BOT_USERNAME = os.environ.get("BOT_USERNAME", "").replace("@", "").strip()
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
PRIMARY_AD_LINK = os.environ.get("MONETAG_STREAM_LINK", os.environ.get("ADSTERRA_DIRECT_LINK", "https://google.com")).strip()
PORT = int(os.environ.get("PORT", "8080"))

FREE_USER_DELETE_DURATION = int(os.environ.get("FREE_USER_DELETE_DURATION", "43200"))
VIP_USER_DELETE_DURATION = int(os.environ.get("VIP_USER_DELETE_DURATION", "86400"))

app = Client(
    "cinex_stable_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=32
)

db_client = AsyncIOMotorClient(MONGO_URI)
files_col = db_client["MovieDB"]["files"]
vip_users_col = db_client["MovieDB"]["vip_users"]
bot_users_col = db_client["MovieDB"]["bot_users"]
manual_orders_col = db_client["MovieDB"]["manual_orders"]

STORAGE_CLEAN = str(STORAGE_CHANNEL_RAW).replace("-100", "").replace("-", "")
CACHED_BACKUP_LINK = BACKUP_CHANNEL_LINK

# =========================================================
# VIP BACKGROUND AUTO-KICK & 3-DAY REMINDER WORKER
# =========================================================
async def auto_kick_expired_vips():
    while True:
        try:
            now = datetime.utcnow()

            three_days_later = now + timedelta(days=3)
            reminder_candidates = await vip_users_col.find({
                "initial_days": {"$gt": 1},
                "expiry_date": {"$gt": now, "$lte": three_days_later},
                "reminded_3d": {"$ne": True}
            }).to_list(length=100)

            for u in reminder_candidates:
                uid = u.get("user_id")
                exp = u.get("expiry_date")
                rem_days = max(1, (exp - now).days) if isinstance(exp, datetime) else 3
                rem_text = (
                    "⏳ <b>Cinex LK VIP Pass Expiry Reminder:</b>\n\n"
                    f"ඔබගේ Cinex LK VIP සාමාජිකත්වය තවත් <b>දින {rem_days}කින්</b> අවසන් වීමට නියමිතයි.\n\n"
                    "👑 බාධාවකින් තොරව VIP Direct Files සහ චැනල් ප්‍රවේශය දිගටම ලබාගැනීමට පහත Button එක මඟින් ඔබගේ සාමාජිකත්වය අලුත් කරගන්න 👇"
                )
                markup = {"inline_keyboard": [[{"text": "👑 Renew VIP Pass", "url": f"https://t.me/{BOT_USERNAME}?start=buyvip"}]]}
                res = await send_tg_message(uid, rem_text, markup)
                if res.get("ok"):
                    await vip_users_col.update_one({"user_id": uid}, {"$set": {"reminded_3d": True}})

            expired_users = await vip_users_col.find({
                "expiry_date": {"$lt": now},
                "is_kicked": {"$ne": True}
            }).to_list(length=100)

            for u in expired_users:
                uid = u.get("user_id")
                if uid:
                    await kick_user_from_vip_channel(uid)
                    await vip_users_col.update_one({"user_id": uid}, {"$set": {"is_kicked": True}})
                    try:
                        renew_markup = {"inline_keyboard": [[{"text": "👑 Renew VIP Membership", "url": f"https://t.me/{BOT_USERNAME}?start=buyvip"}]]}
                        await send_tg_message(
                            uid,
                            "⌛ <b>ඔබගේ Cinex LK VIP සාමාජිකත්ව කාලය අවසන් විය.</b>\n\nVIP Direct Files සහ VIP Channel ප්‍රවේශය නැවත සක්‍රිය කරගැනීමට පහත Button එක ඔබන්න 👇",
                            renew_markup
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"Auto-kick worker error: {e}")
        
        await asyncio.sleep(600)

# =========================================================
# DYNAMIC VIP MENU & BUTTON BUILDER
# =========================================================
def get_vip_selection_menu():
    text = (
        "👑 <b>Cinex LK VIP Pass Membership</b>\n\n"
        "✨ <b>VIP සාමාජිකත්වයේ වාසි:</b>\n"
        "• කිසිදු දැන්වීමක් නොමැත (100% No Ads Direct Files)\n"
        "• Direct Files ක්ෂණිකව ලබාගත හැක\n"
        "• VIP Channel එකට අඛණ්ඩ ප්‍රවේශය\n"
        "• පැය 24ක Auto-Delete කාලයක් හිමිවීම\n\n"
        "👇 <b>ඔබට අවශ්‍ය VIP පැකේජය තෝරන්න:</b>"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⚡ 1 Day Trial - Rs. {VIP_PLANS['1d']['price']}", callback_data="buyplan_1d")
        ],
        [
            InlineKeyboardButton(f"👑 1 Month - Rs. {VIP_PLANS['1m']['price']}", callback_data="buyplan_1m"),
            InlineKeyboardButton(f"🔥 3 Months - Rs. {VIP_PLANS['3m']['price']}", callback_data="buyplan_3m")
        ],
        [
            InlineKeyboardButton(f"⚡ 6 Months - Rs. {VIP_PLANS['6m']['price']}", callback_data="buyplan_6m"),
            InlineKeyboardButton(f"🌟 1 Year - Rs. {VIP_PLANS['12m']['price']}", callback_data="buyplan_12m")
        ]
    ])

    return text, markup

# =========================================================
# MOVIE CATALOG (STRICTLY ONLY POSTED MOVIES)
# =========================================================
async def get_movies_page(page: int = 1, user_id: int = 0):
    limit = 10
    skip = (page - 1) * limit
    
    is_vip = await is_vip_user(user_id) if user_id else False
    
    query = {"is_posted": True}
    total_movies = await files_col.count_documents(query)

    if total_movies == 0:
        return "📂 <b>දැනට Channels වෙත නිල වශයෙන් Publish කරන ලද Movies නොමැත.</b>", None

    total_pages = (total_movies + limit - 1) // limit
    page = max(1, min(page, total_pages))

    cursor = files_col.find(query).sort("_id", -1).skip(skip).limit(limit)
    movies = await cursor.to_list(length=limit)

    tag = "👑 VIP Direct Access" if is_vip else "📥 Free Access"

    text = (
        f"🎬 <b>Cinex LK Movies Catalog ({tag})</b>\n"
        f"📄 <b>Page:</b> <code>{page} / {total_pages}</code> | <b>Published Movies:</b> <code>{total_movies}</code>\n\n"
        "👇 <b>චිත්‍රපටය ලබාගැනීමට අදාළ අංකය ඔබන්න:</b>\n\n"
    )

    buttons = []
    current_row = []
    target_bot = FILE_BOT_USERNAME if is_vip else BOT_USERNAME

    for idx, doc in enumerate(movies, 1):
        global_idx = skip + idx
        raw_name = doc.get("file_name", "Movie")
        clean_t = clean_movie_title(raw_name)[0]
        mid = doc.get("message_id")

        text += f"<b>{global_idx}.</b> {html.escape(clean_t[:35])}\n"

        target_param = f"vipfile_{mid}" if is_vip else f"adstep1_{mid}"
        btn_url = f"https://t.me/{target_bot}?start={target_param}"

        current_row.append(InlineKeyboardButton(f"🎬 {global_idx}", url=btn_url))
        if len(current_row) == 5:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="pages_info"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page + 1}"))

    buttons.append(nav_row)
    return text, InlineKeyboardMarkup(buttons)

# =========================================================
# FILE BOT DELIVERY & HTTP DISPATCHER
# =========================================================
async def send_file_bot_text(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{FILE_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                res = await resp.json()
                if res.get("ok"):
                    return res["result"]["message_id"]
    except Exception:
        pass
    return None

async def delete_file_bot_messages(chat_id: int, message_ids: list):
    url = f"https://api.telegram.org/bot{FILE_BOT_TOKEN}/deleteMessages"
    payload = {"chat_id": chat_id, "message_ids": message_ids}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)):
                pass
    except Exception:
        pass

async def auto_delete_file_task(chat_id: int, msg_ids: list, delay: int):
    await asyncio.sleep(delay)
    await delete_file_bot_messages(chat_id, msg_ids)
    await send_file_bot_text(chat_id, "🗑️ <b>ප්‍රකාශන හිමිකම් ආරක්ෂාව මත චිත්‍රපටය Chat එකෙන් ඉවත් කරන ලදී.</b>")

async def deliver_file_bot_movie(chat_id: int, message_id: int, is_vip: bool = False):
    doc = await files_col.find_one({"message_id": int(message_id)})
    if not doc or not doc.get("is_posted"):
        await send_file_bot_text(chat_id, "❌ <b>මෙම චිත්‍රපටය තවමත් නිල වශයෙන් Channels වෙත Publish කර නොමැත.</b>")
        return False

    delay = VIP_USER_DELETE_DURATION if is_vip else FREE_USER_DELETE_DURATION
    time_label = "පැය 24කින්" if is_vip else "පැය 12කින්"

    try:
        await files_col.update_one({"message_id": int(message_id)}, {"$inc": {"download_count": 1}})
    except Exception:
        pass

    warn_text = (
        "⚡ <b>Cinex LK Delivery Update:</b>\n\n"
        f"⚠️ <b>ප්‍රකාශන හිමිකම් ආරක්ෂාව මත මෙම චිත්‍රපටය තවත් {time_label} Chat එකෙන් ස්වයංක්‍රීයව මැකී යයි.</b>\n\n"
        "📲 <b>Phone එකට Save කරගන්නා ආකාරය (අනිවාර්යයි):</b>\n"
        "1. වීඩියෝව සම්පූර්ණයෙන්ම Download වූ පසු, වීඩියෝව උඩ ඇති <b>තිත් 3 (⋮)</b> ඔබන්න.\n"
        "2. එහි ඇති <b>'Save to Downloads'</b> හෝ <b>'Save to Gallery'</b> තෝරන්න.\n\n"
        "<i>(එසේ Save කළ පසු Chat එකෙන් මැකුණද චිත්‍රපටය ඔබගේ Phone එකෙහි ආරක්ෂිතව පවතී!)</i>\n\n"
        "🎬 <b>නැරඹීමට උපදෙස්:</b>\n"
        "⚠️ කරුණාකර කිසිදු අපහසුවකින් හෝ Audio ගැටලුවකින් තොරව චිත්‍රපටය නැරඹීමට <b>MX Player</b> හෝ <b>VLC Player</b> බාගත කර භාවිත කරන්න."
    )

    url = f"https://api.telegram.org/bot{FILE_BOT_TOKEN}/copyMessage"
    payload = {"chat_id": int(chat_id), "from_chat_id": str(STORAGE_CHANNEL_RAW), "message_id": int(message_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                res = await resp.json()
                if res.get("ok"):
                    sent_file_id = res["result"]["message_id"]
                    warn_msg_id = await send_file_bot_text(chat_id, warn_text)
                    ids_to_del = [sent_file_id]
                    if warn_msg_id:
                        ids_to_del.append(warn_msg_id)
                    asyncio.create_task(auto_delete_file_task(chat_id, ids_to_del, delay))
                    return True
                else:
                    await files_col.delete_one({"message_id": int(message_id)})
                    await send_file_bot_text(chat_id, "❌ <b>මෙම චිත්‍රපටය Storage එකෙන් ඉවත් කර ඇති බැවින් Catalog එකෙන්ද ඉවත් කරන ලදී.</b>")
    except Exception as e:
        await send_file_bot_text(chat_id, f"❌ Delivery Error: {e}")
    return False

# =========================================================
# WEB SERVER, ROBUST AD-GATEWAY & FILE BOT WEBHOOK
# =========================================================
routes = web.RouteTableDef()

@routes.get("/sw.js")
async def monetag_sw_js(request):
    js_content = """self.options = {
    "domain": "3nbf4.com",
    "zoneId": 12155474
}
self.lary = ""
importScripts('https://3nbf4.com/act/files/service-worker.min.js?r=sw');
"""
    return web.Response(text=js_content, content_type="application/javascript")

# SOLID GATEWAY: KILLS BRAVE, SMOOTH FLOW ON CHROME / FIREFOX / SAFARI
SAME_PAGE_GATE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sponsor Verification - Cinex LK</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; }}
        body, html {{ 
            margin: 0; 
            padding: 0; 
            min-height: 100vh; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background: #0b1118; 
            color: white; 
        }}
        .card {{
            background: #16222f;
            border: 1px solid #233446;
            border-radius: 16px;
            padding: 30px 20px;
            max-width: 420px;
            width: 90%;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        .step-label {{ font-size: 13px; font-weight: bold; color: #5da9e9; letter-spacing: 1px; margin-bottom: 8px; }}
        h2 {{ margin: 0 0 12px; font-size: 20px; color: #ffffff; }}
        p {{ font-size: 14px; color: #90a4ae; margin-bottom: 20px; line-height: 1.5; }}
        
        .count-circle {{ 
            width: 60px; 
            height: 60px; 
            border-radius: 50%; 
            border: 4px solid #5da9e9; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-weight: bold; 
            font-size: 24px; 
            color: #5da9e9; 
            margin: 0 auto 20px; 
            background: #0b1118; 
        }}
        .btn {{ 
            display: inline-block; 
            width: 100%; 
            padding: 14px; 
            border-radius: 10px; 
            font-weight: bold; 
            font-size: 15px; 
            text-decoration: none; 
            cursor: pointer; 
            transition: 0.2s; 
            border: none;
        }}
        .btn-ad {{ background: #2b7de9; color: white; margin-bottom: 12px; }}
        .btn-ad:hover {{ background: #1a68d1; }}
        .btn-done {{ display: none; background: #2fa955; color: white; }}
        .btn-done:hover {{ background: #268d46; }}

        /* BRAVE BLOCKER SCREEN */
        #brave-block-box {{
            display: none;
            background: #2a1215;
            border: 2px solid #ef4444;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
            text-align: left;
        }}
        #brave-block-box h4 {{
            margin: 0 0 8px 0;
            color: #ef4444;
            font-size: 16px;
        }}
        #brave-block-box p {{
            margin: 0;
            color: #fca5a5;
            font-size: 13px;
            line-height: 1.5;
        }}
    </style>
</head>
<body>

    <div class="card" id="mainCard">
        <div class="step-label">VERIFICATION STEP {step} OF 2</div>
        <h2>චිත්‍රපටය බාගත කිරීමට පෙර</h2>

        <!-- Brave users get blocked permanently right here -->
        <div id="brave-block-box">
            <h4>🚫 Brave Browser Blocked!</h4>
            <p>
                Brave Browser මඟින් Sponsor Ads සහ සත්‍යාපනය අවහිර කරන බැවින් මෙහිදී චිත්‍රපට ලබාගත නොහැක.<br><br>
                කරුණාකර මෙම පිටුව <b>Google Chrome</b> හෝ වෙනත් සාමාන්‍ය Browser එකකින් විවෘත කරන්න.
            </p>
        </div>

        <div id="normal-flow">
            <p id="desc">පහත Sponsor Link එක Click කර තත්පර 8ක් රැඳී සිටින්න. එවිට Telegram Link එක සක්‍රිය වේ.</p>
            
            <div class="count-circle" id="count">8</div>

            <a id="adBtn" class="btn btn-ad" href="{ad_url}" target="_blank" rel="noopener noreferrer" onclick="startTimer()">🔗 View Sponsor Ad</a>
            <a id="doneBtn" class="btn btn-done" href="https://t.me/{bot_username}?start={token}">✅ Go to Telegram</a>
        </div>
    </div>

    <script>
        // STRICT BRAVE CHECK: If Brave browser, kill the page immediately
        async function checkAndBlockBrave() {{
            try {{
                if (navigator.brave && await navigator.brave.isBrave()) {{
                    document.getElementById('brave-block-box').style.display = 'block';
                    document.getElementById('normal-flow').style.display = 'none';
                }}
            }} catch(e) {{}}
        }}
        checkAndBlockBrave();

        // PURE, BULLETPROOF TIMER FOR CHROME AND OTHER BROWSERS
        let isStarted = false;
        function startTimer() {{
            if (isStarted) return;
            isStarted = true;

            document.getElementById('adBtn').innerText = '⏳ Ad එක විවෘත විය... රැඳී සිටින්න';
            document.getElementById('adBtn').style.opacity = '0.6';
            document.getElementById('adBtn').style.pointerEvents = 'none';

            let sec = 8;
            const timer = setInterval(() => {{
                sec--;
                document.getElementById('count').innerText = sec;
                if (sec <= 0) {{
                    clearInterval(timer);
                    document.getElementById('count').style.display = 'none';
                    document.getElementById('desc').innerText = '🎉 සත්‍යාපනය සාර්ථකයි! දැන් ඔබට චිත්‍රපටය ලබාගත හැක.';
                    document.getElementById('adBtn').style.display = 'none';
                    document.getElementById('doneBtn').style.display = 'block';
                }}
            }}, 1000);
        }}
    </script>
</body>
</html>
"""

@routes.get("/")
async def root_ping(request):
    return web.Response(text="Cinex LK Hybrid Engine Alive", status=200)

@routes.get("/gate/step1/{user_id}/{msg_id}")
async def gate_step1(request):
    try:
        user_id = request.match_info['user_id']
        msg_id = request.match_info['msg_id']
        token = f"tok1_{user_id}_{msg_id}"
        html_page = SAME_PAGE_GATE_HTML.format(step="1", ad_url=PRIMARY_AD_LINK, bot_username=BOT_USERNAME, token=token)
        return web.Response(text=html_page, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"Gate Step 1 Error: {e}", status=500)

@routes.get("/gate/step2/{user_id}/{msg_id}")
async def gate_step2(request):
    try:
        user_id = request.match_info['user_id']
        msg_id = request.match_info['msg_id']
        token = f"tok2_{user_id}_{msg_id}"
        target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME
        html_page = SAME_PAGE_GATE_HTML.format(step="2", ad_url=PRIMARY_AD_LINK, bot_username=target_delivery_bot, token=token)
        return web.Response(text=html_page, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"Gate Step 2 Error: {e}", status=500)

@routes.post("/filebot_webhook")
async def file_bot_webhook_handler(request):
    try:
        data = await request.json()
        message = data.get("message", {})
        text = str(message.get("text", "")).strip()
        chat_id = message.get("chat", {}).get("id")

        if chat_id and text.startswith("/start"):
            parts = text.split(maxsplit=1)
            param = parts[1].strip() if len(parts) > 1 else ""

            if param.startswith("vipfile_"):
                mid = int(param.split("_")[1])
                doc = await files_col.find_one({"message_id": int(mid)})
                if not doc or not doc.get("is_posted"):
                    await send_file_bot_text(chat_id, "❌ <b>මෙම චිත්‍රපටය තවමත් Channels වෙත Publish කර නොමැත.</b>")
                    return web.Response(text="ok", status=200)

                await send_file_bot_text(chat_id, "👑 <b>VIP Direct File:</b> ගොනුව එවමින් පවතී...")
                asyncio.create_task(deliver_file_bot_movie(chat_id, mid, is_vip=True))

            elif param.startswith("tok2_"):
                mid = int(param.split("_")[2])
                doc = await files_col.find_one({"message_id": int(mid)})
                if not doc or not doc.get("is_posted"):
                    await send_file_bot_text(chat_id, "❌ <b>මෙම චිත්‍රපටය තවමත් Channels වෙත Publish කර නොමැත.</b>")
                    return web.Response(text="ok", status=200)

                await send_file_bot_text(chat_id, "🎉 <b>සත්‍යාපනය සාර්ථකයි!</b> මෙන්න ඔබගේ චිත්‍රපටය:")
                asyncio.create_task(deliver_file_bot_movie(chat_id, mid, is_vip=False))

            else:
                await send_file_bot_text(chat_id, f"👋 <b>Cinex LK File Delivery Service</b>\n\nචිත්‍රපට ලබාගැනීමට Main Channel එක හා සම්බන්ධ වන්න:\n📢 {MAIN_CHANNEL}")
    except Exception:
        pass
    return web.Response(text="ok", status=200)

# =========================================================
# TELEGRAM RAW HTTP HELPERS
# =========================================================
async def kick_user_from_vip_channel(user_id: int):
    url_ban = f"https://api.telegram.org/bot{BOT_TOKEN}/banChatMember"
    url_unban = f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember"
    payload = {"chat_id": str(VIP_CHANNEL_RAW), "user_id": int(user_id)}
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url_ban, json=payload, timeout=aiohttp.ClientTimeout(total=8))
            await asyncio.sleep(0.5)
            await session.post(url_unban, json=payload, timeout=aiohttp.ClientTimeout(total=8))
    except Exception:
        pass

    await vip_users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"expiry_date": datetime.utcnow() - timedelta(days=1)}}
    )

async def send_tg_photo_fileid(chat_id: str, file_id: str, caption_html: str, reply_markup: dict):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": str(chat_id),
        "photo": file_id,
        "caption": caption_html,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

async def send_tg_message(chat_id: str, text_html: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(chat_id), "text": text_html, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return await resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

# =========================================================
# BACKUP CHANNEL DYNAMIC INVITE LINK BUILDER
# =========================================================
async def get_backup_link():
    global CACHED_BACKUP_LINK
    if CACHED_BACKUP_LINK:
        return CACHED_BACKUP_LINK

    target = str(BACKUP_CHANNEL_RAW).strip()
    if not (target.startswith("-100") or target.startswith("-")):
        CACHED_BACKUP_LINK = f"https://t.me/{target.replace('@', '')}"
        return CACHED_BACKUP_LINK

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": target}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                res = await resp.json()
                if res.get("ok"):
                    CACHED_BACKUP_LINK = res["result"]["invite_link"]
                    return CACHED_BACKUP_LINK
    except Exception:
        pass

    return f"https://t.me/{str(MAIN_CHANNEL).replace('@', '')}"

# =========================================================
# ACCESS CONTROL
# =========================================================
async def is_vip_user(user_id: int) -> bool:
    try:
        doc = await vip_users_col.find_one({"user_id": int(user_id), "expiry_date": {"$gt": datetime.utcnow()}})
        return bool(doc)
    except Exception:
        return False

async def is_member(chat_target, user_id: int) -> bool:
    if not chat_target:
        return True
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": str(chat_target), "user_id": int(user_id)}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                res = await resp.json()
                if res.get("ok"):
                    status = str(res.get("result", {}).get("status", "")).lower()
                    return any(s in status for s in ["member", "administrator", "creator", "restricted"])
    except Exception:
        pass
    return False

async def check_access(user_id: int) -> bool:
    try:
        rec = await bot_users_col.find_one({"user_id": user_id})
        if rec and rec.get("fsub_verified"):
            return True
        in_main = await is_member(MAIN_CHANNEL, user_id)
        in_back = await is_member(BACKUP_CHANNEL, user_id)
        if in_main and in_back:
            await bot_users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "fsub_verified": True}}, upsert=True)
            return True
        return False
    except Exception:
        return True

async def get_fsub_markup(param: str = "") -> InlineKeyboardMarkup:
    btns = []
    if MAIN_CHANNEL:
        btns.append([InlineKeyboardButton("📢 Join Main Channel", url=f"https://t.me/{str(MAIN_CHANNEL).replace('@', '')}")])
    if BACKUP_CHANNEL:
        b_link = await get_backup_link()
        btns.append([InlineKeyboardButton("🛡️ Join Backup Channel", url=b_link)])
    btns.append([InlineKeyboardButton("🔄 Verify & Unlock", callback_data=f"verify_{param}" if param else "verify_root")])
    return InlineKeyboardMarkup(btns)

# =========================================================
# MOVIE CLEANER & OMDB METADATA
# =========================================================
def clean_movie_title(raw_name: str):
    name = os.path.splitext(raw_name)[0]
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    year = year_match.group(1) if year_match else None
    if year:
        name = name.replace(year, " ")

    name = re.sub(r"[\[\(\{].*?[\]\)\}]", " ", name)
    name = re.split(r"\b(1080p|720p|480p|2160p|4k|hdr|bluray|web-dl|webrip|brrip|dvdrip|x264|x265|hevc|aac|esub|cinexlk|hindi|tamil|sinhala|telugu|malayalam)\b", name, flags=re.IGNORECASE)[0]
    name = re.sub(r"[\._\-\+]+", " ", name)
    cleaned = " ".join(name.split()).strip()
    return cleaned if cleaned else raw_name.strip(), year

async def fetch_metadata(raw_name: str):
    title, year = clean_movie_title(raw_name)
    api_url = f"https://www.omdbapi.com/?t={urllib.parse.quote(title)}&y={year or ''}&apikey=trilogy"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("Response") == "True":
                        poster = data.get("Poster") if data.get("Poster") != "N/A" else None
                        return {
                            "title": data.get("Title", title.title()),
                            "year": data.get("Year", year or "N/A"),
                            "rating": data.get("imdbRating", "N/A"),
                            "genres": data.get("Genre", "Cinema"),
                            "language": data.get("Language", "English"),
                            "plot": data.get("Plot", "Directly uploaded to Cinex LK library."),
                            "poster": poster
                        }
    except Exception:
        pass
    return {"title": title.title(), "year": year or "N/A", "rating": "N/A", "genres": "Cinema", "language": "English", "plot": "Directly uploaded to Cinex LK library.", "poster": None}

# =========================================================
# CREATE PREVIEW POST IN STORAGE CHANNEL
# =========================================================
async def create_storage_preview(client: Client, message: Message):
    global BOT_USERNAME
    media = message.document or message.video
    if not media:
        return

    file_name = getattr(media, "file_name", None) or message.caption or "Movie"
    size_mb = round(media.file_size / (1024 * 1024), 2)
    msg_id = message.id

    if not BOT_USERNAME:
        me = await client.get_me()
        BOT_USERNAME = me.username

    await files_col.update_one(
        {"message_id": msg_id},
        {"$set": {"file_name": file_name, "file_size": media.file_size, "message_id": msg_id, "created_at": datetime.utcnow()}, "$setOnInsert": {"download_count": 0, "is_posted": False, "posted_main": False, "posted_vip": False}},
        upsert=True
    )

    meta = await fetch_metadata(file_name)
    rating_str = f"{meta['rating']} / 10" if meta['rating'] != "N/A" else "N/A"

    safe_title = html.escape(str(meta['title']))
    safe_year = html.escape(str(meta['year']))
    safe_genres = html.escape(str(meta['genres']))
    safe_language = html.escape(str(meta.get('language', 'English')))
    safe_plot = html.escape(str(meta['plot'])[:250])

    caption = (
        f"🎬 <b>{safe_title} ({safe_year})</b>\n\n"
        f"⭐ <b>IMDb Rating:</b> <code>{rating_str}</code>\n"
        f"🎭 <b>Genres:</b> <code>{safe_genres}</code>\n"
        f"🌐 <b>Language:</b> <code>{safe_language}</code>\n"
        f"📦 <b>Size:</b> <code>{size_mb} MB</code>\n\n"
        f"📖 <b>Plot:</b> {safe_plot}...\n\n"
        "👇 <b>චිත්‍රපටය ලබාගැනීමට පහත Button එක ඔබන්න:</b>"
    )

    poster_url = meta.get("poster") if (meta.get("poster") and meta["poster"].startswith("http")) else DEFAULT_POSTER

    preview_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Post to Main Channel", callback_data=f"post_main_{msg_id}")],
        [InlineKeyboardButton("👑 Post to VIP Channel", callback_data=f"post_vip_{msg_id}")]
    ])

    try:
        await client.send_photo(chat_id=message.chat.id, photo=poster_url, caption=caption, reply_markup=preview_markup)
    except Exception:
        await client.send_message(chat_id=message.chat.id, text=caption, reply_markup=preview_markup)
    print(f"✅ Generated Control Preview for: {file_name}")

# =========================================================
# UNIVERSAL MESSAGE DISPATCHER (MAIN BOT)
# =========================================================
@app.on_message()
async def universal_message_handler(client: Client, message: Message):
    if not message.chat:
        return

    if message.from_user and message.from_user.is_bot:
        return

    chat_clean = str(message.chat.id).replace("-100", "").replace("-", "")

    if chat_clean == STORAGE_CLEAN or str(message.chat.id) == str(STORAGE_CHANNEL_RAW):
        if message.document or message.video:
            asyncio.create_task(create_storage_preview(client, message))
        return

    chat_type_val = str(getattr(message.chat.type, "value", message.chat.type)).lower()
    if "private" in chat_type_val:
        text = (message.text or "").strip()
        user_id = message.from_user.id if message.from_user else 0
        target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME

        if text == "/stats":
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            
            total_movies = await files_col.count_documents({})
            posted_movies = await files_col.count_documents({"is_posted": True})
            total_vip = await vip_users_col.count_documents({"expiry_date": {"$gt": datetime.utcnow()}})
            
            pipeline = [{"$group": {"_id": None, "total_downloads": {"$sum": "$download_count"}}}]
            agg = await files_col.aggregate(pipeline).to_list(length=1)
            total_dl = agg[0]["total_downloads"] if agg else 0

            stats_msg = (
                "📊 <b>Cinex LK Storage & Bot Statistics:</b>\n\n"
                f"📦 <b>Total Storage Files:</b> <code>{total_movies}</code>\n"
                f"🎬 <b>Live Published Movies:</b> <code>{posted_movies}</code>\n"
                f"📥 <b>Total Downloads:</b> <code>{total_dl}</code>\n"
                f"👑 <b>Active VIP Members:</b> <code>{total_vip}</code>\n\n"
                f"📦 <i>Storage ID:</i> <code>{STORAGE_CHANNEL_RAW}</code>"
            )
            await message.reply_text(stats_msg)
            return

        if text == "/resetallcatalog":
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            res = await files_col.update_many(
                {},
                {"$set": {"is_posted": False, "posted_main": False, "posted_vip": False}}
            )
            await message.reply_text(
                f"🧹 <b>සම්පූර්ණ Catalog Reset එක සාර්ථකයි!</b>\n\n"
                f"Database Movies <code>{res.modified_count}</code>ම Catalog එකෙන් ඉවත් කරන ලදී."
            )
            return

        if text.startswith("/publishrange"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()
            if len(args) < 3:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/publishrange &lt;START_ID&gt; &lt;END_ID&gt;</code>\nඋදා: <code>/publishrange 64 220</code>")
                return
            try:
                start_id = int(args[1].strip())
                end_id = int(args[2].strip())
            except ValueError:
                await message.reply_text("❌ වලංගු Message ID අංක ලබා දෙන්න.")
                return

            res = await files_col.update_many(
                {"message_id": {"$gte": start_id, "$lte": end_id}},
                {"$set": {"is_posted": True, "posted_main": True, "posted_vip": True}}
            )
            await message.reply_text(f"✅ සාර්ථකයි! ID <code>{start_id}</code> සිට <code>{end_id}</code> දක්වා Movies <code>{res.modified_count}</code>ක් Catalog එකට Publish කරන ලදී.")
            return

        if text.startswith("/publish") and not text.startswith("/publishrange"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()[1:]
            if not args:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/publish &lt;ID&gt;</code>")
                return

            ids = [int(a) for a in args if a.isdigit()]
            if not ids:
                await message.reply_text("❌ වලංගු Message ID හමු නොවීය.")
                return

            res = await files_col.update_many(
                {"message_id": {"$in": ids}},
                {"$set": {"is_posted": True, "posted_main": True, "posted_vip": True}}
            )
            await message.reply_text(f"✅ සාර්ථකයි! Movies <code>{res.modified_count}</code>ක් Catalog එකට Add කරන ලදී.")
            return

        if text.startswith("/unpublish"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()[1:]
            if not args:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/unpublish &lt;Message_ID&gt;</code>")
                return
            ids = [int(a) for a in args if a.isdigit()]
            res = await files_col.update_many(
                {"message_id": {"$in": ids}},
                {"$set": {"is_posted": False, "posted_main": False, "posted_vip": False}}
            )
            await message.reply_text(f"🚫 Movies <code>{res.modified_count}</code>ක් Catalog එකෙන් ඉවත් කරන ලදී.")
            return

        if text in ["/movies", "/list"]:
            catalog_text, catalog_markup = await get_movies_page(page=1, user_id=user_id)
            await message.reply_text(catalog_text, reply_markup=catalog_markup)
            return

        if text == "/storage":
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return

            total_movies = await files_col.count_documents({})
            if total_movies == 0:
                await message.reply_text("📂 <b>Storage Database එකෙහි Movies කිසිවක් හමු නොවීය.</b>")
                return

            recent_cursor = files_col.find({}).sort("_id", -1).limit(30)
            recent_movies = await recent_cursor.to_list(length=30)

            list_text = f"📂 <b>Storage Files List (Total: {total_movies} Movies)</b>\n\n"
            for idx, doc in enumerate(recent_movies, 1):
                clean_t = clean_movie_title(doc.get("file_name", "Movie"))[0]
                mid = doc.get("message_id")
                dl_count = doc.get("download_count", 0)
                is_p = "✅ Live" if doc.get("is_posted") else "❌ Storage Only"
                list_text += f"{idx}. [{is_p}] <b>{html.escape(clean_t[:25])}</b> (ID: <code>{mid}</code> | 📥 {dl_count})\n"

            if total_movies > 30:
                list_text += f"\n<i>...සහ තවත් චිත්‍රපට {total_movies - 30}ක් ඇත.</i>"

            await message.reply_text(list_text)
            return

        if text == "/viplist":
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return

            now = datetime.utcnow()
            active_vips = await vip_users_col.find({"expiry_date": {"$gt": now}}).sort("expiry_date", 1).to_list(length=100)

            if not active_vips:
                await message.reply_text("👑 <b>දැනට Active VIP සාමාජිකයන් කිසිවෙකු නොමැත.</b>")
                return

            vip_text = f"👑 <b>Active VIP Members List (Total: {len(active_vips)})</b>\n\n"
            kick_buttons = []

            for idx, v in enumerate(active_vips, 1):
                v_uid = v.get("user_id")
                joined_at = v.get("joined_at")
                expiry_date = v.get("expiry_date")

                joined_str = joined_at.strftime("%Y-%m-%d") if isinstance(joined_at, datetime) else "N/A"
                expiry_str = expiry_date.strftime("%Y-%m-%d") if isinstance(expiry_date, datetime) else "N/A"
                rem_days = (expiry_date - now).days if isinstance(expiry_date, datetime) else 0

                vip_text += (
                    f"{idx}. 👤 <b>User ID:</b> <code>{v_uid}</code>\n"
                    f"   📅 <b>Joined:</b> <code>{joined_str}</code>\n"
                    f"   ⏳ <b>Expires:</b> <code>{expiry_str}</code> (<b>{rem_days} Days Left</b>)\n\n"
                )
                kick_buttons.append([InlineKeyboardButton(f"🚫 Kick out {v_uid}", callback_data=f"kick_{v_uid}")])

            await message.reply_text(vip_text, reply_markup=InlineKeyboardMarkup(kick_buttons))
            return

        if text.startswith("/kickvip"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()
            if len(args) < 2:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/kickvip &lt;USER_ID&gt;</code>")
                return
            try:
                target_uid = int(args[1].strip())
            except ValueError:
                await message.reply_text("❌ වැරදි User ID එකකි.")
                return

            await kick_user_from_vip_channel(target_uid)
            await message.reply_text(f"✅ User <code>{target_uid}</code> VIP Channel එකෙන් Kick කර VIP සාමාජිකත්වය අවලංගු කරන ලදී.")
            return

        if text.startswith("/addvip"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()
            if len(args) < 2:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/addvip &lt;USER_ID&gt; [දින ගණන]</code>\nඋදා: <code>/addvip 123456789 1</code> හෝ <code>/addvip 123456789 30</code>")
                return
            try:
                target_user_id = int(args[1].strip())
            except ValueError:
                await message.reply_text("❌ වැරදි User ID එකකි.")
                return

            days_to_add = 30
            if len(args) >= 3 and args[2].isdigit():
                days_to_add = int(args[2].strip())

            now = datetime.utcnow()
            expiry_date = now + timedelta(days=days_to_add)
            await vip_users_col.update_one(
                {"user_id": target_user_id},
                {"$set": {
                    "user_id": target_user_id,
                    "expiry_date": expiry_date,
                    "joined_at": now,
                    "initial_days": days_to_add,
                    "is_kicked": False,
                    "reminded_3d": False
                }},
                upsert=True
            )
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
                payload = {"chat_id": str(VIP_CHANNEL_RAW), "member_limit": 1}
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        res = await resp.json()
                        if res.get("ok"):
                            link = res["result"]["invite_link"]
                            await client.send_message(
                                chat_id=target_user_id,
                                text=f"🎉 <b>ඔබගේ VIP සාමාජිකත්වය දින {days_to_add}කට සක්‍රිය විය!</b>\n\n🔗 VIP Channel Link:\n{link}"
                            )
                            await message.reply_text(f"✅ User <code>{target_user_id}</code> වෙත දින {days_to_add}ක VIP සක්‍රිය කරන ලදී.\n📅 Expiry: <code>{expiry_date.strftime('%Y-%m-%d')}</code>")
                            return
                await message.reply_text("⚠️ Invite Link එක සෑදීම අසාර්ථක විය.")
            except Exception as e:
                await message.reply_text(f"⚠️ Invite Error: {e}")
            return

        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            param = parts[1].strip() if len(parts) > 1 else ""

            if param in ["buyvip", "vip"]:
                vip_text, vip_markup = get_vip_selection_menu()
                await message.reply_text(vip_text, reply_markup=vip_markup)
                return

            if param.startswith("vipfile_"):
                mid = param.split("_")[1]
                doc = await files_col.find_one({"message_id": int(mid)})
                if not doc or not doc.get("is_posted"):
                    await message.reply_text("❌ <b>මෙම චිත්‍රපටය තවමත් Channels වෙත Publish කර නොමැත.</b>")
                    return

                dl_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Download Movie File (Click Here)", url=f"https://t.me/{target_delivery_bot}?start=vipfile_{mid}")]
                ])
                await message.reply_text("👑 <b>Cinex LK VIP Direct File:</b>\n\nචිත්‍රපටය ලබාගැනීමට පහත Button එක ඔබන්න 👇", reply_markup=dl_btn)
                return

            if param.startswith("tok1_"):
                mid = param.split("_")[2]
                step2_url = f"{BASE_URL}/gate/step2/{user_id}/{mid}" if BASE_URL else PRIMARY_AD_LINK
                await message.reply_text(
                    "🎉 <b>Step 1 සාර්ථකයි!</b>\n\nඅවසන් පියවර ලෙස පහත Sponsor Link එක විවෘත කරන්න:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Open Sponsor Link 2", url=step2_url)]])
                )
                return

            if param.startswith("tok2_"):
                mid = param.split("_")[2]
                doc = await files_col.find_one({"message_id": int(mid)})
                if not doc or not doc.get("is_posted"):
                    await message.reply_text("❌ <b>මෙම චිත්‍රපටය තවමත් Channels වෙත Publish කර නොමැත.</b>")
                    return

                dl_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Get Movie File (Click Here)", url=f"https://t.me/{target_delivery_bot}?start=tok2_{mid}")]
                ])
                await message.reply_text("🎉 <b>සත්‍යාපනය සාර්ථකයි!</b>\n\nචිත්‍රපටය ලබාගැනීමට පහත Button එක ඔබන්න 👇", reply_markup=dl_btn)
                return

            if not await check_access(user_id):
                await message.reply_text(
                    "🔒 <b>චිත්‍රපට ලබාගැනීමට පෙර කරුණාකර පහත Channels දෙකටම Join වී Verify ඔබන්න:</b>",
                    reply_markup=await get_fsub_markup(param)
                )
                return

            if param.startswith("adstep1_"):
                mid = param.split("_")[1]
                doc = await files_col.find_one({"message_id": int(mid)})
                if not doc or not doc.get("is_posted"):
                    await message.reply_text("❌ <b>මෙම චිත්‍රපටය තවමත් Channels වෙත Publish කර නොමැත.</b>")
                    return

                step1_url = f"{BASE_URL}/gate/step1/{user_id}/{mid}" if BASE_URL else PRIMARY_AD_LINK
                await message.reply_text(
                    "🎬 <b>Download Verification (Step 1 of 2):</b>\n\nනොමිලේ ලබාගැනීමට පහත Sponsor Link එක විවෘත කර තත්පර 8ක් රැඳී සිටින්න:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Open Sponsor Link 1", url=step1_url)]])
                )
                return

            welcome_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 All Movies List (චිත්‍රපට නාමාවලිය)", callback_data="show_movies_list")],
                [InlineKeyboardButton("👑 Buy VIP Membership", callback_data="show_vip_menu")]
            ])

            welcome_text = (
                "👋 <b>සාදරයෙන් පිළිගන්නවා Cinex LK වෙත!</b>\n\n"
                "📌 <b>ප්‍රධාන පහසුකම්:</b>\n"
                "• 🎬 <b>Movies List එක බැලීමට:</b> <code>/movies</code>\n"
                "• 📩 <b>Movie එකක් ඉල්ලීමට:</b> <code>/req &lt;Movie Name&gt;</code> (හෝ නම එවන්න)\n"
                "• 👑 <b>VIP සාමාජිකත්වය:</b> <code>/start vip</code>\n\n"
                f"📢 නිල Channel එක: {MAIN_CHANNEL}"
            )
            await message.reply_text(welcome_text, reply_markup=welcome_markup)
            return

        req_movie = ""
        if text.startswith("/req"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                req_movie = parts[1].strip()
            else:
                await message.reply_text("❌ <b>කරුණාකර චිත්‍රපටයේ නම ඇතුළත් කරන්න.</b>\nඋදා: <code>/req Avatar 2</code>")
                return
        elif not text.startswith("/"):
            req_movie = text

        if req_movie:
            user_full = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            user_handle = f"@{message.from_user.username}" if message.from_user.username else "No Username"
            is_vip = await is_vip_user(user_id)
            vip_tag = "👑 VIP MEMBER" if is_vip else "👤 Regular User"

            if ADMIN_USER_ID:
                admin_alert = (
                    "📩 <b>නව Movie Request එකක් ලැබුණා!</b>\n\n"
                    f"🎬 <b>Movie:</b> <code>{html.escape(req_movie)}</code>\n"
                    f"👤 <b>User:</b> {html.escape(user_full)} ({user_handle})\n"
                    f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🎖️ <b>Status:</b> <b>{vip_tag}</b>"
                )
                try:
                    await client.send_message(chat_id=ADMIN_USER_ID, text=admin_alert)
                except Exception:
                    pass

            resp_text = (
                f"✅ <b>ඔබගේ Request එක Admin වෙත යොමු කරන ලදී!</b>\n\n"
                f"🎬 <b>චිත්‍රපටය:</b> <code>{html.escape(req_movie)}</code>\n\n"
                "කඩිනමින් අපගේ Main සහ VIP Channels වෙත මෙය Upload කරනු ඇත. රැඳී සිටින්න!"
            )
            await message.reply_text(resp_text)
            return

# =========================================================
# CALLBACK HANDLER
# =========================================================
@app.on_callback_query()
async def global_callback_handler(client: Client, callback: CallbackQuery):
    global BOT_USERNAME
    data = callback.data
    user_id = callback.from_user.id
    target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME

    if not BOT_USERNAME:
        me = await client.get_me()
        BOT_USERNAME = me.username

    if data == "show_movies_list":
        await callback.answer()
        c_text, c_markup = await get_movies_page(page=1, user_id=user_id)
        await callback.message.reply_text(c_text, reply_markup=c_markup)
        return

    if data == "show_vip_menu":
        await callback.answer()
        vip_text, vip_markup = get_vip_selection_menu()
        await callback.message.reply_text(vip_text, reply_markup=vip_markup)
        return

    if data.startswith("page_"):
        await callback.answer()
        try:
            req_page = int(data.replace("page_", ""))
            c_text, c_markup = await get_movies_page(page=req_page, user_id=user_id)
            await callback.message.edit_text(c_text, reply_markup=c_markup)
        except Exception:
            pass
        return

    if data == "pages_info":
        await callback.answer("📄 අදාළ Movie අංකය උඩ click කර ලබාගන්න.", show_alert=False)
        return

    if data.startswith("kick_"):
        if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
            await callback.answer("❌ ඔබට මෙම ක්‍රියාව කිරීමට අවසර නැත.", show_alert=True)
            return

        target_uid = int(data.replace("kick_", ""))
        await kick_user_from_vip_channel(target_uid)
        await callback.answer(f"✅ User {target_uid} සාර්ථකව Kick කරන ලදී!", show_alert=True)
        try:
            await callback.message.edit_text(
                f"{callback.message.text}\n\n<b>🚫 [Kick Status]</b> <code>{target_uid}</code> ඉවත් කරන ලදී."
            )
        except Exception:
            pass
        return

    if data.startswith("post_main_"):
        msg_id = int(data.replace("post_main_", ""))
        caption = callback.message.caption or callback.message.text or ""

        main_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Fast Download (Free)", url=f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}")],
            [InlineKeyboardButton("👑 Buy VIP Pass (No Ads)", url=f"https://t.me/{BOT_USERNAME}?start=buyvip")]
        ])

        target = MAIN_CHANNEL
        try:
            if callback.message.photo:
                await client.send_photo(chat_id=target, photo=callback.message.photo.file_id, caption=caption, reply_markup=main_markup)
            else:
                await client.send_message(chat_id=target, text=caption, reply_markup=main_markup)
            
            await files_col.update_one({"message_id": msg_id}, {"$set": {"is_posted": True, "posted_main": True}})

            await callback.answer("✅ Main Channel එකට සාර්ථකව Post කරන ලදී!", show_alert=True)

            try:
                current_keyboard = callback.message.reply_markup.inline_keyboard
                new_keyboard = []
                for row in current_keyboard:
                    new_row = []
                    for btn in row:
                        if btn.callback_data == f"post_main_{msg_id}":
                            new_row.append(InlineKeyboardButton("✅ Posted to Main (Re-post)", callback_data=f"post_main_{msg_id}"))
                        else:
                            new_row.append(btn)
                    new_keyboard.append(new_row)
                await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
            except Exception:
                pass

        except Exception as e:
            await callback.answer(f"❌ Main Fail: {str(e)[:100]}", show_alert=True)
        return

    if data.startswith("post_vip_"):
        msg_id = int(data.replace("post_vip_", ""))
        caption = callback.message.caption or callback.message.text or ""

        clean_caption = re.sub(r"👇.*", "", caption, flags=re.DOTALL).strip()
        vip_caption = f"{clean_caption}\n\n👑 <b>VIP Direct File:</b> දැන්වීම් නොමැතිව download කරගන්න 👇"

        vip_markup = {
            "inline_keyboard": [
                [{"text": "⚡ Instant Download (Direct File)", "url": f"https://t.me/{target_delivery_bot}?start=vipfile_{msg_id}"}]
            ]
        }

        target_vip = str(VIP_CHANNEL_RAW).strip()
        sent = False
        err_desc = ""

        if callback.message.photo:
            res = await send_tg_photo_fileid(target_vip, callback.message.photo.file_id, vip_caption, vip_markup)
            if res.get("ok"):
                sent = True
            else:
                err_desc = res.get("description", "")

        if not sent:
            res = await send_tg_message(target_vip, vip_caption, vip_markup)
            if res.get("ok"):
                sent = True
            else:
                if not err_desc:
                    err_desc = res.get("description", "")

        if sent:
            await files_col.update_one({"message_id": msg_id}, {"$set": {"is_posted": True, "posted_vip": True}})

            await callback.answer("✅ VIP Channel එකට සාර්ථකව Post කරන ලදී!", show_alert=True)

            try:
                current_keyboard = callback.message.reply_markup.inline_keyboard
                new_keyboard = []
                for row in current_keyboard:
                    new_row = []
                    for btn in row:
                        if btn.callback_data == f"post_vip_{msg_id}":
                            new_row.append(InlineKeyboardButton("✅ Posted to VIP (Re-post)", callback_data=f"post_vip_{msg_id}"))
                        else:
                            new_row.append(btn)
                    new_keyboard.append(new_row)
                await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
            except Exception:
                pass

        else:
            await callback.answer(f"❌ VIP Fail: {err_desc[:100]}", show_alert=True)
        return

    if data.startswith("verify_"):
        await callback.answer()
        param = data.replace("verify_", "")
        if await check_access(user_id):
            await callback.message.delete()
            if param and param != "root":
                if param.startswith("adstep1_"):
                    mid = param.split("_")[1]
                    step1_url = f"{BASE_URL}/gate/step1/{user_id}/{mid}" if BASE_URL else PRIMARY_AD_LINK
                    await client.send_message(user_id, "🎬 <b>Step 1 of 2:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Open Sponsor Link 1", url=step1_url)]]))
                elif param in ["buyvip", "vip"]:
                    vip_text, vip_markup = get_vip_selection_menu()
                    await client.send_message(user_id, vip_text, reply_markup=vip_markup)
            else:
                await client.send_message(user_id, "👋 ඔබට අවශ්‍ය Movie එකේ නම type කර Search කරන්න. නාමාවලිය සඳහා: /movies")
        else:
            await callback.answer("❌ කරුණාකර Channels 2ටම Join වී නැවත Verify ඔබන්න.", show_alert=True)
        return

    if data.startswith("buyplan_"):
        await callback.answer()
        plan_key = data.replace("buyplan_", "")
        plan = VIP_PLANS.get(plan_key, VIP_PLANS["1m"])

        price = plan["price"]
        label = plan["label"]
        days = plan["days"]

        ref = f"CX-{random.randint(10000, 99999)}"
        username = f"@{callback.from_user.username}" if callback.from_user.username else "No Username"
        full_name = f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip()

        await manual_orders_col.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "username": username,
                "name": full_name,
                "ref_code": ref,
                "plan": label,
                "days": days,
                "amount": price,
                "status": "pending",
                "created_at": datetime.utcnow()
            }},
            upsert=True
        )

        if ADMIN_USER_ID:
            admin_alert = (
                "🔔 <b>නව VIP Payment ඉල්ලීමක්!</b>\n\n"
                f"👤 <b>පරිශීලකයා:</b> {html.escape(full_name)} ({username})\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                f"📦 <b>තෝරාගත් Plan එක:</b> <b>{label} ({days} Day{'s' if days > 1 else ''})</b>\n"
                f"💰 <b>ගෙවිය යුතු මුදල:</b> <code>Rs. {price}</code>\n"
                f"🔑 <b>Reference Code:</b> <code>{ref}</code>\n\n"
                f"📌 <i>User slip එක එවූ පසු VIP දීමට:</i>\n<code>/addvip {user_id} {days}</code>"
            )
            try:
                await client.send_message(chat_id=ADMIN_USER_ID, text=admin_alert)
            except Exception:
                pass

        admin_link = f"https://t.me/{ADMIN_USERNAME}" if ADMIN_USERNAME else None
        text = (
            f"👑 <b>Cinex LK VIP Pass - {label}</b>\n\n"
            f"💰 <b>ගෙවිය යුතු මුදල:</b> <code>Rs. {price}</code>\n\n"
            f"{BANK_DETAILS}\n\n"
            f"⚠️ <b>අනිවාර්යයි (Very Important):</b>\n"
            f"මුදල් තැන්පත් කරන විට Reference/Remarks සඳහා පහත ඔබගේ Unique Code එක ඇතුළත් කරන්න:\n"
            f"🔑 <b>ඔබගේ Reference Code එක:</b> <code>{ref}</code>\n\n"
            f"📸 මුදල් ගෙවූ පසු Payment Slip හෝ Screenshot එක ඔබගේ User ID (<code>{user_id}</code>) සමඟ Admin වෙත එවන්න."
        )
        btns = [[InlineKeyboardButton("📩 Send Slip to Admin", url=admin_link)]] if admin_link else []
        await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns) if btns else None)
        return

# =========================================================
# SERVER INIT & RUNNER
# =========================================================
async def setup_file_bot_webhook():
    if FILE_BOT_TOKEN and BASE_URL:
        webhook_url = f"{BASE_URL}/filebot_webhook"
        set_url = f"https://api.telegram.org/bot{FILE_BOT_TOKEN}/setWebhook?url={webhook_url}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(set_url) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        print(f"🔗 File Bot Webhook Linked: {webhook_url}", flush=True)
                    else:
                        print(f"⚠️ Webhook Warning: {data.get('description')}", flush=True)
        except Exception as e:
            print(f"Webhook Exception: {e}", flush=True)

async def main():
    global BOT_USERNAME
    await app.start()
    me = await app.get_me()
    BOT_USERNAME = me.username
    print(f"🤖 Cinex LK Super-Control Bot Live as @{BOT_USERNAME}", flush=True)

    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web Engine Live on port {PORT}", flush=True)

    await setup_file_bot_webhook()

    asyncio.create_task(auto_kick_expired_vips())

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
