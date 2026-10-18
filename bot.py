import os
import re
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
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")

ADSTERRA_DIRECT_LINK = os.environ.get("ADSTERRA_DIRECT_LINK", "https://google.com").strip()
MONETAG_STREAM_LINK = os.environ.get("MONETAG_STREAM_LINK", os.environ.get("ADSTERRA_DIRECT_LINK", "https://google.com")).strip()

PORT = int(os.environ.get("PORT", "8080"))

FREE_USER_DELETE_DURATION = int(os.environ.get("FREE_USER_DELETE_DURATION", "3600")) # 1 Hour
VIP_USER_DELETE_DURATION = int(os.environ.get("VIP_USER_DELETE_DURATION", "21600")) # 6 Hours

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
manual_orders_col = db_client["MovieDB"]["manual_orders"]
requests_col = db_client["MovieDB"]["movie_requests"]
peers_col = db_client["MovieDB"]["channel_peers"]

verified_tokens = set()

# =========================================================
# HARDENED ANTI-POPUP-BLOCKER GATE HTML (0 BANDWIDTH)
# =========================================================
routes = web.RouteTableDef()

HARDENED_GATE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sponsor Verification - Cinex LK</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ margin:0; background:#0b1118; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color:white; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
        .box {{ background:#16222f; padding:30px 20px; border-radius:18px; text-align:center; max-width:360px; width:90%; border:1px solid #233446; box-shadow:0 12px 35px rgba(0,0,0,0.5); }}
        .badge {{ background:#233a50; color:#5da9e9; font-size:12px; font-weight:700; padding:6px 12px; border-radius:20px; display:inline-block; margin-bottom:15px; letter-spacing:1px; }}
        h2 {{ margin:0 0 10px; font-size:20px; }}
        p {{ color:#8ea2b5; font-size:13px; line-height:1.5; margin:0 0 20px; }}
        .circle {{ width:75px; height:75px; border-radius:50%; background:#0b1118; border:3px solid #5da9e9; display:flex; align-items:center; justify-content:center; margin:0 auto 20px; font-size:28px; font-weight:bold; color:#5da9e9; }}
        .btn {{ display:none; background:#2fa955; color:white; text-decoration:none; padding:14px; border-radius:12px; font-weight:bold; font-size:15px; width:100%; box-sizing:border-box; cursor:pointer; }}
        .start-btn {{ display:block; background:#3b82f6; color:white; text-decoration:none; padding:14px; border-radius:12px; font-weight:bold; font-size:15px; width:100%; box-sizing:border-box; border:none; cursor:pointer; margin-bottom:15px; }}
        .alert-box {{ display:none; background:#4a151b; border:1px solid #dc3545; padding:12px; border-radius:12px; color:#ffc9c9; margin-bottom:15px; font-size:12px; line-height:1.4; text-align:left; }}
    </style>
</head>
<body>
    <div class="box">
        <div class="badge">STEP {step} OF 2</div>
        <h2>Sponsor Verification</h2>
        
        <div class="alert-box" id="blockAlert">
            ⚠️ <b>Pop-up / AdBlock Blocked!</b><br>
            ඔබගේ Browser එක මඟින් Sponsor පිටුව Block කර ඇත. කරුණාකර URL Bar එක උඩ ඇති Pop-up icon එක ඔබා <b>"Always allow pop-ups"</b> ලබා දෙන්න (හෝ AdBlocker Off කරන්න).
        </div>

        <p id="msg">පහත නිල් පාට බොත්තම ඔබා Sponsor පිටුව විවෘත කරන්න. තත්පර 8ක් අවසානයේ Download Link එක ලැබෙනු ඇත.</p>
        
        <button id="openAdBtn" class="start-btn" onclick="startAdFlow()">🚀 Open Sponsor & Start (8s)</button>

        <div class="circle" id="count" style="display:none;">8</div>
        <a id="doneBtn" class="btn" href="https://t.me/{bot_username}?start={token}">✅ Return to Telegram Bot</a>
    </div>

    <script>
        const targetAd = "{ad_url}";
        let timerStarted = false;
        let sec = 8;

        function startAdFlow() {{
            // Attempt to open the ad window
            let adWindow = window.open(targetAd, '_blank');

            // Check if browser blocked the popup
            if (!adWindow || adWindow.closed || typeof adWindow.closed === 'undefined') {{
                document.getElementById('blockAlert').style.display = 'block';
                return;
            }}

            // If popup is successful, hide alert and start the countdown
            document.getElementById('blockAlert').style.display = 'none';
            document.getElementById('openAdBtn').style.display = 'none';
            document.getElementById('count').style.display = 'flex';
            document.getElementById('msg').innerText = 'කරුණාකර තත්පර 8ක් සම්පූර්ණ වන තෙක් රැඳී සිටින්න...';

            if (!timerStarted) {{
                timerStarted = true;
                const timer = setInterval(() => {{
                    sec--;
                    document.getElementById('count').innerText = sec;
                    if (sec <= 0) {{
                        clearInterval(timer);
                        fetch('/mark-token/{token}');
                        document.getElementById('count').style.display = 'none';
                        document.getElementById('msg').innerText = '🎉 සත්‍යාපනය සාර්ථකයි! පහත Button එක ඔබන්න.';
                        document.getElementById('doneBtn').style.display = 'block';
                    }}
                }}, 1000);
            }}
        }}
    </script>
</body>
</html>
"""

@routes.get("/")
async def root_ping(request):
    return web.Response(text="Cinex LK Engine Online", status=200)

@routes.get("/gate/step1/{user_id}/{msg_id}")
async def gate_step1(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok1_{user_id}_{msg_id}"
    html = HARDENED_GATE_HTML.format(
        step="1",
        ad_url=ADSTERRA_DIRECT_LINK,
        bot_username=BOT_USERNAME,
        token=token
    )
    return web.Response(text=html, content_type='text/html')

@routes.get("/gate/step2/{user_id}/{msg_id}")
async def gate_step2(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok2_{user_id}_{msg_id}"
    html = HARDENED_GATE_HTML.format(
        step="2",
        ad_url=MONETAG_STREAM_LINK,
        bot_username=BOT_USERNAME,
        token=token
    )
    return web.Response(text=html, content_type='text/html')

@routes.get("/mark-token/{token}")
async def mark_token(request):
    token = request.match_info['token']
    verified_tokens.add(token)
    return web.Response(text="OK", status=200)

# =========================================================
# PEER RESOLUTION FOR STORAGE
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
        except Exception:
            pass
    except Exception:
        pass

async def restore_storage_peer():
    try:
        raw_id = int(str(STORAGE_CHANNEL).replace("-100", "").replace("-", ""))
        doc = await peers_col.find_one({"chat_id": raw_id})
        if doc and "access_hash" in doc:
            try:
                await app.storage.update_peers([(raw_id, doc["access_hash"], "channel", "", "")])
            except Exception:
                pass
    except Exception:
        pass

# =========================================================
# TELEGRAM STARS INVOICE
# =========================================================
async def send_stars_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
    data = {
        "chat_id": int(chat_id),
        "title": title,
        "description": description,
        "payload": payload,
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": title, "amount": int(stars)}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
    except Exception as e:
        print(f"⚠️ Stars Invoice HTTP Error: {e}")
        return None

# =========================================================
# FILE SENDER WITH DYNAMIC TIMER (1 HOUR vs 6 HOURS)
# =========================================================
async def auto_delete_file_task(chat_id: int, message_ids: list, delay: int, delete_text: str):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id=chat_id, message_ids=message_ids)
        await app.send_message(chat_id=chat_id, text=delete_text)
    except Exception:
        pass

async def send_file_with_auto_delete(chat_id: int, message_id: int, is_vip: bool = False):
    await restore_storage_peer()
    target_storage = int(STORAGE_CHANNEL) if str(STORAGE_CHANNEL).lstrip("-").isdigit() else STORAGE_CHANNEL
    sent_msg = None

    delay = VIP_USER_DELETE_DURATION if is_vip else FREE_USER_DELETE_DURATION
    time_label = "පැය 6" if is_vip else "පැය 1"

    warn_text = (
        "⚡ **Auto-Download Started (ස්වයංක්‍රීයව බාගත වීම ආරම්භ විය):**\n\n"
        "🎬 මෙම වීඩියෝව ඔබගේ Telegram යෙදුම හරහා **පසුබිමින් Auto-Download වේ.**\n\n"
        f"⚠️ **අවවාදයයි:** ප්‍රකාශන හිමිකම් ආරක්ෂාව මත මෙම වීඩියෝව තවත් **{time_label} කින් මෙතැනින් ඉවත් කෙරේ.**\n\n"
        "📥 **Device එකටම Save කරගැනීමට:**\n"
        "වීඩියෝ පත උඩ තියෙන **තිත් 3 (Menu) ඔබා 'Save to Downloads' හෝ 'Save to Gallery'** ලබා දෙන්න. "
        "නැතහොත් ඔබගේ **Saved Messages** වෙත Share කර තබා ගන්න!"
    )
    delete_notification = f"🗑️ **ප්‍රකාශන හිමිකම් ආරක්ෂාව (Copyright Protection) හේතුවෙන් පෙර එවන ලද වීඩියෝ පටය {time_label} අවසානයේ Chat එකෙන් ඉවත් කරන ලදී.**"

    try:
        sent_msg = await app.copy_message(chat_id=chat_id, from_chat_id=target_storage, message_id=message_id)
    except Exception:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
        payload = {"chat_id": int(chat_id), "from_chat_id": int(str(STORAGE_CHANNEL)), "message_id": int(message_id)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    res = await resp.json()
                    if res.get("ok"):
                        sent_msg_id = res.get("result", {}).get("message_id")
                        warn_msg = await app.send_message(chat_id=chat_id, text=warn_text)
                        asyncio.create_task(auto_delete_file_task(chat_id, [sent_msg_id, warn_msg.id], delay, delete_notification))
                        return True
        except Exception:
            pass

    if sent_msg:
        warn_msg = await app.send_message(chat_id=chat_id, text=warn_text)
        asyncio.create_task(auto_delete_file_task(chat_id, [sent_msg.id, warn_msg.id], delay, delete_notification))
        return True
    else:
        await app.send_message(chat_id=chat_id, text="❌ **File එක Storage එකෙන් සොයා ගැනීමට නොහැකි විය.** කරුණාකර Admin අමතන්න.")
        return False

# =========================================================
# CHANNEL ACCESS & FSUB
# =========================================================
async def is_member(client: Client, chat_target, user_id: int) -> bool:
    if not chat_target:
        return True
    try:
        member = await client.get_chat_member(chat_target, user_id)
        status = str(member.status).lower()
        return any(s in status for s in ["member", "administrator", "owner", "restricted"])
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
    except Exception:
        return True

async def get_dual_fsub_buttons(client: Client, start_param: str = "") -> InlineKeyboardMarkup:
    buttons = []
    if MAIN_CHANNEL:
        main_url = f"https://t.me/{MAIN_CHANNEL.replace('@', '')}" if isinstance(MAIN_CHANNEL, str) and MAIN_CHANNEL.startswith("@") else None
        if not main_url:
            try:
                chat = await client.get_chat(MAIN_CHANNEL)
                main_url = chat.invite_link or (await client.export_chat_invite_link(MAIN_CHANNEL))
            except Exception:
                pass
        if main_url:
            buttons.append([InlineKeyboardButton("📢 Join Main Channel", url=main_url)])

    if BACKUP_CHANNEL:
        backup_url = f"https://t.me/{BACKUP_CHANNEL.replace('@', '')}" if isinstance(BACKUP_CHANNEL, str) and BACKUP_CHANNEL.startswith("@") else None
        if not backup_url:
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
# AUTO-POST STORAGE TO CHANNELS
# =========================================================
@app.on_message((filters.document | filters.video) & (filters.channel | filters.group))
async def handle_storage_upload(client: Client, message: Message):
    try:
        if not message.chat:
            return

        chat_id_clean = str(message.chat.id).replace("-100", "").replace("-", "")
        storage_id_clean = str(STORAGE_CHANNEL).replace("-100", "").replace("-", "")

        if chat_id_clean != storage_id_clean:
            return

        try:
            peer = await client.resolve_peer(message.chat.id)
            if hasattr(peer, "access_hash"):
                await save_peer_to_db(peer.channel_id, peer.access_hash)
        except Exception:
            pass

        media = message.document or message.video
        if not media:
            return

        file_name = media.file_name or "Unknown Movie"
        size_mb = round(media.file_size / (1024 * 1024), 2)
        msg_id = message.id

        await files_col.update_one(
            {"file_name": file_name},
            {"$set": {
                "file_name": file_name,
                "file_size": media.file_size,
                "message_id": msg_id,
                "created_at": datetime.utcnow()
            }},
            upsert=True
        )

        get_movie_ad_url = f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}"
        vip_direct_url = f"https://t.me/{BOT_USERNAME}?start=vipfile_{msg_id}"
        vip_buy_url = f"https://t.me/{BOT_USERNAME}?start=vip"

        main_buttons = [
            [InlineKeyboardButton("📥 Fast Download (Ads)", url=get_movie_ad_url)],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️)", url=f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"),
                InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", url=vip_buy_url)
            ]
        ]
        main_markup = InlineKeyboardMarkup(main_buttons)

        vip_markup = {
            "inline_keyboard": [
                [{"text": "⚡ Instant Download (Direct File)", "url": vip_direct_url}]
            ]
        }

        caption = f"🎬 **{file_name}**\n📦 **Size:** `{size_mb} MB`\n\n👇 **චිත්‍රපටය ලබාගැනීමට පහත Button එක ඔබන්න:**"

        if MAIN_CHANNEL:
            try:
                await client.send_message(chat_id=MAIN_CHANNEL, text=caption, reply_markup=main_markup)
            except Exception:
                pass

        if VIP_CHANNEL:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {"chat_id": str(VIP_CHANNEL), "text": caption, "reply_markup": vip_markup, "parse_mode": "Markdown"}
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json=payload)
            except Exception:
                pass

    except Exception as e:
        print(f"❌ Storage Upload error: {e}")

# =========================================================
# START & COMMAND HANDLERS
# =========================================================
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    text = message.text
    param = text.split()[1] if len(text.split()) > 1 else ""
    user_id = message.from_user.id

    # 1. VIP DIRECT FILE HANDLER (ONLY VIA VIP CHANNEL) -> 6-HOUR TIMER
    if param.startswith("vipfile_"):
        msg_id = int(param.split("_")[1])
        await message.reply_text("👑 **VIP Direct File:** මෙන්න ඔබගේ චිත්‍රපටය:")
        await send_file_with_auto_delete(chat_id=user_id, message_id=msg_id, is_vip=True)
        return

    # 2. DUAL FSUB MEMBERSHIP VERIFICATION
    if not await check_user_access(client, user_id):
        markup = await get_dual_fsub_buttons(client, param)
        await message.reply_text("🔒 **ප්‍රවේශය සත්‍යාපනය කර නොමැත!**\n\nචිත්‍රපට ලබා ගැනීමට ප්‍රථමයෙන් අපගේ Channels වලට Join වන්න.", reply_markup=markup)
        return

    # 3. DIRECT STARS SINGLE PURCHASE INVOICE
    if param.startswith("buy_"):
        msg_id = param.split("_")[1]
        await send_stars_invoice(
            chat_id=user_id,
            title="Direct Movie File",
            description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
            payload=f"single_{msg_id}",
            stars=SINGLE_STAR_PRICE
        )
        return

    # 4. VIP UPGRADE SCREEN
    if param == "vip":
        await message.reply_text("👑 **Cinex LK VIP Pass (Monthly)**", reply_markup=get_vip_selection_markup())
        return

    # 5. TOKEN 1 VERIFIED -> SHOW STEP 2
    if param.startswith("tok1_"):
        if param not in verified_tokens:
            await message.reply_text("⚠️ **සත්‍යාපනය අසාර්ථකයි!** කරුණාකර Pop-up Allow කර තත්පර 8ක් සම්පූර්ණ වන තෙක් රැඳී සිටින්න.")
            return

        parts = param.split("_")
        msg_id = parts[2]
        verified_tokens.remove(param)

        step2_url = f"{BASE_URL}/gate/step2/{user_id}/{msg_id}" if BASE_URL else MONETAG_STREAM_LINK
        step2_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Open Sponsor Link 2 (Final Step)", url=step2_url)]
        ])
        await message.reply_text(
            "🎉 **Step 1 සාර්ථකයි!**\n\n"
            "චිත්‍රපටය ලබාගැනීමට අවසන් පියවර ලෙස පහත **'Open Sponsor Link 2'** ඔබා තත්පර 8 සම්පූර්ණ කරන්න.",
            reply_markup=step2_markup
        )
        return

    # 6. TOKEN 2 VERIFIED -> AUTO SEND MOVIE
    if param.startswith("tok2_"):
        if param not in verified_tokens:
            await message.reply_text("⚠️ **සත්‍යාපනය අසාර්ථකයි!** කරුණාකර Pop-up Allow කර තත්පර 8ක් සම්පූර්ණ වන තෙක් රැඳී සිටින්න.")
            return

        parts = param.split("_")
        msg_id = int(parts[2])
        verified_tokens.remove(param)

        await message.reply_text("🎉 **පියවර 2ම සාර්ථකව අවසන් විය! මෙන්න ඔබගේ චිත්‍රපටය:**")
        await send_file_with_auto_delete(chat_id=user_id, message_id=msg_id, is_vip=False)
        return

    # 7. MAIN CHANNEL FREE DOWNLOAD INITIATOR (STEP 1)
    if param.startswith("adstep1_") or param.startswith("adget_") or param.startswith("get_"):
        msg_id = int(param.split("_")[1])

        step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else ADSTERRA_DIRECT_LINK
        step1_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Open Sponsor Link 1 (Step 1)", url=step1_url)]
        ])
        await message.reply_text(
            "🎬 **Download Verification (Step 1 of 2):**\n\n"
            "නොමිලේ චිත්‍රපටය ලබාගැනීමට පහත **'Open Sponsor Link 1'** ඔබන්න.\n\n"
            "*(කරුණාකර Browser එකේ Pop-ups Allow කර තබා ගන්න)*",
            reply_markup=step1_markup
        )
        return

    await message.reply_text(
        "👋 **සාදරයෙන් පිළිගන්නවා Cinex LK වෙත!**\n\n"
        "🔍 **චිත්‍රපට සෙවීමට:** Movie එකේ නම type කර එවන්න.\n"
        "📚 **චිත්‍රපට නාමාවලිය:** `/movielist`\n"
        "🔥 **Trending:** `/trending`\n"
        "📥 **Request Movie:** `/request <Name>`\n"
        "👑 **VIP:** `/start vip`"
    )

@app.on_callback_query(filters.regex(r"^verify_"))
async def callback_verify_handler(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    param = callback.data.replace("verify_", "")
    if param == "root":
        param = ""

    if await check_user_access(client, user_id):
        await callback.answer("🎉 ප්‍රවේශය සත්‍යාපනය විය!", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass

        if param.startswith("vipfile_"):
            msg_id = int(param.split("_")[1])
            await client.send_message(chat_id=user_id, text="👑 **VIP Direct File:**")
            await send_file_with_auto_delete(chat_id=user_id, message_id=msg_id, is_vip=True)
        elif param.startswith("adstep1_") or param.startswith("adget_") or param.startswith("get_"):
            msg_id = int(param.split("_")[1])
            step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else ADSTERRA_DIRECT_LINK
            step1_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Open Sponsor Link 1 (Step 1)", url=step1_url)]
            ])
            await client.send_message(
                chat_id=user_id,
                text="🎬 **Download Verification (Step 1 of 2):**\n\nනොමිලේ චිත්‍රපටය ලබාගැනීමට පහත **'Open Sponsor Link 1'** ඔබන්න.",
                reply_markup=step1_markup
            )
        elif param == "vip":
            await client.send_message(chat_id=user_id, text="👑 **Cinex LK VIP Pass**", reply_markup=get_vip_selection_markup())
        else:
            await client.send_message(chat_id=user_id, text="👋 ඔබට අවශ්‍ය Movie එකේ නම type කර Search කරන්න.")
    else:
        await callback.answer("❌ කරුණාකර Channels 2ටම Join වී නැවත Verify ඔබන්න.", show_alert=True)

# =========================================================
# SEARCH HANDLER (STRICT ADS ENFORCED)
# =========================================================
@app.on_message(filters.text & filters.incoming & filters.private & ~filters.command(["start", "help", "addvip", "request", "trending", "movielist", "movies"]))
async def handle_search(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට සෙවීමට පෙර Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    query = message.text.strip()
    regex = {"file_name": {"$regex": re.escape(query), "$options": "i"}}
    cursor = files_col.find(regex).limit(3)
    raw_results = await cursor.to_list(length=3)

    if not raw_results:
        await message.reply_text("❌ චිත්‍රපටය හමු නොවීය. නම නිවැරදිව type කරන්න හෝ `/request <Name>` හරහා ඉල්ලන්න.")
        return

    for file in raw_results:
        size_mb = round(file["file_size"] / (1024 * 1024), 2)
        msg_id = file["message_id"]

        caption = f"🎬 **{file['file_name']}**\n📦 **Size:** `{size_mb} MB`\n\n👇 **ලබාගැනීමට තෝරන්න:**"
        buttons = [
            [InlineKeyboardButton("📥 Download Movie (Free Ads)", callback_data=f"search_ad_{msg_id}")],
            [
                InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️ / Rs. 20)", callback_data=f"buy_single_{msg_id}"),
                InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", callback_data="buy_vip_pass")
            ]
        ]
        await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^search_ad_"))
async def callback_search_ad(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    msg_id = int(callback.data.split("_")[2])

    await callback.answer()
    step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else ADSTERRA_DIRECT_LINK
    step1_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 Open Sponsor Link 1 (Step 1)", url=step1_url)]
    ])
    await client.send_message(
        chat_id=user_id,
        text="🎬 **Download Verification (Step 1 of 2):**\n\nනොමිලේ චිත්‍රපටය ලබාගැනීමට පහත **'Open Sponsor Link 1'** ඔබන්න.",
        reply_markup=step1_markup
    )

# =========================================================
# VIP MANAGEMENT & STARS PAYMENT HANDLER
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
        "• කිසිදු Ad එකක් නැත (100% No Ads Direct Files)\n"
        "• VIP Channel එකට දින 30ක අඛණ්ඩ ප්‍රවේශය\n"
        "• පැය 6ක Auto-Delete කාලයක් හිමිවීම\n\n"
        "👇 **ඔබ ගෙවීම් කිරීමට බලාපොරොත්තු වන ක්‍රමය තෝරන්න:**"
    )
    await callback.message.reply_text(text, reply_markup=get_vip_selection_markup())

@app.on_callback_query(filters.regex(r"^pay_vip_stars$"))
async def pay_vip_stars_handler(client: Client, callback: CallbackQuery):
    await callback.answer("⭐ Preparing Stars Invoice...")
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="VIP Pass (30 Days)",
        description="Cinex LK VIP Channel ප්‍රවේශය (No Ads + Direct Files)",
        payload="vip_sub",
        stars=VIP_STAR_PRICE
    )

@app.on_callback_query(filters.regex(r"^buy_single_"))
async def pay_single(client: Client, callback: CallbackQuery):
    msg_id = callback.data.split("_")[2]
    await callback.answer("⭐ Preparing Stars Invoice...")
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="Direct Movie File",
        description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
        payload=f"single_{msg_id}",
        stars=SINGLE_STAR_PRICE
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
            f"💰 **මුදල:** `Rs. {VIP_LKR_PRICE}`\n\n"
            f"📌 *User slip එක එවූ පසු VIP දීමට:*\n`/addvip {user_id}`"
        )
        try:
            await client.send_message(chat_id=ADMIN_USER_ID, text=admin_alert)
        except Exception:
            pass

    admin_link = f"https://t.me/{ADMIN_USERNAME}" if ADMIN_USERNAME else None
    text = (
        "🇱🇰 **බැංකු තැන්පතු මඟින් VIP ලබාගැනීම:**\n\n"
        f"💰 **ගෙවිය යුතු මුදල:** `Rs. {VIP_LKR_PRICE}`\n\n"
        f"{BANK_DETAILS}\n\n"
        f"⚠️ **අනිවාර්යයි (Very Important):**\n"
        f"මුදල් තැන්පත් කරන විට Reference/Remarks සඳහා පහත ඔබගේ Unique Code එක ඇතුළත් කරන්න:\n"
        f"🔑 **ඔබගේ Reference Code එක:** `{ref_code}`\n\n"
        f"📸 මුදල් ගෙවූ පසු Payment Slip හෝ Screenshot එක ඔබගේ User ID (`{user_id}`) සමඟ Admin වෙත එවන්න."
    )
    buttons = [[InlineKeyboardButton("📩 Send Slip to Admin", url=admin_link)]] if admin_link else []
    await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

@app.on_message(filters.command("addvip") & filters.private)
async def admin_add_vip_handler(client: Client, message: Message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ **භාවිතය:** `/addvip <USER_ID>`")
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
        invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
        await client.send_message(
            chat_id=target_user_id,
            text=f"🎉 **ඔබගේ VIP සාමාජිකත්වය සක්‍රිය විය!**\n\n🔗 VIP Channel Link:\n{invite.invite_link}"
        )
        await message.reply_text(f"✅ User `{target_user_id}` VIP ලෙස සක්‍රිය කරන ලදී.")
    except Exception as e:
        await message.reply_text(f"⚠️ Invite Error: {e}")

# =========================================================
# PAYMENT PRE-CHECKOUT & SUCCESS
# =========================================================
@app.on_raw_update()
async def raw_update_handler(client: Client, update, users, chats):
    if update.__class__.__name__ == "UpdateBotPrecheckoutQuery":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"pre_checkout_query_id": str(update.query_id), "ok": True})

payment_filter = filters.create(lambda _, __, m: bool(getattr(m, "successful_payment", None)))

@app.on_message(payment_filter)
async def payment_success(client: Client, message: Message):
    payload = message.successful_payment.invoice_payload

    if payload.startswith("single_"):
        msg_id = int(payload.split("_")[1])
        await message.reply_text("🎉 **ගෙවීම සාර්ථකයි!** මෙන්න Movie එක:")
        await send_file_with_auto_delete(chat_id=message.chat.id, message_id=msg_id, is_vip=True)

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
            await message.reply_text(f"🎉 **VIP සාමාජිකත්වය සක්‍රිය විය!**\n\n🔗 VIP Channel Link:\n{invite.invite_link}")
        except Exception:
            pass

# =========================================================
# MOVIE LIST, REQUEST & TRENDING
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

    text = f"📚 **Cinex LK Movies Library** (පිටුව: `{page}/{total_pages}`)\n\n"
    buttons = []
    for idx, f in enumerate(movies, start=skip + 1):
        name = f.get("file_name", "Unknown")
        msg_id = f.get("message_id")
        text += f"`{idx}.` 🎬 **{name}**\n"
        buttons.append([InlineKeyboardButton(f"📥 {name[:30]}", url=f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"mlist_{page - 1}"))
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

    text = "🔥 **Cinex LK Trending Movies:**\n\n"
    buttons = []
    for idx, f in enumerate(top_movies, 1):
        name = f.get("file_name", "Movie")
        msg_id = f.get("message_id")
        text += f"{idx}. 🎬 **{name}**\n"
        buttons.append([InlineKeyboardButton(f"📥 {name[:28]}", url=f"https://t.me/{BOT_USERNAME}?start=adstep1_{msg_id}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("request") & filters.private)
async def handle_movie_request(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට ඉල්ලීම් කිරීමට පෙර Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("📝 **භාවිතය:** `/request <Movie Name>`")
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
    await message.reply_text(f"✅ **ඔබගේ චිත්‍රපට ඉල්ලීම සටහන් විය!**\n🎬 `{movie_name}`")

# =========================================================
# SERVER RUNNER
# =========================================================
async def main():
    await app.start()
    me = await app.get_me()
    print(f"🤖 Bot Started Successfully as @{me.username}")
    await restore_storage_peer()

    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Hardened Ad Gate Live on port {PORT}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
