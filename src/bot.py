import os
import logging
import json
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = os.getenv('API_BASE_URL')

if not BOT_TOKEN or not API_BASE_URL:
    print("Error: BOT_TOKEN and API_BASE_URL must be set in .env")
    exit(1)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# /search command
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        return await update.message.reply_text('Usage: /search <anime name>')

    query = ' '.join(context.args)
    try:
        # note the param name change: 'query'
        resp = requests.get(
            f"{API_BASE_URL}/search",
            params={'query': query}
        )
        resp.raise_for_status()
        raw = resp.json()

        # API wraps results in { success, data }
        if not raw.get('success', False):
            return await update.message.reply_text(f'No results for \"{query}\".')

        data_list = raw.get('data', [])
        if not isinstance(data_list, list) or not data_list:
            return await update.message.reply_text(f'No results for \"{query}\".')

        # Show top 5
        top5 = data_list[:5]
        lines = [
            f"{i+1}. {anime.get('title','–')} (slug: {anime.get('id','–')})"
            for i, anime in enumerate(top5)
        ]
        await update.message.reply_text(
            f"Top results for '{query}':\n\n" + "\n".join(lines)
        )

    except Exception as e:
        logger.error("Search error: %s\nResponse was: %s",
                     e, json.dumps(raw, indent=2))
        await update.message.reply_text('Error searching anime. Please try again.')

# /get command
async def get_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        return await update.message.reply_text('Usage: /get <animeSlug> <episodeNumber>')

    anime_slug = context.args[0]
    try:
        ep_num = int(context.args[1])
    except ValueError:
        return await update.message.reply_text('Episode number must be an integer.')

    try:
        # 1. Episodes list
        eps_res = requests.get(f"{API_BASE_URL}/episodes/{anime_slug}")
        eps_res.raise_for_status()
        episodes = eps_res.json()
        ep_item = next(
            (e for e in episodes if f"Episode {ep_num}" in e.get('title', "")),
            None
        )
        if not ep_item:
            return await update.message.reply_text(
                f'Episode {ep_num} not found for {anime_slug}.'
            )

        # 2. Servers list
        srv_res = requests.get(f"{API_BASE_URL}/servers", params={'id': ep_item['id']})
        srv_res.raise_for_status()
        hd2 = next(
            (s for s in srv_res.json().get('sub', []) if s.get('name') == 'HD-2'),
            None
        )
        if not hd2:
            return await update.message.reply_text('HD-2 server not available.')

        # 3. Stream + subtitles
        str_res = requests.get(
            f"{API_BASE_URL}/stream",
            params={'id': ep_item['id'], 'server': hd2['name'], 'type': 'sub'}
        )
        str_res.raise_for_status()
        data = str_res.json()

        # Send download link
        await update.message.reply_text(
            f"📥 *Download Link*:\n{data['streamingLink']}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Send subtitles
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
        await update.message.reply_text('An error occurred. Please try again later.')

# Main entry point
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('search', search))
    app.add_handler(CommandHandler('get', get_episode))

    logger.info('Bot is starting...')
    app.run_polling()
