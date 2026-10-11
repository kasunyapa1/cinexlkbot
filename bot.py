import os
import re
import io
import asyncio
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

# =========================================================
# CONFIGURATIONS
# =========================================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
STORAGE_CHANNEL = int(os.environ.get("STORAGE_CHANNEL", "0"))
VIP_CHANNEL = int(os.environ.get("VIP_CHANNEL", "0"))
MAIN_CHANNEL = int(os.environ.get("MAIN_CHANNEL", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").replace("@", "")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "").strip()

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

payment_filter = filters.create(lambda _, __, m: bool(getattr(m, "successful_payment", None)))

# =========================================================
# HELPER FUNCTIONS (IMDb / OMDb)
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

async def fetch_imdb_data(filename: str):
    if not OMDB_API_KEY:
        print("⚠️ OMDB_API_KEY is not configured in Environment Variables.")
        return None

    title, year = parse_movie_query(filename)
    if year:
        url = f"https://www.omdbapi.com/?t={title}&y={year}&apikey={OMDB_API_KEY}"
    else:
        url = f"https://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("Response") == "True":
                    return data
                
                fallback_url = f"https://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
                async with session.get(fallback_url) as fb_resp:
                    fb_data = await fb_resp.json()
                    if fb_data.get("Response") == "True":
                        return fb_data
                    print(f"⚠️ OMDb API error for '{title}': {fb_data.get('Error')}")
    except Exception as e:
        print(f"⚠️ OMDb Request Exception: {e}")
    return None

# =========================================================
# 1. STREAMING SERVER + MONETAG ADS
# =========================================================
routes = web.RouteTableDef()

PLAYER_HTML = """
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
        <source src="/stream/{msg_id}" type="video/mp4">
        Browser does not support video playback.
    </video>

    <script>
        const AD_URL = "{ad_url}";
        const video = document.getElementById('moviePlayer');

        let adTriggers = {{ start: false, p25: false, p50: false, p75: false }};

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
            if (percent >= 25 && !adTriggers.p25) {{ adTriggers.p25 = true; triggerAd(); }}
            if (percent >= 50 && !adTriggers.p50) {{ adTriggers.p50 = true; triggerAd(); }}
            if (percent >= 75 && !adTriggers.p75) {{ adTriggers.p75 = true; triggerAd(); }}
        }});
    </script>
</body>
</html>
"""

@routes.get("/watch/{msg_id}")
async def watch_page(request):
    msg_id = request.match_info['msg_id']
    html_content = PLAYER_HTML.format(msg_id=msg_id, ad_url=MONETAG_STREAM_LINK)
    return web.Response(text=html_content, content_type='text/html')

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
# 2. AUTO-INDEX & AUTO-POST (STORAGE -> CHANNELS)
# =========================================================

@app.on_message(filters.chat(STORAGE_CHANNEL) & (filters.document | filters.video))
async def handle_storage_upload(client: Client, message: Message):
    media = message.document or message.video
    if not media:
        return

    file_name = media.file_name or "Unknown Movie"
    size_mb = round(media.file_size / (1024 * 1024), 2)
    msg_id = message.id

    print(f"\n📥 [Storage Channel] New File: {file_name} (Msg ID: {msg_id})")

    # 1. MongoDB එකට Save කිරීම
    try:
        await files_col.update_one(
            {"file_name": file_name},
            {"$set": {
                "file_name": file_name,
                "file_size": media.file_size,
                "message_id": msg_id
            }},
            upsert=True
        )
        print(f"✅ DB Updated for: {file_name}")
    except Exception as db_err:
        print(f"❌ DB Error: {db_err}")

    # 2. OMDb / IMDb විස්තර ලබාගැනීම
    imdb = await fetch_imdb_data(file_name)

    watch_url = f"{BASE_URL}/watch/{msg_id}"
    buy_stars_url = f"https://t.me/{BOT_USERNAME}?start=buy_{msg_id}"
    vip_url = f"https://t.me/{BOT_USERNAME}?start=vip"

    buttons = [
        [InlineKeyboardButton("🌐 Watch Online", url=watch_url)],
        [
            InlineKeyboardButton("📥 Fast Download", url=ADSTERRA_DIRECT_LINK),
            InlineKeyboardButton("⚡ Direct File (5 ⭐️)", url=buy_stars_url)
        ],
        [InlineKeyboardButton("👑 Buy VIP Pass (No Ads)", url=vip_url)]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    poster_bytes = None
    if imdb and imdb.get("Response") == "True":
        title = f"{imdb.get('Title')} ({imdb.get('Year')})"
        rating = imdb.get('imdbRating', 'N/A')
        genre = imdb.get('Genre', 'N/A')
        plot = imdb.get('Plot', 'No description available.')
        raw_poster = imdb.get("Poster")

        caption = (
            f"🎬 **{title}**\n\n"
            f"⭐ **IMDb Rating:** `{rating}/10`\n"
            f"🎭 **Genre:** `{genre}`\n"
            f"📦 **Size:** `{size_mb} MB`\n\n"
            f"📖 **Story:** {plot[:250]}...\n\n"
            f"👇 **නැරඹීමට හෝ බාගත කිරීමට පහත Buttons භාවිතා කරන්න:**"
        )

        if raw_poster and raw_poster != "N/A":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(raw_poster) as img_resp:
                        if img_resp.status == 200:
                            poster_bytes = await img_resp.read()
                            print("🖼️ Poster successfully downloaded from IMDb.")
            except Exception as dl_err:
                print(f"⚠️ Poster download error: {dl_err}")
    else:
        caption = (
            f"🎬 **{file_name}**\n\n"
            f"📦 **Size:** `{size_mb} MB`\n\n"
            f"👇 **නැරඹීමට හෝ බාගත කිරීමට පහත Buttons භාවිතා කරන්න:**"
        )

    # Post කළ යුතු Channels
    target_channels = [ch for ch in [MAIN_CHANNEL, VIP_CHANNEL] if ch]

    for ch_id in target_channels:
        posted = False
        if poster_bytes:
            try:
                photo_file = io.BytesIO(poster_bytes)
                photo_file.name = "poster.jpg"
                await client.send_photo(
                    chat_id=int(ch_id),
                    photo=photo_file,
                    caption=caption,
                    reply_markup=reply_markup
                )
                print(f"🚀 Photo Post successfully published to: {ch_id}")
                posted = True
            except Exception as p_err:
                print(f"⚠️ Photo Post failed for {ch_id}: {p_err}. Trying text fallback...")

        if not posted:
            try:
                await client.send_message(
                    chat_id=int(ch_id),
                    text=caption,
                    reply_markup=reply_markup
                )
                print(f"🚀 Text Post successfully published to: {ch_id}")
            except Exception as t_err:
                print(f"❌ Text post also failed for {ch_id}: {t_err}")

# =========================================================
# 3. BOT SEARCH (NO DUPLICATES)
# =========================================================

@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    text = message.text
    if len(text.split()) > 1:
        param = text.split()[1]
        if param.startswith("buy_"):
            msg_id = param.split("_")[1]
            await send_stars_invoice(
                chat_id=message.chat.id,
                title="Direct Movie File",
                description="දැන්වීම් නොමැතිව direct movie file එක ලබාගැනීමට.",
                payload=f"single_{msg_id}",
                stars=5
            )
            return
        elif param == "vip":
            await send_stars_invoice(
                chat_id=message.chat.id,
                title="VIP Membership (30 Days)",
                description="සියලුම Movies & Series දැන්වීම් නැතිව direct ලබාගන්න.",
                payload="vip_sub",
                stars=150
            )
            return

    await message.reply_text("👋 **සාදරයෙන් පිළිගන්නවා!**\nඔබට අවශ්‍ය Movie එකේ නම type කර search කරන්න.")

@app.on_message(filters.text & filters.incoming & filters.private & ~filters.command(["start", "help"]))
async def handle_search(client: Client, message: Message):
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

        caption = (
            f"🎬 **{file['file_name']}**\n"
            f"📦 **Size:** `{size_mb} MB`\n\n"
            f"👇 **නැරඹීමට හෝ බාගත කිරීමට තෝරන්න:**"
        )

        buttons = [
            [InlineKeyboardButton("🌐 Watch Online (Fast Player)", url=watch_url)],
            [
                InlineKeyboardButton("📥 Download (Adsterra)", url=ADSTERRA_DIRECT_LINK),
                InlineKeyboardButton("⚡ Get TG File", callback_data=f"getfile_{msg_id}")
            ],
            [InlineKeyboardButton("⚡ Instant (5 ⭐️ / Rs. 20)", callback_data=f"buy_single_{msg_id}")],
            [InlineKeyboardButton("👑 Buy VIP Pass (No Ads)", callback_data="buy_vip_pass")]
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
# 4. TELEGRAM STARS PAYMENTS
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
        await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id)

    elif payload == "vip_sub":
        invite = await client.create_chat_invite_link(chat_id=VIP_CHANNEL, member_limit=1)
        await message.reply_text(f"👑 **VIP Access සක්‍රිය විය!**\n\nVIP Channel Link:\n{invite.invite_link}")

# =========================================================
# 5. SERVER STARTUP & KEEP-ALIVE
# =========================================================
async def main():
    await app.start()
    me = await app.get_me()
    print(f"🤖 Bot Started Successfully as @{me.username}")

    for name, ch_id in [("Storage", STORAGE_CHANNEL), ("Main", MAIN_CHANNEL), ("VIP", VIP_CHANNEL)]:
        if ch_id:
            try:
                chat = await app.get_chat(ch_id)
                print(f"✅ Verified Access to {name} Channel: {chat.title} ({ch_id})")
            except Exception as e:
                print(f"❌ Cannot access {name} Channel ({ch_id}): {e}")

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
