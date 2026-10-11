import os
import re
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# --- Configurations ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
STORAGE_CHANNEL = int(os.environ.get("STORAGE_CHANNEL", "0"))
VIP_CHANNEL = int(os.environ.get("VIP_CHANNEL", "0"))

BASE_URL = os.environ.get("BASE_URL", "")
MONETAG_STREAM_LINK = os.environ.get("MONETAG_STREAM_LINK", "")
ADSTERRA_DIRECT_LINK = os.environ.get("ADSTERRA_DIRECT_LINK", "")
PORT = int(os.environ.get("PORT", "8080"))

app = Client("all_in_one_movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URI)
files_col = db_client["MovieDB"]["files"]

# Telegram Bot API Helper for Stars Invoices
async def send_stars_invoice(chat_id: int, title: str, description: str, payload: str, stars: int):
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

# =========================================================
# 1. STREAMING SERVER + MONETAG 4-MILESTONE ADS
# =========================================================
routes = web.RouteTableDef()

PLAYER_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Stream Player</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ margin:0; background:#080b11; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; }}
        video {{ width:95%; max-width:880px; border-radius:12px; box-shadow:0 8px 30px rgba(0,0,0,0.8); }}
    </style>
</head>
<body>
    <video id="moviePlayer" controls autoplay playsinline>
        <source src="/stream/{{msg_id}}" type="video/mp4">
        Browser does not support video playback.
    </video>

    <script>
        const AD_URL = "{MONETAG_STREAM_LINK}";
        const video = document.getElementById('moviePlayer');

        let adTriggers = {{
            start: false,
            p25: false,
            p50: false,
            p75: false
        }};

        function triggerAd() {{
            window.open(AD_URL, '_blank');
        }}

        document.addEventListener('click', function() {{
            if (!adTriggers.start) {{
                adTriggers.start = true;
                triggerAd();
            }}
        }}, {{ once: true }});

        video.addEventListener('timeupdate', function() {{
            if (!video.duration) return;
            const percent = (video.currentTime / video.duration) * 100;

            if (percent >= 25 && !adTriggers.p25) {{
                adTriggers.p25 = true;
                triggerAd();
            }}
            if (percent >= 50 && !adTriggers.p50) {{
                adTriggers.p50 = true;
                triggerAd();
            }}
            if (percent >= 75 && !adTriggers.p75) {{
                adTriggers.p75 = true;
                triggerAd();
            }}
        }});
    </script>
</body>
</html>
"""

@routes.get("/watch/{msg_id}")
async def watch_page(request):
    msg_id = request.match_info['msg_id']
    return web.Response(text=PLAYER_HTML.format(msg_id=msg_id), content_type='text/html')

@routes.get("/stream/{msg_id}")
async def stream_media(request):
    msg_id = int(request.match_info['msg_id'])
    msg = await app.get_messages(STORAGE_CHANNEL, msg_id)
    media = msg.document or msg.video
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': media.mime_type or 'video/mp4',
            'Content-Length': str(media.file_size),
            'Accept-Ranges': 'bytes'
        }
    )
    await response.prepare(request)
    async for chunk in app.stream_media(msg, limit=0):
        await response.write(chunk)
    return response

# =========================================================
# 2. BOT LOGIC, AUTO-INDEX & SEARCH
# =========================================================

@app.on_message(filters.chat(STORAGE_CHANNEL) & (filters.document | filters.video))
async def auto_index(client: Client, message: Message):
    media = message.document or message.video
    await files_col.update_one(
        {"file_id": media.file_id},
        {"$set": {
            "file_name": media.file_name or "Unknown Movie",
            "file_size": media.file_size,
            "message_id": message.id
        }},
        upsert=True
    )

@app.on_message(filters.text & filters.incoming & ~filters.command(["start", "help"]))
async def handle_search(client: Client, message: Message):
    query = message.text.strip()
    regex = {"file_name": {"$regex": re.escape(query), "$options": "i"}}
    results = await files_col.find(regex).limit(5).to_list(length=5)

    if not results:
        await message.reply_text("❌ Movie එක හමු නොවීය. නම නිවැරදිව type කරන්න.")
        return

    for file in results:
        size_mb = round(file["file_size"] / (1024 * 1024), 2)
        msg_id = file["message_id"]
        watch_url = f"{BASE_URL}/watch/{msg_id}"

        caption = (
            f"🎬 **{file['file_name']}**\n"
            f"📦 **Size:** `{size_mb} MB`\n\n"
            f"👇 **නැරඹීමට හෝ බාගත කිරීමට තෝරන්න:**"
        )

        buttons = [
            [InlineKeyboardButton("🌐 Watch Online (Fast Player)", url=watch_url)],
            [
                InlineKeyboardButton("📥 Download (Adsterra Mirror)", url=ADSTERRA_DIRECT_LINK),
                InlineKeyboardButton("⚡ Get TG File", callback_data=f"getfile_{msg_id}")
            ],
            [InlineKeyboardButton("⚡ Instant (5 ⭐️ / Rs. 20)", callback_data=f"buy_single_{msg_id}")],
            [InlineKeyboardButton("👑 Buy VIP Pass (No Ads Ever)", callback_data="buy_vip_pass")]
        ]
        await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^getfile_"))
async def send_free_file(client: Client, callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[1])
    await callback.answer()
    await client.copy_message(
        chat_id=callback.from_user.id,
        from_chat_id=STORAGE_CHANNEL,
        message_id=msg_id
    )

# =========================================================
# 3. TELEGRAM STARS PAYMENTS
# =========================================================

@app.on_callback_query(filters.regex(r"^buy_single_"))
async def pay_single(client: Client, callback: CallbackQuery):
    msg_id = callback.data.split("_")[1]
    await callback.answer()
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="Direct Movie File",
        description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
        payload=f"single_{msg_id}",
        stars=5
    )

@app.on_callback_query(filters.regex(r"^buy_vip_pass$"))
async def pay_vip(client: Client, callback: CallbackQuery):
    await callback.answer()
    await send_stars_invoice(
        chat_id=callback.from_user.id,
        title="VIP Membership (30 Days)",
        description="සියලුම Movies & Series දැන්වීම් නැතිව direct ලබාගන්න.",
        payload="vip_sub",
        stars=150
    )

@app.on_raw_update()
async def raw_update_handler(client: Client, update, users, chats):
    # Auto-answer pre-checkout query via HTTP API
    if update.__class__.__name__ == "UpdateBotPrecheckoutQuery":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"pre_checkout_query_id": str(update.query_id), "ok": True})

@app.on_message(filters.successful_payment)
async def payment_success(client: Client, message: Message):
    payload = message.successful_payment.invoice_payload

    if payload.startswith("single_"):
        msg_id = int(payload.split("_")[1])
        await message.reply_text("🎉 **ගෙවීම සාර්ථකයි!** මෙන්න Movie එක:")
        await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)

    elif payload == "vip_sub":
        invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
        await message.reply_text(f"👑 **VIP Access සක්‍රිය විය!**\n\nVIP Channel Link:\n{invite.invite_link}")

# =========================================================
# 4. SERVER STARTUP
# =========================================================
async def start_services():
    await app.start()
    web_app = web.Application()
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

if __name__ == "__main__":
    app.run(start_services())
