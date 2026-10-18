import os
import re
import io
import random
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
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid, RPCError
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

STORAGE_INVITE_LINK = os.environ.get("STORAGE_INVITE_LINK", "").strip()

# Admin & Pricing Configurations
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "0"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").replace("@", "")

VIP_STAR_PRICE = int(os.environ.get("VIP_STAR_PRICE", "250"))
VIP_LKR_PRICE = int(os.environ.get("VIP_LKR_PRICE", "1000"))
SINGLE_STAR_PRICE = int(os.environ.get("SINGLE_STAR_PRICE", "5"))

BANK_DETAILS = os.environ.get(
    "BANK_DETAILS",
    "🏦 **Bank:** Commercial Bank\n"
    "👤 **Name:** Cinex LK Admin\n"
    "💳 **Account No:** 8001234567\n"
    "🏢 **Branch:** Colombo"
)

BOT_USERNAME = os.environ.get("BOT_USERNAME", "").replace("@", "")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "").strip()

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
MONETAG_STREAM_LINK = os.environ.get("MONETAG_STREAM_LINK", "")
ADSTERRA_DIRECT_LINK = os.environ.get("ADSTERRA_DIRECT_LINK", "")
PORT = int(os.environ.get("PORT", "8080"))

# Auto-delete duration for direct files: 24 Hours = 86400 seconds (දවසක Countdown Timer)
AUTO_DELETE_DURATION = int(os.environ.get("AUTO_DELETE_DURATION", "86400"))

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
peers_col = db_client["MovieDB"]["channel_peers"]
manual_orders_col = db_client["MovieDB"]["manual_orders"]
requests_col = db_client["MovieDB"]["movie_requests"]

# =========================================================
# PERMANENT PEER DATABASE RESOLVER
# =========================================================
async def save_peer_to_db(chat_id: int, access_hash: int):
    try:
        raw_id = int(str(chat_id).replace("-100", "").replace("-", ""))
        await peers_col.update_one(
            {"chat_id": raw_id},
            {"$set": {"chat_id": raw_id, "access_hash": access_hash, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        try:
            await app.storage.update_peers([(raw_id, access_hash, "channel", "", "")])
        except Exception as storage_err:
            print(f"⚠️ Storage peer note: {storage_err}")
        print(f"💾 Storage Peer (ID: {raw_id}) Hash registered and saved!")
    except Exception as e:
        print(f"⚠️ DB save peer error: {e}")

async def restore_storage_peer():
    try:
        raw_id = int(str(STORAGE_CHANNEL).replace("-100", "").replace("-", ""))
        doc = await peers_col.find_one({"chat_id": raw_id})

        if doc and "access_hash" in doc:
            try:
                await app.storage.update_peers([(raw_id, doc["access_hash"], "channel", "", "")])
                return True
            except Exception as e:
                print(f"⚠️ Storage local restore warning: {e}")
    except Exception as e:
        print(f"⚠️ Mongo peer restore warning: {e}")

    if STORAGE_INVITE_LINK:
        try:
            chat = await app.get_chat(STORAGE_INVITE_LINK)
            if chat:
                peer = await app.resolve_peer(chat.id)
                if hasattr(peer, "access_hash"):
                    await save_peer_to_db(peer.channel_id, peer.access_hash)
                    return True
        except Exception as inv_err:
            print(f"⚠️ Invite link check warning: {inv_err}")

    return False

# =========================================================
# DIRECT TELEGRAM BOT API CALLS
# =========================================================
async def send_tg_api_post(chat_id, text, reply_markup=None, photo_file_id=None):
    try:
        async with aiohttp.ClientSession() as session:
            target = int(chat_id) if str(chat_id).lstrip("-").isdigit() else str(chat_id)
            if photo_file_id:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": target,
                    "photo": photo_file_id,
                    "caption": text,
                    "parse_mode": "Markdown"
                }
            else:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": target,
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
        to_target = int(chat_id) if str(chat_id).lstrip("-").isdigit() else str(chat_id)
        from_target = int(from_chat_id) if str(from_chat_id).lstrip("-").isdigit() else str(from_chat_id)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
        payload = {
            "chat_id": to_target,
            "from_chat_id": from_target,
            "message_id": int(message_id)
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Direct Bot API Copy Error: {e}")
        return {"ok": False, "description": str(e)}

async def send_stars_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
        data = {
            "chat_id": int(chat_id),
            "title": title,
            "description": description,
            "payload": payload,
            "currency": "XTR",
            "prices": [{"label": title, "amount": int(stars)}]
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Stars Invoice Error: {e}")

payment_filter = filters.create(lambda _, __, m: bool(getattr(m, "successful_payment", None)))

# =========================================================
# AUTO-DELETE BACKGROUND WORKER (DAY / 24-HOUR TIMER)
# =========================================================
async def auto_delete_file_task(chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id=chat_id, message_ids=message_ids)
        await app.send_message(
            chat_id=chat_id,
            text="🗑️ **ප්‍රකාශන හිමිකම් ආරක්ෂාව (Copyright Protection) හේතුවෙන් පෙර එවන ලද වීඩියෝ පටය පැය 24ක් අවසානයේ ස්වයංක්‍රීයව ඉවත් කරන ලදී.**"
        )
    except Exception as e:
        print(f"⚠️ Auto delete error for chat {chat_id}: {e}")

async def send_file_with_auto_delete(chat_id: int, from_chat_id, message_id: int):
    copy_res = await send_tg_api_copy(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
    sent_msg_id = None
    if copy_res.get("ok"):
        sent_msg_id = copy_res.get("result", {}).get("message_id")
    else:
        try:
            target_id = int(from_chat_id) if str(from_chat_id).lstrip("-").isdigit() else from_chat_id
            m = await app.copy_message(chat_id=chat_id, from_chat_id=target_id, message_id=message_id)
            sent_msg_id = m.id
        except Exception as e:
            print(f"⚠️ Fallback copy error: {e}")

    if sent_msg_id:
        warn_msg = await app.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ **අවවාදයයි (Important Note):**\n"
                f"ප්‍රකාශන හිමිකම් ආරක්ෂාව හේතුවෙන් මෙම File එක තවත් **පැය 24 කින් (දින 1කින්) ස්වයංක්‍රීයව මැකී යනු ඇත.**\n\n"
                "කරුණාකර දැන්ම මෙය ඔබගේ **Saved Messages** වෙත Forward කර හෝ Save කරගන්න!"
            )
        )
        asyncio.create_task(auto_delete_file_task(chat_id, [sent_msg_id, warn_msg.id], AUTO_DELETE_DURATION))

# =========================================================
# DUAL CHANNEL VERIFICATION SYSTEM
# =========================================================
async def is_member(client: Client, chat_target, user_id: int) -> bool:
    if not chat_target:
        return True
    try:
        member = await client.get_chat_member(chat_target, user_id)
        status = str(member.status).lower()
        if any(s in status for s in ["member", "administrator", "owner", "restricted"]):
            return True
        return False
    except UserNotParticipant:
        return False
    except (ChatAdminRequired, PeerIdInvalid):
        return True
    except RPCError:
        return True
    except Exception:
        return True

async def check_user_access(client: Client, user_id: int) -> bool:
    try:
        user_record = await bot_users_col.find_one({"user_id": user_id})
        if user_record and user_record.get("fsub_verified"):
            return True

        in_main = await is_member(client, MAIN_CHANNEL, user_id)
        in_backup = await is_member(client, BACKUP_CHANNEL, user_id)

        if in_main and in_backup:
            await bot_users_col.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "fsub_verified": True, "verified_at": datetime.utcnow()}},
                upsert=True
            )
            return True
        return False
    except Exception as e:
        print(f"⚠️ check_user_access error: {e}")
        return True

async def get_dual_fsub_buttons(client: Client, start_param: str = "") -> InlineKeyboardMarkup:
    buttons = []
    
    if MAIN_CHANNEL:
        main_url = None
        if isinstance(MAIN_CHANNEL, str) and MAIN_CHANNEL.startswith("@"):
            main_url = f"https://t.me/{MAIN_CHANNEL.replace('@', '')}"
        else:
            try:
                chat = await client.get_chat(MAIN_CHANNEL)
                main_url = chat.invite_link or (await client.export_chat_invite_link(MAIN_CHANNEL))
            except Exception:
                pass
        if main_url:
            buttons.append([InlineKeyboardButton("📢 Join Main Channel", url=main_url)])

    if BACKUP_CHANNEL:
        backup_url = None
        if isinstance(BACKUP_CHANNEL, str) and BACKUP_CHANNEL.startswith("@"):
            backup_url = f"https://t.me/{BACKUP_CHANNEL.replace('@', '')}"
        else:
            try:
                chat = await client.get_chat(BACKUP_CHANNEL)
                backup_url = chat.invite_link or (await client.export_chat_invite_link(BACKUP_CHANNEL))
            except Exception:
                pass
        if backup_url:
            buttons.append([InlineKeyboardButton("🛡️ Join Backup Channel", url=backup_url)])

    callback_data = f"verify_{start_param}" if start_param else "verify_root"
    buttons.append([InlineKeyboardButton("🔄 Verify & Unlock", callback_data=callback_data)])
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
# NOTIFY USERS ON MOVIE REQUEST COMPLETION
# =========================================================
async def notify_requested_users(client: Client, file_name: str, msg_id: int):
    try:
        clean_title, _ = parse_movie_query(file_name)
        if not clean_title or len(clean_title) < 3:
            return

        regex = re.compile(rf"\b{re.escape(clean_title)}\b", re.IGNORECASE)
        pending_reqs = await requests_col.find({"movie_name": {"$regex": regex}, "status": "pending"}).to_list(length=100)

        for req in pending_reqs:
            user_id = req.get("user_id")
            if not user_id:
                continue

            watch_bot_url = f"https://t.me/{BOT_USERNAME}?start=watch_{msg_id}"
            dl_bot_url = f"https://t.me/{BOT_USERNAME}?start=dl_{msg_id}"

            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=watch_bot_url), InlineKeyboardButton("📥 Download", url=dl_bot_url)]
            ])

            text = (
                f"🎉 **සුභ ආරංචියක්! ඔබ කලින් ඉල්ලූ චිත්‍රපටය දැන් එක් කර ඇත.**\n\n"
                f"🎬 **චිත්‍රපටය:** `{file_name}`\n\n"
                f"නැරඹීමට හෝ බාගත කිරීමට පහත Buttons භාවිතා කරන්න."
            )

            try:
                await client.send_message(chat_id=user_id, text=text, reply_markup=btn)
            except Exception:
                pass

            await requests_col.update_one({"_id": req["_id"]}, {"$set": {"status": "fulfilled", "fulfilled_at": datetime.utcnow()}})
            print(f"🔔 Notified requester {user_id} for movie {clean_title}")

    except Exception as e:
        print(f"⚠️ notify_requested_users error: {e}")

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

        await restore_storage_peer()

        target_id = int(STORAGE_CHANNEL) if str(STORAGE_CHANNEL).lstrip("-").isdigit() else STORAGE_CHANNEL
        msg = await app.get_messages(target_id, msg_id)
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
# 2. AUTO-POST TO MAIN CHANNEL (HANDLES MESSAGES IN CHANNELS)
# =========================================================

@app.on_message((filters.document | filters.video) & (filters.channel | filters.group))
async def handle_storage_upload(client: Client, message: Message):
    try:
        if not message.chat:
            return

        chat_id_clean = str(message.chat.id).replace("-100", "").replace("-", "")
        storage_id_clean = str(STORAGE_CHANNEL).replace("-100", "").replace("-", "")

        # Only process files uploaded to the configured storage channel
        if chat_id_clean != storage_id_clean:
            return

        print(f"\n📥 [Storage Channel] New File Upload Detected! Message ID: {message.id}")

        try:
            peer = await client.resolve_peer(message.chat.id)
            if hasattr(peer, "access_hash"):
                await save_peer_to_db(peer.channel_id, peer.access_hash)
        except Exception as p_err:
            print(f"⚠️ Resolve peer error on upload: {p_err}")

        media = message.document or message.video
        if not media:
            return

        file_name = media.file_name or "Unknown Movie"
        size_mb = round(media.file_size / (1024 * 1024), 2)
        msg_id = message.id

        print(f"📦 Processing File: {file_name} ({size_mb} MB)")

        imdb = await fetch_imdb_data(file_name)
        imdb_rating = imdb.get('imdbRating', 'N/A') if imdb else 'N/A'

        try:
            await files_col.update_one(
                {"file_name": file_name},
                {"$set": {
                    "file_name": file_name,
                    "file_size": media.file_size,
                    "message_id": msg_id,
                    "imdb_rating": imdb_rating,
                    "created_at": datetime.utcnow()
                }},
                upsert=True
            )
        except Exception as db_err:
            print(f"❌ DB Error: {db_err}")

        watch_bot_url = f"https://t.me/{BOT_USERNAME}?start=watch_{msg_id}"
        dl_bot_url = f"https://t.me/{BOT_USERNAME}?start=dl_{msg_id}"
        buy_stars_url = f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"
        vip_buy_url = f"https://t.me/{BOT_USERNAME}?start=vip"

        main_buttons = [
            [InlineKeyboardButton("🌐 Watch Online", url=watch_bot_url)],
            [InlineKeyboardButton("📥 Fast Download (Ads)", url=dl_bot_url)],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️)", url=buy_stars_url),
                InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", url=vip_buy_url)
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

        # Trigger auto-notification to users who requested this movie
        asyncio.create_task(notify_requested_users(client, file_name, msg_id))

    except Exception as general_err:
        print(f"❌ Storage Handler Error: {general_err}")

# =========================================================
# 3. AUTO-KICK EXPIRED VIP USERS & 3-DAY RENEWAL REMINDER
# =========================================================
async def vip_expiry_checker():
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.utcnow()

            # 1. SEND 3-DAY EXPIRY REMINDER
            reminder_threshold = now + timedelta(days=3)
            reminder_users = await vip_users_col.find({
                "expiry_date": {"$lte": reminder_threshold, "$gt": now},
                "reminder_sent": {"$ne": True}
            }).to_list(length=50)

            for u in reminder_users:
                user_id = u.get("user_id")
                if not user_id:
                    continue
                try:
                    rem_markup = InlineKeyboardMarkup([[InlineKeyboardButton("👑 Renew VIP Now", callback_data="buy_vip_pass")]])
                    await app.send_message(
                        chat_id=user_id,
                        text=(
                            "⏳ **Cinex LK VIP Renewal Reminder**\n\n"
                            "ඔබගේ VIP සාමාජිකත්වය තව **දින 3කින් අවසන් වේ.**\n"
                            "අඛණ්ඩව Direct Files සහ No-Ads Player භුක්ති විඳීමට දැන්ම ඔබගේ සාමාජිකත්වය Renew කරගන්න!"
                        ),
                        reply_markup=rem_markup
                    )
                    await vip_users_col.update_one({"_id": u["_id"]}, {"$set": {"reminder_sent": True}})
                    print(f"📩 Sent 3-day renewal reminder to user: {user_id}")
                except Exception as rem_err:
                    print(f"⚠️ Reminder send error {user_id}: {rem_err}")

            # 2. AUTO-KICK EXPIRED MEMBERS
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
# 4. FORWARD-TO-VIP CONVERTER & STORAGE PEER REGISTRATION
# =========================================================

@app.on_message(filters.private & filters.forwarded)
async def manual_share_to_vip(client: Client, message: Message):
    try:
        fwd_chat = message.forward_from_chat

        if fwd_chat and str(fwd_chat.id).replace("-100", "").replace("-", "") == str(STORAGE_CHANNEL).replace("-100", "").replace("-", ""):
            peer = await client.resolve_peer(fwd_chat.id)
            if hasattr(peer, "access_hash"):
                await save_peer_to_db(peer.channel_id, peer.access_hash)
            await message.reply_text(f"🎉 **Storage Channel Access Hash Saved to MongoDB!**\n\nTitle: `{fwd_chat.title}`\nID: `{fwd_chat.id}`\n\nදැන් Web Streaming සහ Fast Download 100% ක් වැඩ කරනු ඇත.")
            return

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
# 5. VIP PAYMENT SELECTION & ADMIN NOTIFICATIONS
# =========================================================

def get_vip_selection_markup():
    approx_star_lkr = int(VIP_STAR_PRICE * 6.8)
    savings = max(0, approx_star_lkr - VIP_LKR_PRICE)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"⭐ Pay with Telegram Stars ({VIP_STAR_PRICE} ⭐️ / ~Rs. {approx_star_lkr})", 
            callback_data="pay_vip_stars"
        )],
        [InlineKeyboardButton(
            f"🇱🇰 Bank Transfer - Rs. {VIP_LKR_PRICE} (Save Rs. {savings} 🔥)", 
            callback_data="pay_vip_bank"
        )]
    ])

@app.on_callback_query(filters.regex(r"^buy_vip_pass$"))
async def vip_selection_callback(client: Client, callback: CallbackQuery):
    await callback.answer()
    text = (
        "👑 **Cinex LK VIP Pass (Monthly - 30 Days)**\n\n"
        "✨ **VIP වරප්‍රසාද:**\n"
        "• Direct Files (Bot එකෙන්ම කෙලින්ම Movies ලබාගැනීම)\n"
        "• කිසිදු දැන්වීමක් නොමැත (100% No Ads Online Player & Fast Download)\n"
        "• VIP Channel එකට දින 30ක අඛණ්ඩ ප්‍රවේශය\n\n"
        "👇 **ඔබ ගෙවීම් කිරීමට බලාපොරොත්තු වන ක්‍රමය තෝරන්න:**"
    )
    await callback.message.reply_text(text, reply_markup=get_vip_selection_markup())

@app.on_callback_query(filters.regex(r"^pay_vip_stars$"))
async def pay_vip_stars_handler(client: Client, callback: CallbackQuery):
    await callback.answer()
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="VIP Membership (30 Days)",
        description="Cinex LK VIP Channel එකට දින 30ක ප්‍රවේශය (No Ads + Direct Files).",
        payload="vip_sub",
        stars=VIP_STAR_PRICE
    )

@app.on_callback_query(filters.regex(r"^pay_vip_bank$"))
async def pay_vip_bank_handler(client: Client, callback: CallbackQuery):
    user = callback.from_user
    user_id = user.id
    username = f"@{user.username}" if user.username else "No Username"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    ref_code = f"CX-{random.randint(10000, 99999)}"

    await manual_orders_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "username": username,
            "name": full_name,
            "ref_code": ref_code,
            "amount": VIP_LKR_PRICE,
            "status": "pending",
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )

    if ADMIN_USER_ID:
        admin_alert = (
            "🔔 **නව Bank Payment ඉල්ලීමක්!**\n\n"
            f"👤 **පරිශීලකයා:** {full_name} ({username})\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"🔑 **Reference Code:** `{ref_code}`\n"
            f"💰 **මුදල:** `Rs. {VIP_LKR_PRICE}`\n"
            f"⏰ **වේලාව:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`\n\n"
            f"📌 *User slip එක එවූ පසු verify කර VIP දීමට පහත command එක ඔබන්න:*\n"
            f"`/addvip {user_id}`"
        )
        try:
            await client.send_message(chat_id=ADMIN_USER_ID, text=admin_alert)
        except Exception as alert_err:
            print(f"⚠️ Failed to send admin payment alert: {alert_err}")

    admin_link = f"https://t.me/{ADMIN_USERNAME}" if ADMIN_USERNAME else None

    text = (
        "🇱🇰 **බැංකු තැන්පතු මඟින් VIP ලබාගැනීම:**\n\n"
        f"💰 **ගෙවිය යුතු මුදල:** `Rs. {VIP_LKR_PRICE}`\n\n"
        f"{BANK_DETAILS}\n\n"
        f"⚠️ **අනිවාර්යයි (Very Important):**\n"
        f"මුදල් තැන්පත් කරන විට / Online Transfer කරන විට Reference හෝ Remarks සඳහා පහත ඔබගේ Unique Code එක ඇතුළත් කරන්න:\n"
        f"🔑 **ඔබගේ Reference Code එක:** `{ref_code}`\n\n"
        f"📸 මුදල් ගෙවූ පසු, **ලැබුණු Payment Slip පත හෝ Screenshot එක** ඔබගේ User ID (`{user_id}`) සමඟ පහත Admin ගිණුමට Telegram මඟින් එවන්න."
    )

    buttons = []
    if admin_link:
        buttons.append([InlineKeyboardButton("📩 Send Slip to Admin", url=admin_link)])

    await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

# ADMIN COMMAND: /addvip <USER_ID>
@app.on_message(filters.command("addvip") & filters.private)
async def admin_add_vip_handler(client: Client, message: Message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ **භාවිතා කරන ආකාරය:** `/addvip <USER_ID>`\n(උදා: `/addvip 123456789`)")
        return

    try:
        target_user_id = int(args[1].strip())
    except ValueError:
        await message.reply_text("❌ වැරදි User ID එකකි. අංකයක් පමණක් ඇතුළත් කරන්න.")
        return

    expiry_date = datetime.utcnow() + timedelta(days=30)
    await vip_users_col.update_one(
        {"user_id": target_user_id},
        {"$set": {"user_id": target_user_id, "expiry_date": expiry_date, "joined_at": datetime.utcnow(), "reminder_sent": False}},
        upsert=True
    )

    await manual_orders_col.update_one(
        {"user_id": target_user_id},
        {"$set": {"status": "approved", "approved_at": datetime.utcnow()}}
    )

    try:
        invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
        await client.send_message(
            chat_id=target_user_id,
            text=(
                "🎉 **ඔබගේ ගෙවීම තහවුරු විය! Cinex LK VIP සාමාජිකත්වය දින 30කට සක්‍රිය කරන ලදී.**\n\n"
                f"🔗 **ඔබගේ විශේෂ VIP Channel Link එක:**\n{invite.invite_link}\n\n"
                "*(මෙම Link එකෙන් සම්බන්ධ විය හැක්කේ ඔබට පමණි. දින 30 කින් සාමාජිකත්වය ස්වයංක්‍රීයව අවසන් වේ.)*"
            )
        )
        await message.reply_text(f"✅ User `{target_user_id}` හට සාර්ථකව VIP Access ලබා දුනි. (දින 30 කින් Auto-Kick වේ)")
    except Exception as e:
        await message.reply_text(f"⚠️ Invite link සැකසීමේ දෝෂයකි: {e}")

# =========================================================
# 6. MOVIE REQUEST SYSTEM
# =========================================================
@app.on_message(filters.command("request") & filters.private)
async def handle_movie_request(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට ඉල්ලීම් කිරීමට පෙර අපගේ Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("📝 **භාවිතා කරන ආකාරය:** `/request <Movie Name>`\nඋදාහරණයක් ලෙස: `/request Avatar 2`")
        return

    movie_name = args[1].strip()
    user = message.from_user
    username = f"@{user.username}" if user.username else "No Username"

    await requests_col.insert_one({
        "user_id": user.id,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "username": username,
        "movie_name": movie_name,
        "status": "pending",
        "created_at": datetime.utcnow()
    })

    await message.reply_text(
        f"✅ **ඔබගේ චිත්‍රපට ඉල්ලීම සාර්ථකව සටහන් විය!**\n\n"
        f"🎬 **ඉල්ලූ චිත්‍රපටය:** `{movie_name}`\n\n"
        "අප විසින් මෙම චිත්‍රපටය Storage එකට Upload කළ සැනින් ඔබට Bot මඟින් ස්වයංක්‍රීයව Notification පණිවිඩයක් ලැබෙනු ඇත."
    )

    if ADMIN_USER_ID:
        admin_req_alert = (
            "📥 **නව Movie Request එකක්!**\n\n"
            f"👤 **පරිශීලකයා:** {user.first_name} ({username})\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"🎬 **Movie:** `{movie_name}`"
        )
        try:
            await client.send_message(chat_id=ADMIN_USER_ID, text=admin_req_alert)
        except Exception:
            pass

# =========================================================
# 7. TRENDING MOVIES FEATURE (/trending)
# =========================================================
@app.on_message(filters.command("trending") & filters.private)
async def handle_trending(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **මෙම පහසුකම භාවිතා කිරීමට Channels වලට Join වන්න:**", reply_markup=markup)
        return

    cursor = files_col.find({}).sort("_id", -1).limit(5)
    top_movies = await cursor.to_list(length=5)

    if not top_movies:
        await message.reply_text("දැනට Movies කිසිවක් හමු නොවීය.")
        return

    text = "🔥 **Cinex LK Trending Movies (මේ සතියේ වැඩිපුරම නැරඹූ):**\n\n"
    buttons = []

    for idx, f in enumerate(top_movies, 1):
        name = f.get("file_name", "Movie")
        msg_id = f.get("message_id")
        rating = f.get("imdb_rating", "N/A")
        clean_name, _ = parse_movie_query(name)

        text += f"{idx}. 🎬 **{clean_name}** (⭐ `{rating}/10`)\n"
        buttons.append([
            InlineKeyboardButton(f"▶️ {clean_name[:24]}", url=f"{BASE_URL}/watch/{msg_id}"),
            InlineKeyboardButton("📥 Get", url=f"https://t.me/{BOT_USERNAME}?start=dl_{msg_id}")
        ])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# =========================================================
# 8. COMPLETE MOVIE LIST WITH PAGINATION (/movielist, /movies)
# =========================================================
@app.on_message(filters.command(["movielist", "movies"]) & filters.private)
async def handle_movie_list(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට ලැයිස්තුව බැලීමට අපගේ Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    await send_movie_list_page(message.chat.id, page=1)

async def send_movie_list_page(chat_id: int, page: int = 1, edit_message_id: int = None):
    PAGE_SIZE = 10
    skip = (page - 1) * PAGE_SIZE
    total_movies = await files_col.count_documents({})
    total_pages = max(1, (total_movies + PAGE_SIZE - 1) // PAGE_SIZE)

    cursor = files_col.find({}).sort("file_name", 1).skip(skip).limit(PAGE_SIZE)
    movies = await cursor.to_list(length=PAGE_SIZE)

    if not movies:
        text = "📁 **දැනට චිත්‍රපට කිසිවක් එක් කර නොමැත.**"
        if edit_message_id:
            await app.edit_message_text(chat_id=chat_id, message_id=edit_message_id, text=text)
        else:
            await app.send_message(chat_id=chat_id, text=text)
        return

    text = f"📚 **Cinex LK චිත්‍රපට නාමාවලිය (Movies Library)**\n"
    text += f"📊 මුළු චිත්‍රපට ගණන: `{total_movies}` | පිටුව: `{page}/{total_pages}`\n\n"

    buttons = []
    for idx, f in enumerate(movies, start=skip + 1):
        name = f.get("file_name", "Unknown")
        msg_id = f.get("message_id")
        clean_name, year = parse_movie_query(name)
        display_label = f"{clean_name} ({year})" if year else clean_name

        text += f"`{idx}.` 🎬 **{display_label}**\n"
        buttons.append([InlineKeyboardButton(f"📥 {display_label[:30]}", url=f"https://t.me/{BOT_USERNAME}?start=dl_{msg_id}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"mlist_{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"mlist_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons)
    if edit_message_id:
        try:
            await app.edit_message_text(chat_id=chat_id, message_id=edit_message_id, text=text, reply_markup=markup)
        except Exception:
            pass
    else:
        await app.send_message(chat_id=chat_id, text=text, reply_markup=markup)

@app.on_callback_query(filters.regex(r"^mlist_"))
async def movie_list_nav_callback(client: Client, callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.split("_")[1])
    await send_movie_list_page(chat_id=callback.message.chat.id, page=page, edit_message_id=callback.message.id)

# =========================================================
# 9. BOT COMMANDS & GENERAL ACTIONS
# =========================================================

COMMANDS_HELP_TEXT = (
    "📌 **Cinex LK Bot Commands & Features (උපදෙස් මාලාව):**\n\n"
    "🔍 **චිත්‍රපට සෙවීම:**\n"
    "ඕනෑම Movie එකක නම type කර එවන්න (උදා: `Avengers`)\n\n"
    "📚 **චිත්‍රපට ලැයිස්තුව:**\n"
    "▶️ `/movielist` හෝ `/movies` - අප සතු සියලු Movies පිටු වශයෙන් බැලීමට\n\n"
    "🔥 **Trending Movies:**\n"
    "▶️ `/trending` - මේ සතියේ ජනප්‍රියම චිත්‍රපට 5 බැලීමට\n\n"
    "📥 **චිත්‍රපට ඉල්ලීම:**\n"
    "▶️ `/request <Movie Name>` - ඔබට අවශ්‍ය චිත්‍රපටයක් Request කිරීමට\n\n"
    "👑 **VIP සාමාජිකත්වය:**\n"
    "▶️ `/start vip` - No-Ads Online Player & VIP Channel සඳහා"
)

@app.on_message(filters.command("help") & filters.private)
async def handle_help_cmd(client: Client, message: Message):
    await message.reply_text(COMMANDS_HELP_TEXT)

@app.on_callback_query(filters.regex(r"^verify_"))
async def callback_verify_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    param = callback.data.replace("verify_", "")
    if param == "root":
        param = ""

    if await check_user_access(client, user_id):
        await callback.answer("🎉 සුභ පැතුම්! ප්‍රවේශය සාර්ථකව Unlock විය.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass

        if param.startswith("watch_"):
            msg_id = param.split("_")[1]
            watch_url = f"{BASE_URL}/watch/{msg_id}"
            await client.send_message(
                chat_id=user_id,
                text="🎉 **සත්‍යාපනය සාර්ථකයි! චිත්‍රපටය නැරඹීමට පහත Button එක ඔබන්න:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch Online Now", url=watch_url)]])
            )
        elif param.startswith("dl_"):
            msg_id = param.split("_")[1]
            dl_url = f"{BASE_URL}/download/{msg_id}"
            await client.send_message(
                chat_id=user_id,
                text="🎉 **සත්‍යාපනය සාර්ථකයි! චිත්‍රපටය බාගත කිරීමට පහත Button එක ඔබන්න:**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download Movie Now", url=dl_url)]])
            )
        elif param.startswith("buy_"):
            msg_id = param.split("_")[1]
            await send_stars_invoice(
                chat_id=user_id,
                title="Direct Movie File",
                description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
                payload=f"single_{msg_id}",
                stars=SINGLE_STAR_PRICE
            )
        elif param == "vip":
            text = "👑 **Cinex LK VIP Pass (Monthly - 30 Days)**\n\n👇 **ගෙවීම් ක්‍රමය තෝරන්න:**"
            await client.send_message(chat_id=user_id, text=text, reply_markup=get_vip_selection_markup())
        else:
            await client.send_message(chat_id=user_id, text=f"👋 **සාදරයෙන් පිළිගන්නවා!**\n\n{COMMANDS_HELP_TEXT}")
    else:
        await callback.answer("❌ ඔබ තවමත් Channels 2ටම Join වී නොමැත! කරුණාකර Join වී නැවත ඔබන්න.", show_alert=True)

@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    text = message.text
    param = text.split()[1] if len(text.split()) > 1 else ""

    if param.startswith("vipfile_"):
        msg_id = int(param.split("_")[1])
        await message.reply_text("👑 **VIP Direct File:** මෙන්න ඔබගේ Movie එක:")
        await send_file_with_auto_delete(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)
        return

    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client, param)
        await message.reply_text(
            "🔒 **ප්‍රවේශය සත්‍යාපනය කර නොමැත! (Channel Verification)**\n\n"
            "චිත්‍රපට නැරඹීමට, බාගත කිරීමට, හෝ VIP ලබා ගැනීමට ප්‍රථමයෙන් පහත **Main Channel** සහ **Backup Channel** යන දෙකටම Join වන්න.\n"
            "*(මෙය අවශ්‍ය වන්නේ පළමු වතාවට පමණි)*",
            reply_markup=markup
        )
        return

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
            text = "👑 **Cinex LK VIP Pass (Monthly - 30 Days)**\n\n👇 **ගෙවීම් ක්‍රමය තෝරන්න:**"
            await message.reply_text(text, reply_markup=get_vip_selection_markup())
            return

    await message.reply_text(f"👋 **සාදරයෙන් පිළිගන්නවා!**\n\n{COMMANDS_HELP_TEXT}")

@app.on_message(filters.text & filters.incoming & filters.private & ~filters.command(["start", "help", "addvip", "request", "trending", "movielist", "movies"]))
async def handle_search(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
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
        await message.reply_text(
            "❌ **චිත්‍රපටය හමු නොවීය.**\n\n"
            "නම නිවැරදිව type කර නැවත උත්සාහ කරන්න. හෝ අපට එය Upload කිරීමට `/request <Movie Name>` හරහා Request එකක් දමන්න!"
        )
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
                InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", callback_data="buy_vip_pass")
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
        await send_file_with_auto_delete(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)

    elif payload == "vip_sub":
        user_id = message.from_user.id
        expiry_date = datetime.utcnow() + timedelta(days=30)

        await vip_users_col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "expiry_date": expiry_date, "joined_at": datetime.utcnow(), "reminder_sent": False}},
            upsert=True
        )

        try:
            invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
            await message.reply_text(
                f"🎉 **ගෙවීම සාර්ථකයි! ඔබගේ VIP සාමාජිකත්වය දින 30කට සක්‍රිය විය.**\n\n"
                f"🔗 **ඔබගේ විශේෂ VIP Channel Link එක:**\n{invite.invite_link}\n\n"
                "*(මෙම Link එකෙන් සම්බන්ධ විය හැක්කේ ඔබට පමණි. දින 30 කින් සාමාජිකත්වය අවසන් වේ.)*"
            )
        except Exception as inv_err:
            print(f"❌ Invite link creation error: {inv_err}")
            await message.reply_text("VIP Access සක්‍රිය විය! කරුණාකර Admin අමතන්න.")

# =========================================================
# 10. 24/7 SELF-PING & KEEP-ALIVE BACKGROUND WORKER
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
# 11. SERVER STARTUP & RUNNER
# =========================================================
async def main():
    await app.start()
    me = await app.get_me()
    print(f"🤖 Bot Started Successfully as @{me.username}")

    await restore_storage_peer()

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
