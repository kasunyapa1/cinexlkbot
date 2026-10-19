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
        return 0
    val = str(val).strip()
    if val.startswith("@"):
        return val
    try:
        return int(val)
    except ValueError:
        return val

# =========================================================
# CONFIGURATIONS
# =========================================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

STORAGE_CHANNEL = parse_target(os.environ.get("STORAGE_CHANNEL", "-1004413765578"))
VIP_CHANNEL = parse_target(os.environ.get("VIP_CHANNEL", "-1004387584375"))
MAIN_CHANNEL = parse_target(os.environ.get("MAIN_CHANNEL", "@cinexlk"))
BACKUP_CHANNEL = parse_target(os.environ.get("BACKUP_CHANNEL", "-1003901762623"))

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

FREE_USER_DELETE_DURATION = int(os.environ.get("FREE_USER_DELETE_DURATION", "3600"))
VIP_USER_DELETE_DURATION = int(os.environ.get("VIP_USER_DELETE_DURATION", "21600"))

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
requests_col = db_client["MovieDB"]["movie_requests"]

channel_post_lock = asyncio.Lock()

# =========================================================
# WEB SERVER & AD GATE
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
    return web.Response(text="Cinex LK Bot Alive", status=200)

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
    html_page = SAME_PAGE_GATE_HTML.format(step="2", ad_url=PRIMARY_AD_LINK, bot_username=BOT_USERNAME, token=token)
    return web.Response(text=html_page, content_type='text/html')

# =========================================================
# TELEGRAM HTTP ENGINES (HTML SAFE)
# =========================================================
async def send_tg_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
    body = {
        "chat_id": int(chat_id),
        "title": str(title),
        "description": str(description),
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

async def send_tg_photo_url(chat_id: str, photo_url: str, caption_html: str, reply_markup: dict):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": str(chat_id),
        "photo": photo_url,
        "caption": caption_html,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                res = await resp.json()
                return res
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
# FILE SENDER & AUTO-DELETE
# =========================================================
async def auto_delete_task(chat_id: int, msg_ids: list, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id=chat_id, message_ids=msg_ids)
        await app.send_message(chat_id=chat_id, text="🗑️ <b>ප්‍රකාශන හිමිකම් ආරක්ෂාව මත චිත්‍රපටය Chat එකෙන් ඉවත් කරන ලදී.</b>", parse_mode=None)
    except Exception:
        pass

async def deliver_movie_file(chat_id: int, message_id: int, is_vip: bool = False):
    delay = VIP_USER_DELETE_DURATION if is_vip else FREE_USER_DELETE_DURATION
    time_label = "පැය 6" if is_vip else "පැය 1"

    try:
        await files_col.update_one({"message_id": int(message_id)}, {"$inc": {"download_count": 1}})
    except Exception:
        pass

    warn_text = (
        "⚡ <b>Auto-Download Started:</b>\n\n"
        f"⚠️ මෙම චිත්‍රපටය තවත් <b>{time_label}කින්</b> Chat එකෙන් ඉවත් වේ.\n"
        "📥 Device එකට Save කරගැනීමට වීඩියෝවේ Menu එකෙන් <b>'Save to Downloads'</b> දෙන්න."
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
    payload = {"chat_id": int(chat_id), "from_chat_id": str(STORAGE_CHANNEL), "message_id": int(message_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                res = await resp.json()
                if res.get("ok"):
                    sent_id = res["result"]["message_id"]
                    warn_msg = await app.send_message(chat_id=chat_id, text=warn_text)
                    asyncio.create_task(auto_delete_task(chat_id, [sent_id, warn_msg.id], delay))
                    return True
    except Exception:
        pass

    await app.send_message(chat_id=chat_id, text="❌ <b>මෙම චිත්‍රපටය Storage එකෙන් ඉවත් කර ඇත.</b>")
    return False

# =========================================================
# VIP CHECK & ACCESS CONTROL
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
        btns.append([InlineKeyboardButton("🛡️ Join Backup Channel", url=f"https://t.me/{str(BACKUP_CHANNEL).replace('@', '')}")])
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
    "• පැය 6ක Auto-Delete කාලයක් හිමිවීම\n\n"
    "👇 <b>ගෙවීම් කිරීමට කැමති ආකාරය තෝරන්න:</b>"
)

# =========================================================
# PERFECT MOVIE CLEANER & OMDB MATCHER
# =========================================================
def clean_movie_title(raw_name: str):
    name = os.path.splitext(raw_name)[0]
    
    # 1. Year extract
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    year = year_match.group(1) if year_match else None
    
    # 2. Year eka nathuwa ithuru tika clean karanna
    if year:
        name = name.replace(year, " ")

    # 3. Quality tags, brackets, dashes remove
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
    
    # Fallback to local clean name if OMDb fails
    return {"title": title.title(), "year": year or "N/A", "rating": "N/A", "genres": "Cinema", "plot": "Directly uploaded to Cinex LK library.", "poster": None}

# =========================================================
# STORAGE TO MAIN DISPATCH WORKER
# =========================================================
async def dispatch_storage_to_main(client: Client, message: Message):
    global BOT_USERNAME
    async with channel_post_lock:
        try:
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

            markup = {
                "inline_keyboard": [
                    [{"text": "📥 Fast Download (Ads)", "url": f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}"}],
                    [
                        {"text": f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️)", "url": f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"},
                        {"text": "👑 Buy VIP Pass (Monthly)", "url": f"https://t.me/{BOT_USERNAME}?start=buyvip"}
                    ]
                ]
            }

            target = str(MAIN_CHANNEL).strip()
            poster_url = meta.get("poster") if (meta.get("poster") and meta["poster"].startswith("http")) else DEFAULT_POSTER

            # 1. Send with Poster
            res = await send_tg_photo_url(target, poster_url, caption, markup)
            
            # 2. Safe Fallback to text message if photo fails
            if not res.get("ok"):
                await send_tg_message(target, caption, markup)

            print(f"✅ Auto-posted '{file_name}' ({size_mb} MB) to Main Channel")
            await asyncio.sleep(2.5)

        except Exception as e:
            print(f"❌ Error dispatching to main: {e}")

# =========================================================
# HANDLER 1: STORAGE CHANNEL POSTS ONLY
# =========================================================
@app.on_message(filters.chat([STORAGE_CHANNEL]) & (filters.document | filters.video))
async def on_channel_upload(client: Client, message: Message):
    asyncio.create_task(dispatch_storage_to_main(client, message))

# =========================================================
# HANDLER 2: PRIVATE COMMANDS ONLY (/start)
# =========================================================
@app.on_message(filters.command("start") & filters.private)
async def handle_start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ""

    if param in ["buyvip", "vip", "buystar_vip"]:
        await message.reply_text(VIP_DETAILS_TEXT, reply_markup=get_vip_options_markup())
        return

    if param.startswith("vipfile_"):
        mid = int(param.split("_")[1])
        await message.reply_text("👑 <b>VIP Direct File:</b>")
        await deliver_movie_file(user_id, mid, is_vip=True)
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
        mid = int(param.split("_")[2])
        await message.reply_text("🎉 <b>සත්‍යාපනය සාර්ථකයි! මෙන්න ඔබගේ චිත්‍රපටය:</b>")
        await deliver_movie_file(user_id, mid, is_vip=False)
        return

    if param.startswith("buy_"):
        mid = param.split("_")[1]
        ok, err = await send_tg_invoice(user_id, "⚡ Direct Movie File", "දැන්වීම් නොමැතිව direct Telegram file එක ලබාගැනීමට.", f"single_{mid}", SINGLE_STAR_PRICE)
        if not ok:
            await message.reply_text(f"⚠️ Stars Error: <code>{err}</code>")
        return

    if not await check_access(user_id):
        await message.reply_text("🔒 <b>චිත්‍රපට ලබාගැනීමට පෙර අපගේ Channels වලට Join වන්න:</b>", reply_markup=await get_fsub_markup(param))
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
        "📚 චිත්‍රපට නාමාවලිය: <code>/movielist</code>\n"
        "👑 VIP සාමාජිකත්වය: <code>/start vip</code>"
    )

# =========================================================
# HANDLER 3: CALLBACK QUERIES
# =========================================================
@app.on_callback_query()
async def global_callback_handler(client: Client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    await callback.answer()

    if data.startswith("verify_"):
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
                    await send_tg_invoice(user_id, "⚡ Direct Movie File", "No Ads File", f"single_{mid}", SINGLE_STAR_PRICE)
            else:
                await client.send_message(user_id, "👋 ඔබට අවශ්‍ය Movie එකේ නම type කර Search කරන්න.")
        else:
            await callback.answer("❌ කරුණාකර Channels 2ටම Join වී Verify ඔබන්න.", show_alert=True)
        return

    if data == "pay_vip_stars":
        ok, err = await send_tg_invoice(user_id, "👑 Cinex LK VIP Pass (30 Days)", "VIP Access (No Ads)", "vip_sub", VIP_STAR_PRICE)
        if not ok:
            await callback.message.reply_text(f"⚠️ Stars Invoice Error: <code>{err}</code>")
        return

    if data == "pay_vip_bank":
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
# HANDLER 4: FORWARD POST TO VIP CHANNEL
# =========================================================
@app.on_message(filters.private & filters.forwarded)
async def handle_forward_to_vip(client: Client, message: Message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        return

    orig = message.caption or message.text or ""
    target_msg_id = None

    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.url and ("adstep1_" in btn.url or "buy_" in btn.url or "vipfile_" in btn.url):
                    m = re.search(r"_(\d+)", btn.url)
                    if m:
                        target_msg_id = int(m.group(1))
                        break

    if not target_msg_id:
        m = re.search(r"🎬\s*(?:<b>|\*\*)(.*?)(?:\s*\(\d{4}\))?(?:</b>|\*\*)", orig)
        if m:
            doc = await files_col.find_one({"file_name": {"$regex": re.escape(m.group(1).strip()), "$options": "i"}})
            if doc:
                target_msg_id = doc.get("message_id")

    if not target_msg_id:
        target_msg_id = message.forward_from_message_id or message.id

    f_doc = await files_col.find_one({"message_id": target_msg_id})
    file_name = f_doc.get("file_name", "Movie") if f_doc else "Movie"

    clean_caption = re.sub(r"👇.*", "", orig, flags=re.DOTALL).strip()
    if not clean_caption:
        meta = await fetch_metadata(file_name)
        clean_caption = f"🎬 <b>{html.escape(meta['title'])} ({meta['year']})</b>\n\n⭐ <b>IMDb Rating:</b> <code>{meta['rating']} / 10</code>\n🎭 <b>Genres:</b> <code>{meta['genres']}</code>"

    vip_caption = f"{clean_caption}\n\n👑 <b>VIP Direct File:</b> දැන්වීම් නොමැතිව download කරගන්න 👇"
    vip_markup = {"inline_keyboard": [[{"text": "⚡ Instant Download (Direct File)", "url": f"https://t.me/{BOT_USERNAME}?start=vipfile_{target_msg_id}"}]]}

    status = await message.reply_text("⏳ VIP Channel එකට Auto-Post කරමින් පවතී...")
    target_vip = str(VIP_CHANNEL).strip()

    poster_url = DEFAULT_POSTER
    if message.photo:
        p = await client.download_media(message.photo.file_id)
        if p and os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", target_vip)
                    form.add_field("photo", f.read(), filename="poster.jpg")
                    form.add_field("caption", vip_caption)
                    form.add_field("parse_mode", "HTML")
                    form.add_field("reply_markup", json.dumps(vip_markup))
                    async with aiohttp.ClientSession() as s:
                        async with s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data=form) as r:
                            res = await r.json()
                            if res.get("ok"):
                                await status.edit_text(f"✅ <b>'{file_name}'</b> සාර්ථකව VIP Channel එකට Auto-Post කරන ලදී!")
                                return
            except Exception:
                pass
            finally:
                os.remove(p)

    res = await send_tg_photo_url(target_vip, poster_url, vip_caption, vip_markup)
    if not res.get("ok"):
        res = await send_tg_message(target_vip, vip_caption, vip_markup)

    if res.get("ok"):
        await status.edit_text(f"✅ <b>'{file_name}'</b> සාර්ථකව VIP Channel එකට Auto-Post කරන ලදී!")
    else:
        await status.edit_text("❌ VIP Post Error!")

# =========================================================
# HANDLER 5: ADMIN /addvip COMMAND
# =========================================================
@app.on_message(filters.command("addvip") & filters.private)
async def admin_add_vip_handler(client: Client, message: Message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>භාවිතය:</b> <code>/addvip &lt;USER_ID&gt;</code>")
        return

    try:
        target_user_id = int(args[1].strip())
    except ValueError:
        await message.reply_text("❌ වැරදි User ID එකකි.")
        return

    expiry_date = datetime.utcnow() + timedelta(days=30)
    await vip_users_col.update_one(
        {"user_id": target_user_id},
        {"$set": {"user_id": target_user_id, "expiry_date": expiry_date, "joined_at": datetime.utcnow()}},
        upsert=True
    )
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
        payload = {"chat_id": str(VIP_CHANNEL), "member_limit": 1}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                res = await resp.json()
                if res.get("ok"):
                    link = res["result"]["invite_link"]
                    await client.send_message(
                        chat_id=target_user_id,
                        text=f"🎉 <b>ඔබගේ VIP සාමාජිකත්වය සක්‍රිය විය!</b>\n\n🔗 VIP Channel Link:\n{link}"
                    )
                    await message.reply_text(f"✅ User <code>{target_user_id}</code> VIP ලෙස සක්‍රිය කරන ලදී.")
                    return
        await message.reply_text("⚠️ Invite Link එක සෑදීම අසාර්ථක විය.")
    except Exception as e:
        await message.reply_text(f"⚠️ Invite Error: {e}")

# =========================================================
# HANDLER 6: TELEGRAM STARS RAW PRECHECKOUT & SUCCESS
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

    if payload.startswith("single_"):
        mid = int(payload.split("_")[1])
        await message.reply_text("🎉 <b>Stars ගෙවීම සාර්ථකයි!</b> මෙන්න Movie එක:")
        await deliver_movie_file(message.chat.id, mid, is_vip=True)

    elif payload == "vip_sub":
        user_id = message.from_user.id
        expiry = datetime.utcnow() + timedelta(days=30)
        await vip_users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "expiry_date": expiry}}, upsert=True)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": str(VIP_CHANNEL), "member_limit": 1}) as resp:
                res = await resp.json()
                if res.get("ok"):
                    link = res["result"]["invite_link"]
                    await message.reply_text(f"🎉 <b>VIP සාමාජිකත්වය සක්‍රිය විය!</b>\n\n🔗 VIP Channel Link:\n{link}")

# =========================================================
# SERVER INIT & RUNNER
# =========================================================
async def main():
    global BOT_USERNAME
    await app.start()
    me = await app.get_me()
    BOT_USERNAME = me.username
    print(f"🤖 Bot Started as @{BOT_USERNAME}")

    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Cinex LK Web Engine Live on port {PORT}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
