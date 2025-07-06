import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load env vars
load_dotenv()
BOT_TOKEN    = os.getenv('BOT_TOKEN')
API_BASE_URL = os.getenv('API_BASE_URL')  # e.g. https://hiapitest.onrender.com/api/v1

if not BOT_TOKEN or not API_BASE_URL:
    print("Error: BOT_TOKEN and API_BASE_URL must be set in .env")
    exit(1)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === /search handler (unchanged) ===
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        return await update.message.reply_text('Usage: /search <anime name>')

    query = ' '.join(context.args)
    # note: this API expects `keyword`
    resp = requests.get(f"{API_BASE_URL}/search", params={'keyword': query})
    raw = {}
    try:
        raw = resp.json()
    except ValueError:
        pass

    if resp.status_code != 200 or not raw.get('success', False):
        logger.error("Search failed (%s): %s", resp.status_code, raw)
        return await update.message.reply_text(f'No results for "{query}".')

    results = raw.get('data', {}).get('response', [])
    if not isinstance(results, list) or not results:
        return await update.message.reply_text(f'No results for "{query}".')

    top5 = results[:5]
    lines = [
        f"{i+1}. {item.get('title','–')} (slug: {item.get('id','–')})"
        for i, item in enumerate(top5)
    ]
    await update.message.reply_text(
        f"Top results for '{query}':\n\n" + "\n".join(lines)
    )

# === /get handler (with slug‐cleaning) ===
async def get_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        return await update.message.reply_text(
            'Usage: /get <animeSlug> <episodeNumber>'
        )

    # Strip off any query‐string from the slug
    raw_slug = context.args[0]
    anime_slug = raw_slug.split('?', 1)[0]
    try:
        ep_num = int(context.args[1])
    except ValueError:
        return await update.message.reply_text('Episode number must be an integer.')

    try:
        # 1) Fetch episodes list
        eps_res = requests.get(f"{API_BASE_URL}/episodes/{anime_slug}")
        eps_res.raise_for_status()
        episodes = eps_res.json()

        # Find the matching episode object
        ep_item = next(
            (e for e in episodes if f"Episode {ep_num}" in e.get('title', "")),
            None
        )
        if not ep_item:
            return await update.message.reply_text(
                f'Episode {ep_num} not found for "{anime_slug}".'
            )

        # 2) Fetch available servers
        srv_res = requests.get(
            f"{API_BASE_URL}/servers",
            params={'id': ep_item['id']}
        )
        srv_res.raise_for_status()
        hd2 = next(
            (s for s in srv_res.json().get('sub', []) if s.get('name') == 'HD-2'),
            None
        )
        if not hd2:
            return await update.message.reply_text(
                'HD-2 server not available for this episode.'
            )

        # 3) Fetch stream link + subtitles
        str_res = requests.get(
            f"{API_BASE_URL}/stream",
            params={
                'id': ep_item['id'],
                'server': hd2['name'],
                'type': 'sub'
            }
        )
        str_res.raise_for_status()
        data = str_res.json()

        # Send download link
        await update.message.reply_text(
            f"📥 *Download Link*:\n{data['streamingLink']}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Send any English subtitles
        subs = data.get('subtitles', [])
        if subs:
            for sub in subs:
                await update.message.reply_text(
                    f"💬 *Subtitle ({sub['lang']})*:\n{sub['src']}",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await update.message.reply_text('No English subtitles found.')

    except Exception as e:
        logger.error("Get error: %s", e)
        await update.message.reply_text(
            'An error occurred while fetching the episode. Please try again later.'
        )

# === Main ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('search', search))
    app.add_handler(CommandHandler('get', get_episode))
    logger.info('Bot is starting...')
    app.run_polling()
