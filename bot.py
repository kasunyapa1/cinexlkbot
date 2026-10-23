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

VIP_STAR_PRICE = int(os.environ.get("VIP_STAR_PRICE", "250"))
VIP_LKR_PRICE = int(os.environ.get("VIP_LKR_PRICE", "1000"))
SINGLE_STAR_PRICE = int(os.environ.get("SINGLE_STAR_PRICE", "5"))

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

# Active Pyrogram Client (Main Bot Only)
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
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                pass
    except Exception:
        pass

async def auto_delete_file_task(chat_id: int, msg_ids: list, delay: int):
    await asyncio.sleep(delay)
    await delete_file_bot_messages(chat_id, msg_ids)
    await send_file_bot_text(chat_id, "🗑️ <b>ප්‍රකාශන හිමිකම් ආරක්ෂාව මත චිත්‍රපටය Chat එකෙන් ඉවත් කරන ලදී.</b>")

async def deliver_file_bot_movie(chat_id: int, message_id: int, is_vip: bool = False):
    delay = VIP_USER_DELETE_DURATION if is_vip else FREE_USER_DELETE_DURATION
    time_label = "පැය 24කින්" if is_vip else "පැය 12කින්"

    try:
        await files_col.update_one({"message_id": int(message_id)}, {"$inc": {"download_count": 1}})
    except Exception:
        pass

    warn_text = (
        "⚡ <b>Cinex LK Delivery:</b>\n\n"
        f"⚠️ මෙම චිත්‍රපටය තවත් <b>{time_label}</b> Chat එකෙන් ඉවත් වේ.\n"
        "📥 Device එකට Save කරගැනීමට වීඩියෝවේ Menu එකෙන් <b>'Save to Downloads'</b> දෙන්න.\n"
        "<i>(Save කළ පසු Chat එකෙන් මැකුණද ඔබගේ Phone එකෙහි සුරක්ෂිතව පවතී)</i>"
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
                    await send_file_bot_text(chat_id, "❌ <b>මෙම චිත්‍රපටය Storage එකෙන් ඉවත් කර ඇත.</b>")
    except Exception as e:
        await send_file_bot_text(chat_id, f"❌ Delivery Error: {e}")
    return False

# =========================================================
# WEB SERVER, AD GATE & FILE BOT WEBHOOK
# =========================================================
routes = web.RouteTableDef()

SAME_PAGE_GATE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sponsor Verification - Cinex LK</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; }}
        body, html {{ margin:0; padding:0; height:100%; overflow:hidden; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#0b1118; color:white; }}
        #header-bar {{ height:75px; background:#16222f; border-bottom:2px solid #233446; display:flex; align-items:center; justify-content:space-between; padding:0 15px; position:fixed; top:0; left:0; right:0; z-index:9999; box-shadow:0 4px 15px rgba(0,0,0,0.5); }}
        .step-label {{ font-size:12px; font-weight:bold; color:#5da9e9; letter-spacing:1px; }}
        .countdown-wrap {{ display:flex; align-items:center; gap:8px; }}
        .count-circle {{ width:42px; height:42px; border-radius:50%; border:3px solid #5da9e9; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:18px; color:#5da9e9; background:#0b1118; }}
        .btn {{ display:none; background:#2fa955; color:white; text-decoration:none; padding:10px 18px; border-radius:10px; font-weight:bold; font-size:14px; transition:0.2s; white-space:nowrap; }}
        .btn:hover {{ background:#268d46; }}
        #ad-frame {{ width:100%; height:calc(100% - 75px); margin-top:75px; border:none; }}
    </style>
</head>
<body>
    <div id="header-bar">
        <div>
            <div class="step-label">STEP {step} OF 2</div>
            <div style="font-size:13px; color:#cfd8dc;" id="status-text">Ad එක නරඹමින් තත්පර 8ක් රැඳී සිටින්න...</div>
        </div>
        <div class="countdown-wrap">
            <div class="count-circle" id="count">8</div>
            <a id="doneBtn" class="btn" href="https://t.me/{bot_username}?start={token}">✅ Go to Telegram</a>
        </div>
    </div>
    <iframe id="ad-frame" src="{ad_url}" sandbox="allow-forms allow-scripts allow-same-origin allow-popups"></iframe>
    <script>
        let sec = 8;
        const timer = setInterval(() => {{
            sec--;
            document.getElementById('count').innerText = sec;
            if (sec <= 0) {{
                clearInterval(timer);
                document.getElementById('count').style.display = 'none';
                document.getElementById('status-text').innerText = '🎉 සත්‍යාපනය සාර්ථකයි!';
                document.getElementById('doneBtn').style.display = 'block';
            }}
        }}, 1000);
    </script>
</body>
</html>
"""

@routes.get("/")
async def root_ping(request):
    return web.Response(text="Cinex LK Hybrid Engine Alive", status=200)

@routes.get("/gate/step1/{user_id}/{msg_id}")
async def gate_step1(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok1_{user_id}_{msg_id}"
    html_page = SAME_PAGE_GATE_HTML.format(step="1", ad_url=PRIMARY_AD_LINK, bot_username=BOT_USERNAME, token=token)
    return web.Response(text=html_page, content_type='text/html')

@routes.get("/gate/step2/{user_id}/{msg_id}")
async def gate_step2(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok2_{user_id}_{msg_id}"
    target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME
    html_page = SAME_PAGE_GATE_HTML.format(step="2", ad_url=PRIMARY_AD_LINK, bot_username=target_delivery_bot, token=token)
    return web.Response(text=html_page, content_type='text/html')

# Webhook for File Delivery Bot
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
                await send_file_bot_text(chat_id, "👑 <b>VIP Direct File:</b> ගොනුව එවමින් පවතී...")
                asyncio.create_task(deliver_file_bot_movie(chat_id, mid, is_vip=True))

            elif param.startswith("tok2_"):
                mid = int(param.split("_")[2])
                await send_file_bot_text(chat_id, "🎉 <b>සත්‍යාපනය සාර්ථකයි!</b> මෙන්න ඔබගේ චිත්‍රපටය:")
                asyncio.create_task(deliver_file_bot_movie(chat_id, mid, is_vip=False))

            else:
                await send_file_bot_text(chat_id, f"👋 <b>Cinex LK File Delivery Service</b>\n\nචිත්‍රපට ලබාගැනීමට Main Channel එක හා සම්බන්ධ වන්න:\n📢 {MAIN_CHANNEL}")
    except Exception:
        pass
    return web.Response(text="ok", status=200)

# =========================================================
# TELEGRAM RAW HTTP HELPERS & KICK LOGIC
# =========================================================
async def kick_user_from_vip_channel(user_id: int):
    # 1. Ban & Unban quickly to remove user from private broadcast channel
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

    # 2. Expire in Database immediately
    await vip_users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"expiry_date": datetime.utcnow() - timedelta(days=1)}}
    )

async def send_tg_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
    body = {
        "chat_id": int(chat_id),
        "title": str(title)[:32],
        "description": str(description)[:255],
        "payload": str(payload),
        "currency": "XTR",
        "prices": json.dumps([{"label": str(title)[:30], "amount": int(stars)}]),
        "provider_token": ""
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                res = await resp.json()
                return res.get("ok", False), res.get("description", "")
    except Exception as e:
        return False, str(e)

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

def get_vip_options_markup():
    approx_lkr = int(VIP_STAR_PRICE * 6.8)
    savings = max(0, approx_lkr - VIP_LKR_PRICE)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ Pay with Telegram Stars ({VIP_STAR_PRICE} ⭐️ / ~Rs. {approx_lkr})", callback_data="pay_vip_stars")],
        [InlineKeyboardButton(f"🇱🇰 Bank Transfer - Rs. {VIP_LKR_PRICE} (Save Rs. {savings} 🔥)", callback_data="pay_vip_bank")]
    ])

VIP_DETAILS_TEXT = (
    "👑 <b>Cinex LK VIP Pass (Monthly - 30 Days)</b>\n\n"
    "✨ <b>VIP සාමාජිකත්වයේ වාසි:</b>\n"
    "• කිසිදු දැන්වීමක් නොමැත (100% No Ads Direct Files)\n"
    "• Direct Files ක්ෂණිකව ලබාගත හැක\n"
    "• VIP Channel එකට දින 30ක අඛණ්ඩ ප්‍රවේශය\n"
    "• පැය 24ක Auto-Delete කාලයක් හිමිවීම\n\n"
    "👇 <b>ගෙවීම් කිරීමට කැමති ආකාරය තෝරන්න:</b>"
)

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
                            "plot": data.get("Plot", "Directly uploaded to Cinex LK library."),
                            "poster": poster
                        }
    except Exception:
        pass
    return {"title": title.title(), "year": year or "N/A", "rating": "N/A", "genres": "Cinema", "plot": "Directly uploaded to Cinex LK library.", "poster": None}

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
        {"$set": {"file_name": file_name, "file_size": media.file_size, "message_id": msg_id, "created_at": datetime.utcnow()}, "$setOnInsert": {"download_count": 0}},
        upsert=True
    )

    meta = await fetch_metadata(file_name)
    rating_str = f"{meta['rating']} / 10" if meta['rating'] != "N/A" else "N/A"

    safe_title = html.escape(str(meta['title']))
    safe_year = html.escape(str(meta['year']))
    safe_genres = html.escape(str(meta['genres']))
    safe_plot = html.escape(str(meta['plot'])[:250])

    caption = (
        f"🎬 <b>{safe_title} ({safe_year})</b>\n\n"
        f"⭐ <b>IMDb Rating:</b> <code>{rating_str}</code>\n"
        f"🎭 <b>Genres:</b> <code>{safe_genres}</code>\n"
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

    chat_clean = str(message.chat.id).replace("-100", "").replace("-", "")

    # 1. Storage Channel Uploads
    if chat_clean == STORAGE_CLEAN or str(message.chat.id) == str(STORAGE_CHANNEL_RAW):
        if message.document or message.video:
            asyncio.create_task(create_storage_preview(client, message))
        return

    # 2. Private Chats
    chat_type_val = str(getattr(message.chat.type, "value", message.chat.type)).lower()
    if "private" in chat_type_val:
        text = message.text or ""
        user_id = message.from_user.id if message.from_user else 0
        target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME

        # /stats Command (ADMIN ONLY)
        if text == "/stats":
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            
            total_movies = await files_col.count_documents({})
            total_vip = await vip_users_col.count_documents({"expiry_date": {"$gt": datetime.utcnow()}})
            
            pipeline = [{"$group": {"_id": None, "total_downloads": {"$sum": "$download_count"}}}]
            agg = await files_col.aggregate(pipeline).to_list(length=1)
            total_dl = agg[0]["total_downloads"] if agg else 0

            stats_msg = (
                "📊 <b>Cinex LK Storage & Bot Statistics:</b>\n\n"
                f"🎬 <b>Total Movies in Storage:</b> <code>{total_movies}</code>\n"
                f"📥 <b>Total Movie Downloads:</b> <code>{total_dl}</code>\n"
                f"👑 <b>Active VIP Members:</b> <code>{total_vip}</code>\n\n"
                f"📦 <i>Storage Channel ID:</i> <code>{STORAGE_CHANNEL_RAW}</code>"
            )
            await message.reply_text(stats_msg)
            return

        # /storage Command (ADMIN ONLY - List Recent 30 Movies)
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
                list_text += f"{idx}. <b>{html.escape(clean_t[:30])}</b> (ID: <code>{mid}</code> | 📥 {dl_count})\n"

            if total_movies > 30:
                list_text += f"\n<i>...සහ තවත් චිත්‍රපට {total_movies - 30}ක් ඇත.</i>"

            await message.reply_text(list_text)
            return

        # /viplist Command (ADMIN ONLY - Shows Members + Individual Kick Buttons)
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

        # /kickvip <USER_ID> (ADMIN DIRECT COMMAND)
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

        # /addvip Command
        if text.startswith("/addvip"):
            if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
                return
            args = text.split()
            if len(args) < 2:
                await message.reply_text("❌ <b>භාවිතය:</b> <code>/addvip &lt;USER_ID&gt;</code>")
                return
            try:
                target_user_id = int(args[1].strip())
            except ValueError:
                await message.reply_text("❌ වැරදි User ID එකකි.")
                return

            now = datetime.utcnow()
            expiry_date = now + timedelta(days=30)
            await vip_users_col.update_one(
                {"user_id": target_user_id},
                {"$set": {"user_id": target_user_id, "expiry_date": expiry_date, "joined_at": now}},
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
                                text=f"🎉 <b>ඔබගේ VIP සාමාජිකත්වය සක්‍රිය විය!</b>\n\n🔗 VIP Channel Link:\n{link}"
                            )
                            await message.reply_text(f"✅ User <code>{target_user_id}</code> VIP ලෙස සක්‍රිය කරන ලදී.\n📅 Expiry: <code>{expiry_date.strftime('%Y-%m-%d')}</code>")
                            return
                await message.reply_text("⚠️ Invite Link එක සෑදීම අසාර්ථක විය.")
            except Exception as e:
                await message.reply_text(f"⚠️ Invite Error: {e}")
            return

        # /start Command
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            param = parts[1].strip() if len(parts) > 1 else ""

            if param in ["buyvip", "vip", "buystar_vip"]:
                await message.reply_text(VIP_DETAILS_TEXT, reply_markup=get_vip_options_markup())
                return

            # RE-ROUTING OLD POSTS: Seamlessly redirect old VIP links to File Bot
            if param.startswith("vipfile_"):
                mid = param.split("_")[1]
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

            # RE-ROUTING OLD POSTS: Seamlessly redirect old Step 2 links to File Bot
            if param.startswith("tok2_"):
                mid = param.split("_")[2]
                dl_btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Get Movie File (Click Here)", url=f"https://t.me/{target_delivery_bot}?start=tok2_{mid}")]
                ])
                await message.reply_text("🎉 <b>සත්‍යාපනය සාර්ථකයි!</b>\n\nචිත්‍රපටය ලබාගැනීමට පහත Button එක ඔබන්න 👇", reply_markup=dl_btn)
                return

            if param.startswith("buy_"):
                mid = param.split("_")[1]
                f_doc = await files_col.find_one({"message_id": int(mid)})
                m_title = f_doc.get("file_name", "Movie File") if f_doc else "Movie File"
                clean_t = clean_movie_title(m_title)[0]

                ok, err = await send_tg_invoice(user_id, f"⚡ {clean_t[:25]}", f"{clean_t} චිත්‍රපටය Telegram Stars හරහා ලබාගැනීමට.", f"single_{mid}", SINGLE_STAR_PRICE)
                if not ok:
                    await message.reply_text(f"⚠️ Stars Error: <code>{err}</code>")
                return

            if not await check_access(user_id):
                await message.reply_text(
                    "🔒 <b>චිත්‍රපට ලබාගැනීමට පෙර කරුණාකර පහත Channels දෙකටම Join වී Verify ඔබන්න:</b>",
                    reply_markup=await get_fsub_markup(param)
                )
                return

            if param.startswith("adstep1_"):
                mid = param.split("_")[1]
                step1_url = f"{BASE_URL}/gate/step1/{user_id}/{mid}" if BASE_URL else PRIMARY_AD_LINK
                await message.reply_text(
                    "🎬 <b>Download Verification (Step 1 of 2):</b>\n\nනොමිලේ ලබාගැනීමට පහත Sponsor Link එක විවෘත කර තත්පර 8ක් රැඳී සිටින්න:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Open Sponsor Link 1", url=step1_url)]])
                )
                return

            await message.reply_text(
                "👋 <b>සාදරයෙන් පිළිගන්නවා Cinex LK වෙත!</b>\n\n"
                "🔍 Movie එකේ නම එවන්න.\n"
                "👑 VIP සාමාජිකත්වය: <code>/start vip</code>"
            )

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

    # ACTION: KICK VIP USER
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

    # ACTION 1: POST TO MAIN CHANNEL
    if data.startswith("post_main_"):
        msg_id = int(data.replace("post_main_", ""))
        caption = callback.message.caption or callback.message.text or ""

        main_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Fast Download (Ads)", url=f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}")],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️)", url=f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"),
                InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", url=f"https://t.me/{BOT_USERNAME}?start=buyvip")
            ]
        ])

        target = MAIN_CHANNEL
        try:
            if callback.message.photo:
                await client.send_photo(chat_id=target, photo=callback.message.photo.file_id, caption=caption, reply_markup=main_markup)
            else:
                await client.send_message(chat_id=target, text=caption, reply_markup=main_markup)
            await callback.answer("✅ Main Channel එකට සාර්ථකව Post කරන ලදී!", show_alert=True)
        except Exception as e:
            await callback.answer(f"❌ Main Fail: {str(e)[:100]}", show_alert=True)
        return

    # ACTION 2: POST TO VIP CHANNEL
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
            await callback.answer("✅ VIP Channel එකට සාර්ථකව Post කරන ලදී!", show_alert=True)
        else:
            await callback.answer(f"❌ VIP Fail: {err_desc[:100]}", show_alert=True)
        return

    # USER VERIFY CALLBACK
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
                elif param in ["buyvip", "vip", "buystar_vip"]:
                    await client.send_message(user_id, VIP_DETAILS_TEXT, reply_markup=get_vip_options_markup())
                elif param.startswith("buy_"):
                    mid = param.split("_")[1]
                    f_doc = await files_col.find_one({"message_id": int(mid)})
                    m_title = f_doc.get("file_name", "Movie File") if f_doc else "Movie File"
                    clean_t = clean_movie_title(m_title)[0]
                    await send_tg_invoice(user_id, f"⚡ {clean_t[:25]}", f"{clean_t} Direct File", f"single_{mid}", SINGLE_STAR_PRICE)
            else:
                await client.send_message(user_id, "👋 ඔබට අවශ්‍ය Movie එකේ නම type කර Search කරන්න.")
        else:
            await callback.answer("❌ කරුණාකර Channels 2ටම Join වී නැවත Verify ඔබන්න.", show_alert=True)
        return

    # VIP STARS CALLBACK
    if data == "pay_vip_stars":
        await callback.answer()
        ok, err = await send_tg_invoice(user_id, "👑 Cinex LK VIP Pass (30 Days)", "VIP Access (No Ads)", "vip_sub", VIP_STAR_PRICE)
        if not ok:
            await callback.message.reply_text(f"⚠️ Stars Invoice Error: <code>{err}</code>")
        return

    # VIP BANK CALLBACK
    if data == "pay_vip_bank":
        await callback.answer()
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
                "amount": VIP_LKR_PRICE,
                "status": "pending",
                "created_at": datetime.utcnow()
            }},
            upsert=True
        )

        if ADMIN_USER_ID:
            admin_alert = (
                "🔔 <b>නව Bank Payment ඉල්ලීමක්!</b>\n\n"
                f"👤 <b>පරිශීලකයා:</b> {html.escape(full_name)} ({username})\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                f"🔑 <b>Reference Code:</b> <code>{ref}</code>\n"
                f"💰 <b>මුදල:</b> <code>Rs. {VIP_LKR_PRICE}</code>\n\n"
                f"📌 <i>User slip එක එවූ පසු VIP දීමට:</i>\n<code>/addvip {user_id}</code>"
            )
            try:
                await client.send_message(chat_id=ADMIN_USER_ID, text=admin_alert)
            except Exception:
                pass

        admin_link = f"https://t.me/{ADMIN_USERNAME}" if ADMIN_USERNAME else None
        text = (
            "🇱🇰 <b>බැංකු තැන්පතු මඟින් VIP ලබාගැනීම:</b>\n\n"
            f"💰 <b>ගෙවිය යුතු මුදල:</b> <code>Rs. {VIP_LKR_PRICE}</code>\n\n"
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
# TELEGRAM STARS SUCCESS
# =========================================================
@app.on_raw_update()
async def handle_precheckout(client: Client, update, users, chats):
    if update.__class__.__name__ == "UpdateBotPrecheckoutQuery":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"pre_checkout_query_id": str(update.query_id), "ok": True})

payment_filter = filters.create(lambda _, __, m: bool(getattr(m, "successful_payment", None)))

@app.on_message(payment_filter)
async def handle_payment_success(client: Client, message: Message):
    payload = message.successful_payment.invoice_payload
    target_delivery_bot = FILE_BOT_USERNAME or BOT_USERNAME

    if payload.startswith("single_"):
        mid = int(payload.split("_")[1])
        dl_link = f"https://t.me/{target_delivery_bot}?start=vipfile_{mid}"
        await message.reply_text(
            "🎉 <b>Stars ගෙවීම සාර්ථකයි!</b>\n\nපහත Button එකෙන් Direct File එක ලබාගන්න 👇",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download Movie File", url=dl_link)]])
        )

    elif payload == "vip_sub":
        user_id = message.from_user.id
        now = datetime.utcnow()
        expiry = now + timedelta(days=30)
        await vip_users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "expiry_date": expiry, "joined_at": now}}, upsert=True)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": str(VIP_CHANNEL_RAW), "member_limit": 1}) as resp:
                res = await resp.json()
                if res.get("ok"):
                    link = res["result"]["invite_link"]
                    await message.reply_text(f"🎉 <b>VIP සාමාජිකත්වය සක්‍රිය විය!</b>\n\n🔗 VIP Channel Link:\n{link}")

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
                        print(f"🔗 File Bot Webhook Linked: {webhook_url}")
                    else:
                        print(f"⚠️ Webhook Warning: {data.get('description')}")
        except Exception as e:
            print(f"Webhook Exception: {e}")

async def main():
    global BOT_USERNAME
    await app.start()
    me = await app.get_me()
    BOT_USERNAME = me.username
    print(f"🤖 Cinex LK Super-Control Bot Live as @{BOT_USERNAME}")

    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web Engine Live on port {PORT}")

    await setup_file_bot_webhook()

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
