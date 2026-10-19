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
from pyrogram.raw.functions.channels import GetMessages
from pyrogram.raw.types import InputMessageID
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

PRIMARY_AD_LINK = os.environ.get("MONETAG_STREAM_LINK", os.environ.get("ADSTERRA_DIRECT_LINK", "https://google.com")).strip()

PORT = int(os.environ.get("PORT", "8080"))

FREE_USER_DELETE_DURATION = int(os.environ.get("FREE_USER_DELETE_DURATION", "3600"))
VIP_USER_DELETE_DURATION = int(os.environ.get("VIP_USER_DELETE_DURATION", "21600"))

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

awaiting_request = set()

# =========================================================
# WEB SERVER & SAME-PAGE AD GATE
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
    return web.Response(text="Cinex LK Engine Online", status=200)

@routes.get("/gate/step1/{user_id}/{msg_id}")
async def gate_step1(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok1_{user_id}_{msg_id}"
    html = SAME_PAGE_GATE_HTML.format(
        step="1",
        ad_url=PRIMARY_AD_LINK,
        bot_username=BOT_USERNAME,
        token=token
    )
    return web.Response(text=html, content_type='text/html')

@routes.get("/gate/step2/{user_id}/{msg_id}")
async def gate_step2(request):
    user_id = request.match_info['user_id']
    msg_id = request.match_info['msg_id']
    token = f"tok2_{user_id}_{msg_id}"
    html = SAME_PAGE_GATE_HTML.format(
        step="2",
        ad_url=PRIMARY_AD_LINK,
        bot_username=BOT_USERNAME,
        token=token
    )
    return web.Response(text=html, content_type='text/html')

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
# FILE SENDER WITH DYNAMIC TIMER & DOWNLOAD TRACKING
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

    try:
        await files_col.update_one({"message_id": int(message_id)}, {"$inc": {"download_count": 1}})
    except Exception:
        pass

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
                    else:
                        await files_col.delete_one({"message_id": int(message_id)})
                        await app.send_message(chat_id=chat_id, text="❌ **මෙම චිත්‍රපටය Storage එකෙන් ඉවත් කර ඇත.**")
                        return False
        except Exception:
            pass

    if sent_msg:
        warn_msg = await app.send_message(chat_id=chat_id, text=warn_text)
        asyncio.create_task(auto_delete_file_task(chat_id, [sent_msg.id, warn_msg.id], delay, delete_notification))
        return True
    else:
        await files_col.delete_one({"message_id": int(message_id)})
        await app.send_message(chat_id=chat_id, text="❌ **මෙම චිත්‍රපටය Storage එකෙන් ඉවත් කර ඇත.**")
        return False

# =========================================================
# VIP CHECK & CHANNEL ACCESS (SAFE VERIFICATION)
# =========================================================
async def is_vip_user(user_id: int) -> bool:
    try:
        doc = await vip_users_col.find_one({"user_id": int(user_id), "expiry_date": {"$gt": datetime.utcnow()}})
        return bool(doc)
    except Exception:
        return False

async def is_member(client: Client, chat_target, user_id: int) -> bool:
    if not chat_target:
        return True
    try:
        member = await client.get_chat_member(chat_target, user_id)
        status = str(member.status).lower()
        return any(s in status for s in ["member", "administrator", "owner", "restricted"])
    except Exception:
        return False

async def check_user_access(client: Client, user_id: int) -> bool:
    try:
        user_record = await bot_users_col.find_one({"user_id": user_id})
        if user_record and user_record.get("fsub_verified"):
            return True

        in_main = await is_member(client, MAIN_CHANNEL, user_id) if MAIN_CHANNEL else True
        in_backup = await is_member(client, BACKUP_CHANNEL, user_id) if BACKUP_CHANNEL else True

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

        # Do not auto-post forward messages or bot's own internal messages
        if message.from_user and message.from_user.is_self:
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
            {"message_id": msg_id},
            {"$set": { "file_name": file_name, "file_size": media.file_size, "message_id": msg_id, "created_at": datetime.utcnow() }, "$setOnInsert": {"download_count": 0}},
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

@app.on_deleted_messages()
async def handle_storage_delete(client: Client, messages: list):
    try:
        msg_ids = [m.id for m in messages if hasattr(m, "id")]
        if msg_ids:
            res = await files_col.delete_many({"message_id": {"$in": msg_ids}})
            if res.deleted_count > 0:
                print(f"🗑️ Storage Synced: Deleted {res.deleted_count} movies from Database.")
    except Exception as e:
        print(f"⚠️ Storage delete sync error: {e}")

# =========================================================
# START COMMAND (RELIABLE PARAMETER ROUTING)
# =========================================================
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ""
    user_id = message.from_user.id

    # 1. VIP DIRECT FILE REQUEST
    if param.startswith("vipfile_"):
        try:
            msg_id = int(param.split("_")[1])
            await message.reply_text("👑 **VIP Direct File:** මෙන්න ඔබගේ චිත්‍රපටය:")
            await send_file_with_auto_delete(chat_id=user_id, message_id=msg_id, is_vip=True)
            return
        except Exception:
            pass

    # 2. TOKEN 1 VERIFIED
    if param.startswith("tok1_"):
        try:
            tok_parts = param.split("_")
            msg_id = tok_parts[2]
            step2_url = f"{BASE_URL}/gate/step2/{user_id}/{msg_id}" if BASE_URL else PRIMARY_AD_LINK
            step2_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Open Sponsor Link 2 (Final Step)", url=step2_url)]
            ])
            await message.reply_text(
                "🎉 **Step 1 සාර්ථකයි!**\n\n"
                "චිත්‍රපටය ලබාගැනීමට අවසන් පියවර ලෙස පහත **'Open Sponsor Link 2'** ඔබා තත්පර 8ක් රැඳී සිටින්න.",
                reply_markup=step2_markup
            )
            return
        except Exception:
            pass

    # 3. TOKEN 2 VERIFIED
    if param.startswith("tok2_"):
        try:
            tok_parts = param.split("_")
            msg_id = int(tok_parts[2])
            await message.reply_text("🎉 **පියවර 2ම සාර්ථකව අවසන් විය! මෙන්න ඔබගේ චිත්‍රපටය:**")
            await send_file_with_auto_delete(chat_id=user_id, message_id=msg_id, is_vip=False)
            return
        except Exception:
            pass

    # 4. STARS SINGLE PURCHASE
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

    # 5. VIP MENU
    if param == "vip":
        await message.reply_text("👑 **Cinex LK VIP Pass (Monthly)**", reply_markup=get_vip_selection_markup())
        return

    # 6. FORCE SUB MEMBERSHIP CHECK
    has_access = await check_user_access(client, user_id)
    if not has_access:
        markup = await get_dual_fsub_buttons(client, param)
        await message.reply_text(
            "🔒 **ප්‍රවේශය සත්‍යාපනය කර නොමැත!**\n\nචිත්‍රපට ලබා ගැනීමට ප්‍රථමයෙන් පහත Channels වලට Join වන්න.",
            reply_markup=markup
        )
        return

    # 7. MAIN CHANNEL FREE DOWNLOAD INITIATOR
    if param.startswith("adstep1_") or param.startswith("adget_") or param.startswith("get_"):
        try:
            msg_id = int(param.split("_")[1])
            step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else PRIMARY_AD_LINK
            step1_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Open Sponsor Link 1 (Step 1)", url=step1_url)]
            ])
            await message.reply_text(
                "🎬 **Download Verification (Step 1 of 2):**\n\n"
                "නොමිලේ චිත්‍රපටය ලබාගැනීමට පහත **'Open Sponsor Link 1'** ඔබා එකම පිටුවේ තත්පර 8ක් රැඳී සිටින්න.",
                reply_markup=step1_markup
            )
            return
        except Exception:
            pass

    # DEFAULT ROOT WELCOME
    await message.reply_text(
        "👋 **සාදරයෙන් පිළිගන්නවා Cinex LK වෙත!**\n\n"
        "🔍 **චිත්‍රපට සෙවීමට:** Movie එකේ නම type කර එවන්න.\n"
        "📚 **චිත්‍රපට නාමාවලිය:** `/movielist`\n"
        "🔥 **Trending චිත්‍රපට:** `/trending`\n"
        "📥 **චිත්‍රපට ඉල්ලීම:** `/request`\n"
        "👑 **VIP සාමාජිකත්වය:** `/start vip`"
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
            step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else PRIMARY_AD_LINK
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
# ZERO-POST SAFE STORAGE EXISTENCE CHECK (MTPROTO RAW RPC)
# =========================================================
async def check_file_exists_in_storage(message_id: int) -> bool:
    try:
        await restore_storage_peer()
        peer = await app.resolve_peer(STORAGE_CHANNEL)
        r = await app.invoke(
            GetMessages(
                channel=peer,
                id=[InputMessageID(id=int(message_id))]
            )
        )
        if hasattr(r, "messages") and len(r.messages) > 0:
            m = r.messages[0]
            # If message is empty/deleted
            if m.__class__.__name__ == "MessageEmpty":
                await files_col.delete_one({"message_id": int(message_id)})
                return False
            # Check if media exists
            if hasattr(m, "media") and m.media:
                return True
        await files_col.delete_one({"message_id": int(message_id)})
        return False
    except Exception as e:
        # If error occurs, fallback to DB without deleting
        return True

# =========================================================
# MOVIE LIST WITH REAL-TIME STORAGE EXISTENCE VERIFICATION
# =========================================================
@app.on_message(filters.command(["movielist", "movies"]) & filters.private)
async def handle_movie_list(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට ලැයිස්තුව බැලීමට අපගේ Channels වලට එක්වන්න:**", reply_markup=markup)
        return
    await send_movie_list_page(message.chat.id, message.from_user.id, page=1)

async def send_movie_list_page(chat_id: int, user_id: int, page: int = 1, edit_message_id: int = None):
    PAGE_SIZE = 10
    skip = (page - 1) * PAGE_SIZE

    cursor = files_col.find({}).sort("_id", -1).skip(skip).limit(PAGE_SIZE * 2)
    raw_movies = await cursor.to_list(length=PAGE_SIZE * 2)

    valid_movies = []
    for f in raw_movies:
        if await check_file_exists_in_storage(f.get("message_id")):
            valid_movies.append(f)
        if len(valid_movies) == PAGE_SIZE:
            break

    total_movies = await files_col.count_documents({})
    total_pages = max(1, (total_movies + PAGE_SIZE - 1) // PAGE_SIZE)

    if not valid_movies:
        text = "📁 **දැනට චිත්‍රපට කිසිවක් එක් කර නොමැත.**"
        if edit_message_id:
            await app.edit_message_text(chat_id=chat_id, message_id=edit_message_id, text=text)
        else:
            await app.send_message(chat_id=chat_id, text=text)
        return

    is_vip = await is_vip_user(user_id)
    badge = "👑 VIP User (Direct Files)" if is_vip else "👤 Free User (With Ads)"

    text = f"📚 **Cinex LK Movies Library**\n"
    text += f"📊 මුළු චිත්‍රපට: `{total_movies}` | පිටුව: `{page}/{total_pages}`\n"
    text += f"🔖 ඔබගේ තත්ත්වය: `{badge}`\n\n"
    text += "👇 **බාගත කිරීමට අවශ්‍ය චිත්‍රපටය තෝරන්න:**\n\n"

    buttons = []
    for idx, f in enumerate(valid_movies, start=skip + 1):
        name = f.get("file_name", "Unknown Movie")
        msg_id = f.get("message_id")
        target_param = f"vipfile_{msg_id}" if is_vip else f"adstep1_{msg_id}"
        btn_url = f"https://t.me/{BOT_USERNAME}?start={target_param}"
        buttons.append([InlineKeyboardButton(f"🎬 {idx}. {name[:30]}", url=btn_url)])

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
    await send_movie_list_page(chat_id=callback.message.chat.id, user_id=callback.from_user.id, page=page, edit_message_id=callback.message.id)

# =========================================================
# TRENDING MOVIES (/trending)
# =========================================================
@app.on_message(filters.command("trending") & filters.private)
async def handle_trending(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **මෙම පහසුකම භාවිතා කිරීමට Channels වලට Join වන්න:**", reply_markup=markup)
        return

    cursor = files_col.find({}).sort("download_count", -1).limit(10)
    top_candidates = await cursor.to_list(length=10)

    top_movies = []
    for f in top_candidates:
        if await check_file_exists_in_storage(f.get("message_id")):
            top_movies.append(f)
        if len(top_movies) == 5:
            break

    if not top_movies:
        await message.reply_text("📊 දැනට Trending දත්ත කිසිවක් හමු නොවීය.")
        return

    is_vip = await is_vip_user(message.from_user.id)
    text = "🔥 **Cinex LK Trending Movies (වැඩිපුරම Download වූ චිත්‍රපට 5):**\n\n"
    buttons = []

    for idx, f in enumerate(top_movies, 1):
        name = f.get("file_name", "Movie")
        msg_id = f.get("message_id")
        dl_count = f.get("download_count", 0)

        text += f"`{idx}.` 🎬 **{name}**\n📥 Downloads: `{dl_count}` වාරයක්\n\n"
        target_param = f"vipfile_{msg_id}" if is_vip else f"adstep1_{msg_id}"
        buttons.append([InlineKeyboardButton(f"📥 Download #{idx} - {name[:24]}", url=f"https://t.me/{BOT_USERNAME}?start={target_param}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# =========================================================
# ADMIN STORAGE SYNC TOOL (/syncmovies) - ZERO CHAT POSTS
# =========================================================
@app.on_message(filters.command("syncmovies") & filters.private)
async def admin_sync_movies(client: Client, message: Message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        return

    status_msg = await message.reply_text("🔄 Storage Channel එක නිහඬව පරීක්ෂා කරමින් පවතී...")
    deleted_count = 0

    cursor = files_col.find({})
    all_movies = await cursor.to_list(length=1000)

    for movie in all_movies:
        msg_id = movie.get("message_id")
        exists = await check_file_exists_in_storage(msg_id)
        if not exists:
            deleted_count += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(f"✅ Sync සාර්ථකයි! Storage එකේ නොමැති පැරණි Movies `{deleted_count}` ක් Database එකෙන් ඉවත් කරන ලදී. (Duplicate posts 0)")

# =========================================================
# MOVIE REQUEST SYSTEM (/request)
# =========================================================
@app.on_message(filters.command("request") & filters.private)
async def handle_movie_request(client: Client, message: Message):
    if not await check_user_access(client, message.from_user.id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට ඉල්ලීම් කිරීමට පෙර Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id

    if len(args) < 2:
        awaiting_request.add(user_id)
        await message.reply_text(
            "📝 **ඔබට අවශ්‍ය චිත්‍රපටයේ නම Type කර මෙහි එවන්න:**\n\n"
            "*(උදාහරණයක් ලෙස: `Avatar 2` හෝ `Spiderman No Way Home`)*"
        )
        return

    movie_name = args[1].strip()
    await save_and_confirm_request(client, message, user_id, movie_name)

async def save_and_confirm_request(client: Client, message: Message, user_id: int, movie_name: str):
    user = message.from_user
    username = f"@{user.username}" if user.username else "No Username"

    await requests_col.insert_one({
        "user_id": user_id,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "username": username,
        "movie_name": movie_name,
        "status": "pending",
        "created_at": datetime.utcnow()
    })

    await message.reply_text(
        f"✅ **ඔබගේ චිත්‍රපට ඉල්ලීම සාර්ථකව සටහන් විය!**\n\n"
        f"🎬 **චිත්‍රපටය:** `{movie_name}`\n\n"
        "අප විසින් මෙම චිත්‍රපටය Upload කළ සැනින් Bot මඟින් ඔබට Notification පණිවිඩයක් එවනු ඇත."
    )

    if ADMIN_USER_ID:
        try:
            await client.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"🔔 **නව Movie Request එකක්!**\n\n🎬 චිත්‍රපටය: `{movie_name}`\n👤 User: {user.first_name} (`{user_id}`)"
            )
        except Exception:
            pass

# =========================================================
# SEARCH HANDLER
# =========================================================
@app.on_message(filters.text & filters.incoming & filters.private & ~filters.command(["start", "help", "addvip", "request", "trending", "movielist", "movies", "syncmovies"]))
async def handle_search_and_request(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in awaiting_request:
        awaiting_request.remove(user_id)
        movie_name = message.text.strip()
        await save_and_confirm_request(client, message, user_id, movie_name)
        return

    if not await check_user_access(client, user_id):
        markup = await get_dual_fsub_buttons(client)
        await message.reply_text("🔒 **චිත්‍රපට සෙවීමට පෙර Channels වලට එක්වන්න:**", reply_markup=markup)
        return

    query = message.text.strip()
    regex = {"file_name": {"$regex": re.escape(query), "$options": "i"}}
    cursor = files_col.find(regex).limit(5)
    candidates = await cursor.to_list(length=5)

    raw_results = []
    for file in candidates:
        if await check_file_exists_in_storage(file.get("message_id")):
            raw_results.append(file)
        if len(raw_results) == 3:
            break

    if not raw_results:
        req_markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Request This Movie", callback_data=f"make_req_{query[:30]}")]])
        await message.reply_text(
            f"❌ **'{query}' චිත්‍රපටය හමු නොවීය.**\n\nනම නිවැරදිව type කරන්න හෝ පහත Button එක ඔබා මෙම චිත්‍රපටය Bot වෙත Request කරන්න.",
            reply_markup=req_markup
        )
        return

    is_vip = await is_vip_user(user_id)

    for file in raw_results:
        size_mb = round(file["file_size"] / (1024 * 1024), 2)
        msg_id = file["message_id"]

        caption = f"🎬 **{file['file_name']}**\n📦 **Size:** `{size_mb} MB`\n\n👇 **ලබාගැනීමට තෝරන්න:**"
        
        if is_vip:
            buttons = [
                [InlineKeyboardButton("⚡ VIP Direct Download", callback_data=f"vip_get_{msg_id}")]
            ]
        else:
            buttons = [
                [InlineKeyboardButton("📥 Download Movie (Free Ads)", callback_data=f"search_ad_{msg_id}")],
                [
                    InlineKeyboardButton(f"⚡ Instant ({SINGLE_STAR_PRICE} ⭐️ / Rs. 20)", callback_data=f"buy_single_{msg_id}"),
                    InlineKeyboardButton("👑 Buy VIP Pass (Monthly)", callback_data="buy_vip_pass")
                ]
            ]
        await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^vip_get_"))
async def callback_vip_direct(client: Client, callback: CallbackQuery):
    await callback.answer()
    msg_id = int(callback.data.split("_")[2])
    await client.send_message(chat_id=callback.from_user.id, text="👑 **VIP Direct File:**")
    await send_file_with_auto_delete(chat_id=callback.from_user.id, message_id=msg_id, is_vip=True)

@app.on_callback_query(filters.regex(r"^make_req_"))
async def callback_make_req(client: Client, callback: CallbackQuery):
    await callback.answer("Request Recorded!")
    movie_name = callback.data.replace("make_req_", "")
    await requests_col.insert_one({
        "user_id": callback.from_user.id,
        "name": callback.from_user.first_name or "",
        "username": f"@{callback.from_user.username}" if callback.from_user.username else "",
        "movie_name": movie_name,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    await callback.message.edit_text(f"✅ **චිත්‍රපට ඉල්ලීම සටහන් විය:** `{movie_name}`")

@app.on_callback_query(filters.regex(r"^search_ad_"))
async def callback_search_ad(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    msg_id = int(callback.data.split("_")[2])

    await callback.answer()
    step1_url = f"{BASE_URL}/gate/step1/{user_id}/{msg_id}" if BASE_URL else PRIMARY_AD_LINK
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
    print(f"🌐 Cinex LK Engine Live on port {PORT}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
