import os
import re
import io
import asyncio
from datetime import datetime, timedelta
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

def parse_chat_target(val: str):
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

STORAGE_CHANNEL = parse_chat_target(os.environ.get("STORAGE_CHANNEL", "-1004413765578"))
VIP_CHANNEL = parse_chat_target(os.environ.get("VIP_CHANNEL", "-1004387584375"))
MAIN_CHANNEL = parse_chat_target(os.environ.get("MAIN_CHANNEL", "@cinexlk"))
BACKUP_CHANNEL = parse_chat_target(os.environ.get("BACKUP_CHANNEL", "-1003901762623"))

VIP_STAR_PRICE = int(os.environ.get("VIP_STAR_PRICE", "150"))
SINGLE_STAR_PRICE = int(os.environ.get("SINGLE_STAR_PRICE", "5"))

BOT_USERNAME = os.environ.get("BOT_USERNAME", "").replace("@", "")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "").strip()

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
MONETAG_STREAM_LINK = os.environ.get("MONETAG_STREAM_LINK", "")
ADSTERRA_DIRECT_LINK = os.environ.get("ADSTERRA_DIRECT_LINK", "")
PORT = int(os.environ.get("PORT", "8080"))

app = Client(
    "all_in_one_movie_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=16,
    sleep_threshold=30
)

db_client = AsyncIOMotorClient(MONGO_URI)
files_col = db_client["MovieDB"]["files"]
vip_users_col = db_client["MovieDB"]["vip_users"]
bot_users_col = db_client["MovieDB"]["bot_users"]

# =========================================================
# DIRECT TELEGRAM BOT API CALLS
# =========================================================
async def send_tg_api_post(chat_id, text, reply_markup=None, photo_file_id=None):
    try:
        async with aiohttp.ClientSession() as session:
            if photo_file_id:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": chat_id,
                    "photo": photo_file_id,
                    "caption": text,
                    "parse_mode": "Markdown"
                }
            else:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Direct Bot API Post Error: {e}")
        return {"ok": False, "description": str(e)}

async def send_tg_api_copy(chat_id, from_chat_id, message_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
        payload = {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Direct Bot API Copy Error: {e}")
        return {"ok": False, "description": str(e)}

async def get_tg_api_chat_member(chat_id, user_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        payload = {"chat_id": chat_id, "user_id": user_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ getChatMember Error: {e}")
        return {"ok": False}

async def get_tg_api_invite_link(chat_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/exportChatInviteLink"
        payload = {"chat_id": chat_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data.get("result")
    except Exception as e:
        print(f"⚠️ exportChatInviteLink Error: {e}")
    return None

async def send_stars_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        data = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload,
            "currency": "XTR",
            "prices": [{"label": title, "amount": stars}]
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Stars Invoice Error: {e}")

payment_filter = filters.create(lambda _, __, m: bool(getattr(m, "successful_payment", None)))

# =========================================================
# DUAL CHANNEL (MAIN + BACKUP) VERIFICATION SYSTEM
# =========================================================
async def is_user_in_channel(chat_target, user_id: int) -> bool:
    if not chat_target:
        return True
    res = await get_tg_api_chat_member(chat_target, user_id)
    if res.get("ok"):
        status = res.get("result", {}).get("status", "")
        return status in ["member", "administrator", "creator", "restricted"]
    return False

async def check_user_access(client: Client, user_id: int) -> bool:
    try:
        user_record = await bot_users_col.find_one({"user_id": user_id})
        if user_record and user_record.get("fsub_verified"):
            return True

        in_main = await is_user_in_channel(MAIN_CHANNEL, user_id)
        in_backup = await is_user_in_channel(BACKUP_CHANNEL, user_id)

        if in_main and in_backup:
            await bot_users_col.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "fsub_verified": True, "verified_at": datetime.utcnow()}},
                upsert=True
            )
            return True
    except Exception as e:
        print(f"⚠️ User check error: {e}")
    return False

async def get_dual_fsub_buttons(start_param: str = "") -> InlineKeyboardMarkup:
    buttons = []
    
    # 1. Main Channel Button
    if MAIN_CHANNEL:
        if isinstance(MAIN_CHANNEL, str) and MAIN_CHANNEL.startswith("@"):
            main_url = f"https://t.me/{MAIN_CHANNEL.replace('@', '')}"
        else:
            main_url = await get_tg_api_invite_link(MAIN_CHANNEL)
        if main_url:
            buttons.append([InlineKeyboardButton("📢 Join Main Channel", url=main_url)])

    # 2. Backup Channel Button
    if BACKUP_CHANNEL:
        if isinstance(BACKUP_CHANNEL, str) and BACKUP_CHANNEL.startswith("@"):
            backup_url = f"https://t.me/{BACKUP_CHANNEL.replace('@', '')}"
        else:
            backup_url = await get_tg_api_invite_link(BACKUP_CHANNEL)
        if backup_url:
            buttons.append([InlineKeyboardButton("🛡️ Join Backup Channel", url=backup_url)])

    try_url = f"https://t.me/{BOT_USERNAME}?start={start_param}" if start_param else f"https://t.me/{BOT_USERNAME}?start"
    buttons.append([InlineKeyboardButton("🔄 Verify & Unlock", url=try_url)])
    return InlineKeyboardMarkup(buttons)

# =========================================================
# HELPER FUNCTIONS (IMDb & LANGUAGE)
# =========================================================
def parse_movie_query(filename: str):
    name = re.sub(r"\.(mp4|mkv|avi|webm|mov)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    name = re.sub(r"(1080p|720p|480p|2160p|4k|BluRay|WEB-DL|HDRip|x264|x265|HEVC|AAC|DDP|ESub)", "", name, flags=re.IGNORECASE)
    name = name.replace(".", " ").replace("_", " ").strip()

    match_year = re.search(r"\b(19\d\d|20\d\d)\b", name)
    year = match_year.group(1) if match_year else None
    if year:
        title = re.sub(r"\b" + year + r"\b", "", name).strip()
    else:
        title = name.strip()

    return title, year

def get_clean_language(raw_lang: str, filename: str = "") -> str:
    fn_lower = filename.lower()
    common_langs = ["sinhala", "tamil", "hindi", "malayalam", "telugu", "korean", "japanese", "english", "chinese", "spanish", "french"]
    for lang in common_langs:
        if re.search(r"\b" + lang + r"\b", fn_lower):
            return lang.capitalize()

    if raw_lang and raw_lang != "N/A":
        return raw_lang.split(",")[0].strip()

    return "English"

async def fetch_imdb_data(filename: str):
    if not OMDB_API_KEY:
        return None

    title, year = parse_movie_query(filename)
    url = f"https://www.omdbapi.com/?t={title}&y={year}&apikey={OMDB_API_KEY}" if year else f"https://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                if data.get("Response") == "True":
                    return data
                fallback_url = f"https://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
                async with session.get(fallback_url, timeout=aiohttp.ClientTimeout(total=5)) as fb_resp:
                    fb_data = await fb_resp.json()
                    if fb_data.get("Response") == "True":
                        return fb_data
    except Exception as e:
        print(f"⚠️ OMDb Request Error: {e}")
    return None

# =========================================================
# 1. STREAMING & 2-STEP ADS DOWNLOAD WEB SERVER
# =========================================================
routes = web.RouteTableDef()

@routes.get("/")
async def root_ping(request):
    return web.Response(text="Bot is Live and Active 24/7!", status=200)

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Cinex LK Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ margin:0; background:#080b11; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; color:white; }}
        video {{ width:95%; max-width:880px; border-radius:12px; box-shadow:0 8px 30px rgba(0,0,0,0.8); }}
    </style>
</head>
<body>
    <video id="moviePlayer" controls autoplay playsinline preload="metadata">
        <source src="/stream/{msg_id}" type="video/mp4">
        Browser does not support video playback.
    </video>
    {ad_script}
</body>
</html>
"""

AD_SCRIPT_TEMPLATE = """
    <script>
        const AD_URL = "{ad_url}";
        let adOpened = false;
        function triggerSafeAd() {{
            if (!adOpened && AD_URL) {{
                adOpened = true;
                const win = window.open(AD_URL, '_blank');
                if (win) win.focus();
            }}
        }}
        document.body.addEventListener('click', function() {{ triggerSafeAd(); }}, {{ once: true }});
    </script>
"""

DOWNLOAD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Fast Download - Cinex LK</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ margin:0; background:#0e1621; display:flex; flex-direction:column; justify-content:center; align-items:center; min-height:100vh; font-family:sans-serif; color:white; text-align:center; padding:20px; box-sizing:border-box; }}
        .card {{ background:#17212b; padding:35px 25px; border-radius:18px; box-shadow:0 10px 35px rgba(0,0,0,0.6); max-width:420px; width:100%; border:1px solid #242f3d; }}
        .badge {{ background:#2b5278; color:#64b5f6; font-size:12px; padding:6px 12px; border-radius:20px; font-weight:bold; letter-spacing:1px; display:inline-block; margin-bottom:15px; }}
        h2 {{ margin:0 0 10px 0; font-size:22px; }}
        p {{ color:#8a9aa8; font-size:14px; margin:0 0 20px 0; line-height:1.5; }}
        .btn {{ display:block; width:100%; box-sizing:border-box; background:#2481cc; color:white; padding:15px; border-radius:12px; text-decoration:none; font-weight:bold; font-size:16px; margin-top:15px; cursor:pointer; border:none; transition:0.2s; }}
        .btn:hover {{ background:#1d6fa5; transform:scale(1.02); }}
        .btn-success {{ background:#2ea650; }}
        .timer {{ font-size:20px; font-weight:bold; color:#64b5f6; margin:15px 0; }}
        .step-indicator {{ display:flex; justify-content:center; gap:8px; margin-bottom:20px; }}
        .dot {{ width:10px; height:10px; border-radius:50%; background:#334454; }}
        .dot.active {{ background:#2481cc; }}
        .dot.done {{ background:#2ea650; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">CINEX LK SECURE DOWNLOAD</div>
        <h2>🎬 Download Verification</h2>
        <p id="desc">File එක download කිරීමට පියවර 2 සම්පූර්ණ කරන්න.</p>
        <div class="step-indicator">
            <div class="dot active" id="dot1"></div>
            <div class="dot" id="dot2"></div>
            <div class="dot" id="dot3"></div>
        </div>
        <button id="step1Btn" class="btn" onclick="startStep1()">🔓 Step 1: Verify & Continue</button>
        <div class="timer" id="timerBox" style="display:none;">Wait <span id="seconds">5</span>s...</div>
        <button id="step2Btn" class="btn" onclick="startStep2()" style="display:none;">🔓 Step 2: Unlock Download</button>
        <a id="finalDlBtn" class="btn btn-success" href="/stream/{msg_id}" target="_blank" style="display:none;">📥 Download Movie Now</a>
    </div>
    <script>
        const AD1 = "{ad1}";
        const AD2 = "{ad2}";
        const STREAM_URL = "/stream/{msg_id}";
        function openAd(url) {{ if (url) {{ const win = window.open(url, '_blank'); if (win) win.focus(); }} }}
        function startStep1() {{
            openAd(AD1);
            document.getElementById('step1Btn').style.display = 'none';
            document.getElementById('timerBox').style.display = 'block';
            document.getElementById('desc').innerText = "පළමු පියවර සත්‍යාපනය වෙමින් පවතී...";
            document.getElementById('dot1').className = "dot done";
            document.getElementById('dot2').className = "dot active";
            let count = 5;
            const timer = setInterval(() => {{
                count--;
                document.getElementById('seconds').innerText = count;
                if (count <= 0) {{
                    clearInterval(timer);
                    document.getElementById('timerBox').style.display = 'none';
                    document.getElementById('step2Btn').style.display = 'block';
                    document.getElementById('desc').innerText = "දෙවන Ad එක Unlock කර Download ලබාගන්න.";
                }}
            }}, 1000);
        }}
        function startStep2() {{
            openAd(AD2);
            document.getElementById('step2Btn').style.display = 'none';
            document.getElementById('timerBox').style.display = 'block';
            document.getElementById('seconds').innerText = '3';
            document.getElementById('desc').innerText = "Download Link එක සූදානම් කරමින් පවතී...";
            document.getElementById('dot2').className = "dot done";
            document.getElementById('dot3').className = "dot active";
            let count = 3;
            const timer2 = setInterval(() => {{
                count--;
                document.getElementById('seconds').innerText = count;
                if (count <= 0) {{
                    clearInterval(timer2);
                    document.getElementById('timerBox').style.display = 'none';
                    document.getElementById('finalDlBtn').style.display = 'block';
                    document.getElementById('dot3').className = "dot done";
                    document.getElementById('desc').innerText = "🎉 සූදානම්! පහත Button එක ඔබන්න.";
                    window.location.href = STREAM_URL;
                }}
            }}, 1000);
        }}
    </script>
</body>
</html>
"""

@routes.get("/watch/{msg_id}")
async def watch_page(request):
    msg_id = request.match_info['msg_id']
    is_vip = request.query.get("vip", "0") == "1"
    ad_script = "" if is_vip else AD_SCRIPT_TEMPLATE.format(ad_url=MONETAG_STREAM_LINK)
    return web.Response(text=PLAYER_HTML.format(msg_id=msg_id, ad_script=ad_script), content_type='text/html')

@routes.get("/download/{msg_id}")
async def download_page(request):
    msg_id = request.match_info['msg_id']
    return web.Response(
        text=DOWNLOAD_HTML.format(msg_id=msg_id, ad1=ADSTERRA_DIRECT_LINK, ad2=MONETAG_STREAM_LINK or ADSTERRA_DIRECT_LINK),
        content_type='text/html'
    )

@routes.get("/stream/{msg_id}")
async def stream_media(request):
    try:
        msg_id = int(request.match_info['msg_id'])
        
        # Ensure peer resolution before fetching messages
        try:
            target_peer = await app.resolve_peer(STORAGE_CHANNEL)
        except Exception:
            target_peer = STORAGE_CHANNEL

        msg = await app.get_messages(target_peer, msg_id)
        if not msg:
            return web.Response(text="File message not found in storage channel.", status=404)

        media = msg.document or msg.video
        if not media:
            return web.Response(text="No media found in the specified message.", status=404)

        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': media.mime_type or 'video/mp4',
                'Content-Length': str(media.file_size),
                'Content-Disposition': f'attachment; filename="{media.file_name or "movie.mp4"}"',
                'Accept-Ranges': 'bytes'
            }
        )
        await response.prepare(request)
        async for chunk in app.stream_media(msg, limit=0):
            await response.write(chunk)
        return response
    except Exception as e:
        print(f"❌ Streaming error: {e}")
        return web.Response(text=f"Error streaming file: {e}", status=500)

# =========================================================
# 2. AUTO-POST TO MAIN CHANNEL (MONETIZED ROUTING)
# =========================================================

@app.on_message((filters.chat(STORAGE_CHANNEL) | filters.channel) & (filters.document | filters.video))
async def handle_storage_upload(client: Client, message: Message):
    try:
        if str(message.chat.id) != str(STORAGE_CHANNEL):
            return

        media = message.document or message.video
        if not media:
            return

        file_name = media.file_name or "Unknown Movie"
        size_mb = round(media.file_size / (1024 * 1024), 2)
        msg_id = message.id

        print(f"\n📥 [Storage Channel] New File Uploaded: {file_name} (Msg ID: {msg_id})")

        try:
            await files_col.update_one(
                {"file_name": file_name},
                {"$set": {"file_name": file_name, "file_size": media.file_size, "message_id": msg_id}},
                upsert=True
            )
        except Exception as db_err:
            print(f"❌ DB Error: {db_err}")

        imdb = await fetch_imdb_data(file_name)

        # Route EVERY action via Bot to force First-Time verification
        watch_bot_url = f"https://t.me/{BOT_USERNAME}?start=watch_{msg_id}"
        dl_bot_url = f"https://t.me/{BOT_USERNAME}?start=dl_{msg_id}"
        buy_stars_url = f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"
        vip_buy_url = f"https://t.me/{BOT_USERNAME}?start=vip"

        main_buttons = [
            [InlineKeyboardButton("🌐 Watch Online", url=watch_bot_url)],
            [InlineKeyboardButton("📥 Fast Download (Ads)", url=dl_bot_url)],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️)", url=buy_stars_url),
                InlineKeyboardButton("👑 Buy VIP Pass (No Ads)", url=vip_buy_url)
            ]
        ]
        main_markup = InlineKeyboardMarkup(main_buttons)

        poster_bytes = None
        if imdb and imdb.get("Response") == "True":
            title = f"{imdb.get('Title')} ({imdb.get('Year')})"
            rating = imdb.get('imdbRating', 'N/A')
            genre = imdb.get('Genre', 'N/A')
            language = get_clean_language(imdb.get('Language', ''), file_name)
            plot = imdb.get('Plot', 'No description available.')
            raw_poster = imdb.get("Poster")

            caption = (
                f"🎬 **{title}**\n\n"
                f"⭐ **IMDb Rating:** `{rating}/10`\n"
                f"🎭 **Genre:** `{genre}`\n"
                f"🗣️ **Language:** `{language}`\n"
                f"📦 **Size:** `{size_mb} MB`\n\n"
                f"📖 **Story:** {plot[:250]}...\n\n"
                f"👇 **නැරඹීමට හෝ බාගත කිරීමට පහත Buttons භාවිතා කරන්න:**"
            )

            if raw_poster and raw_poster != "N/A":
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(raw_poster, timeout=aiohttp.ClientTimeout(total=5)) as img_resp:
                            if img_resp.status == 200:
                                poster_bytes = await img_resp.read()
                except Exception as dl_err:
                    print(f"⚠️ Poster download error: {dl_err}")
        else:
            language = get_clean_language("", file_name)
            caption = (
                f"🎬 **{file_name}**\n\n"
                f"🗣️ **Language:** `{language}`\n"
                f"📦 **Size:** `{size_mb} MB`\n\n"
                f"👇 **නැරඹීමට හෝ බාගත කිරීමට පහත Buttons භාවිතා කරන්න:**"
            )

        if MAIN_CHANNEL:
            posted = False
            if poster_bytes:
                try:
                    photo_file = io.BytesIO(poster_bytes)
                    photo_file.name = "poster.jpg"
                    await client.send_photo(chat_id=MAIN_CHANNEL, photo=photo_file, caption=caption, reply_markup=main_markup)
                    print(f"🚀 Photo Post published to Main Channel: {MAIN_CHANNEL}")
                    posted = True
                except Exception as p_err:
                    print(f"⚠️ Photo Post failed for Main: {p_err}. Trying text fallback...")

            if not posted:
                try:
                    await client.send_message(chat_id=MAIN_CHANNEL, text=caption, reply_markup=main_markup)
                    print(f"🚀 Text Post published to Main Channel: {MAIN_CHANNEL}")
                except Exception as t_err:
                    print(f"❌ Text post also failed for Main: {t_err}")

    except Exception as general_err:
        print(f"❌ Storage Handler Error: {general_err}")

# =========================================================
# 3. AUTO-KICK EXPIRED VIP USERS
# =========================================================
async def vip_expiry_checker():
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.utcnow()
            cursor = vip_users_col.find({"expiry_date": {"$lte": now}})
            expired_users = await cursor.to_list(length=50)

            for u in expired_users:
                user_id = u.get("user_id")
                if not user_id:
                    continue
                try:
                    await app.ban_chat_member(VIP_CHANNEL, user_id)
                    await app.unban_chat_member(VIP_CHANNEL, user_id)
                    print(f"🔒 Removed expired VIP member: {user_id}")

                    await app.send_message(
                        chat_id=user_id,
                        text="⚠️ **ඔබගේ Cinex LK VIP සාමාජිකත්වය දින 30 අවසන් විය!**\nනැවත සම්බන්ධ වීමට /start ගොස් VIP Pass එක ලබාගන්න."
                    )
                except Exception as kick_err:
                    print(f"⚠️ Failed to remove VIP member {user_id}: {kick_err}")

                await vip_users_col.delete_one({"_id": u["_id"]})

        except Exception as e:
            print(f"⚠️ VIP Checker error: {e}")

        await asyncio.sleep(6 * 3600)

# =========================================================
# 4. FORWARD-TO-VIP CONVERTER
# =========================================================

@app.on_message(filters.private & filters.forwarded)
async def manual_share_to_vip(client: Client, message: Message):
    try:
        target_text = message.caption or message.text or ""
        msg_id = None
        if message.reply_markup and message.reply_markup.inline_keyboard:
            for row in message.reply_markup.inline_keyboard:
                for btn in row:
                    if btn.url and ("watch_" in btn.url or "/watch/" in btn.url):
                        match = re.search(r"(?:watch_|/watch/)(\d+)", btn.url)
                        if match:
                            msg_id = match.group(1)
                            break
                    elif btn.url and ("dl_" in btn.url or "/download/" in btn.url):
                        match = re.search(r"(?:dl_|/download/)(\d+)", btn.url)
                        if match:
                            msg_id = match.group(1)
                            break
                if msg_id:
                    break

        if not msg_id and target_text:
            first_line = target_text.split("\n")[0].replace("🎬", "").strip()
            first_line_clean = re.sub(r"\(\d{4}\)", "", first_line).strip()
            db_doc = await files_col.find_one({"file_name": {"$regex": re.escape(first_line_clean), "$options": "i"}})
            if db_doc:
                msg_id = str(db_doc.get("message_id"))

        if not msg_id:
            return

        vip_watch_url = f"{BASE_URL}/watch/{msg_id}?vip=1"
        vip_direct_file_url = f"https://t.me/{BOT_USERNAME}?start=vipfile_{msg_id}"

        api_markup = {
            "inline_keyboard": [
                [{"text": "🌐 Watch Online (No Ads)", "url": vip_watch_url}],
                [{"text": "⚡ Instant Download (Direct File)", "url": vip_direct_file_url}]
            ]
        }

        photo_id = message.photo.file_id if message.photo else None

        res = await send_tg_api_post(
            chat_id=VIP_CHANNEL,
            text=target_text,
            reply_markup=api_markup,
            photo_file_id=photo_id
        )

        if res.get("ok"):
            await message.reply_text("👑 **සාර්ථකයි!** මෙම Post එක VIP Channel එකට Ad-Free buttons සමඟ Publish කරන ලදී.")
            print(f"🚀 Published to VIP Channel: Msg ID {msg_id}")
        else:
            err_desc = res.get("description", "Unknown error")
            await message.reply_text(f"❌ Telegram API Error: {err_desc}")

    except Exception as vip_err:
        await message.reply_text(f"❌ Error: {vip_err}")

# =========================================================
# 5. BOT COMMANDS & ACTIONS (STRICT DUAL FSUB UNLOCK)
# =========================================================

@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    text = message.text
    param = text.split()[1] if len(text.split()) > 1 else ""

    # VIP Direct File Download (Direct Bot API call - No verification needed for paid VIPs)
    if param.startswith("vipfile_"):
        msg_id = int(param.split("_")[1])
        await message.reply_text("👑 **VIP Direct File:** මෙන්න ඔබගේ Movie එක:")
        res = await send_tg_api_copy(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)
        if not res.get("ok"):
            try:
                await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)
            except Exception as copy_err:
                await message.reply_text(f"⚠️ File එක ලබාදීමට නොහැකි විය: {copy_err}")
        return

    # Check Dual Channel (Main + Backup) access for EVERY action
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(param)
        await message.reply_text(
            "🔒 **ප්‍රවේශය සත්‍යාපනය කර නොමැත! (Channel Verification)**\n\n"
            "චිත්‍රපට නැරඹීමට, බාගත කිරීමට, හෝ VIP ලබා ගැනීමට ප්‍රථමයෙන් පහත **Main Channel** සහ **Backup Channel** යන දෙකටම Join වන්න.\n"
            "*(මෙය අවශ්‍ය වන්නේ පළමු වතාවට පමණි)*",
            reply_markup=markup
        )
        return

    # Once verified, unlock the requested content
    if param:
        if param.startswith("watch_"):
            msg_id = param.split("_")[1]
            watch_url = f"{BASE_URL}/watch/{msg_id}"
            await message.reply_text(
                "🎉 **සත්‍යාපනය සාර්ථකයි! චිත්‍රපටය නැරඹීමට පහත Button එක ඔබන්න:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch Online Now", url=watch_url)]])
            )
            return

        elif param.startswith("dl_"):
            msg_id = param.split("_")[1]
            dl_url = f"{BASE_URL}/download/{msg_id}"
            await message.reply_text(
                "🎉 **සත්‍යාපනය සාර්ථකයි! චිත්‍රපටය බාගත කිරීමට පහත Button එක ඔබන්න:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download Movie Now", url=dl_url)]])
            )
            return

        elif param.startswith("buy_"):
            msg_id = param.split("_")[1]
            await send_stars_invoice(
                chat_id=message.chat.id,
                title="Direct Movie File",
                description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
                payload=f"single_{msg_id}",
                stars=SINGLE_STAR_PRICE
            )
            return

        elif param == "vip":
            await send_stars_invoice(
                chat_id=message.chat.id,
                title="VIP Membership (30 Days)",
                description="Cinex LK VIP Channel එකට දින 30ක ප්‍රවේශය (No Ads + Direct Files).",
                payload="vip_sub",
                stars=VIP_STAR_PRICE
            )
            return

    await message.reply_text("👋 **සාදරයෙන් පිළිගන්නවා!**\nඔබට අවශ්‍ය Movie එකේ නම type කර search කරන්න.")

@app.on_message(filters.text & filters.incoming & filters.private & ~filters.command(["start", "help"]))
async def handle_search(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons()
        await message.reply_text(
            "🔒 **චිත්‍රපට සෙවීමට පෙර අපගේ Channels වලට එක්වන්න:**",
            reply_markup=markup
        )
        return

    query = message.text.strip()
    regex = {"file_name": {"$regex": re.escape(query), "$options": "i"}}
    
    cursor = files_col.find(regex).limit(10)
    raw_results = await cursor.to_list(length=10)

    if not raw_results:
        await message.reply_text("❌ Movie එක හමු නොවීය. නම නිවැරදිව type කරන්න.")
        return

    seen_names = set()
    unique_results = []
    for f in raw_results:
        name = f.get("file_name", "")
        if name not in seen_names:
            seen_names.add(name)
            unique_results.append(f)
        if len(unique_results) >= 3:
            break

    for file in unique_results:
        size_mb = round(file["file_size"] / (1024 * 1024), 2)
        msg_id = file["message_id"]
        watch_url = f"{BASE_URL}/watch/{msg_id}"
        dl_url = f"{BASE_URL}/download/{msg_id}"

        caption = f"🎬 **{file['file_name']}**\n📦 **Size:** `{size_mb} MB`\n\n👇 **නැරඹීමට හෝ බාගත කිරීමට තෝරන්න:**"
        buttons = [
            [InlineKeyboardButton("🌐 Watch Online (Fast Player)", url=watch_url)],
            [InlineKeyboardButton("📥 Fast Download (Ads)", url=dl_url)],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️ / Rs. 20)", callback_data=f"buy_single_{msg_id}"),
                InlineKeyboardButton("👑 Buy VIP Pass (No Ads)", callback_data="buy_vip_pass")
            ]
        ]
        await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^buy_single_"))
async def pay_single(client: Client, callback: CallbackQuery):
    msg_id = callback.data.split("_")[2]
    await callback.answer()
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="Direct Movie File",
        description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
        payload=f"single_{msg_id}",
        stars=SINGLE_STAR_PRICE
    )

@app.on_callback_query(filters.regex(r"^buy_vip_pass$"))
async def pay_vip(client: Client, callback: CallbackQuery):
    await callback.answer()
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="VIP Membership (30 Days)",
        description="Cinex LK VIP Channel එකට දින 30ක ප්‍රවේශය (No Ads + Direct Files).",
        payload="vip_sub",
        stars=VIP_STAR_PRICE
    )

@app.on_raw_update()
async def raw_update_handler(client: Client, update, users, chats):
    if update.__class__.__name__ == "UpdateBotPrecheckoutQuery":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"pre_checkout_query_id": str(update.query_id), "ok": True})

@app.on_message(payment_filter)
async def payment_success(client: Client, message: Message):
    payload = message.successful_payment.invoice_payload

    if payload.startswith("single_"):
        msg_id = int(payload.split("_")[1])
        await message.reply_text("🎉 **ගෙවීම සාර්ථකයි!** මෙන්න Movie එක:")
        await send_tg_api_copy(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)

    elif payload == "vip_sub":
        user_id = message.from_user.id
        expiry_date = datetime.utcnow() + timedelta(days=30)

        await vip_users_col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "expiry_date": expiry_date, "joined_at": datetime.utcnow()}},
            upsert=True
        )

        try:
            invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
            await message.reply_text(
                f"🎉 **ගෙවීම සාර්ථකයි! ඔබගේ VIP සාමාජිකත්වය දින 30කට සක්‍රිය විය.**\n\n"
                f"🔗 **ඔබගේ විශේෂ VIP Channel Link එක:**\n{invite.invite_link}\n\n"
                f"*(මෙම Link එකෙන් සම්බන්ධ විය හැක්කේ ඔබට පමණි. දින 30 කින් සාමාජිකත්වය අවසන් වේ.)*"
            )
        except Exception as inv_err:
            print(f"❌ Invite link creation error: {inv_err}")
            await message.reply_text("VIP Access සක්‍රිය විය! කරුණාකර Admin අමතන්න.")

# =========================================================
# 6. 24/7 SELF-PING & KEEP-ALIVE BACKGROUND WORKER
# =========================================================
async def keep_alive_self_ping():
    await asyncio.sleep(15)
    while True:
        try:
            if BASE_URL:
                async with aiohttp.ClientSession() as session:
                    async with session.get(BASE_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            print("💓 Keep-Alive Ping Successful (Render Sleep Prevented).")
        except Exception as ping_err:
            print(f"⚠️ Keep-Alive Ping Warning: {ping_err}")

        await asyncio.sleep(240)

# =========================================================
# 7. SERVER STARTUP & RUNNER
# =========================================================
async def main():
    await app.start()
    me = await app.get_me()
    print(f"🤖 Bot Started Successfully as @{me.username}")

    # Force load and cache Storage Channel peer access hash
    try:
        await app.resolve_peer(STORAGE_CHANNEL)
        print("🎉 Storage Channel Peer Access Hash Loaded Successfully!")
    except Exception as pe:
        print(f"⚠️ Storage Peer Startup Warning: {pe}")

    asyncio.create_task(vip_expiry_checker())
    asyncio.create_task(keep_alive_self_ping())

    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web Server live on port {PORT}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
