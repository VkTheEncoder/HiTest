import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
def load_config():
    load_dotenv()
    return os.getenv('BOT_TOKEN'), os.getenv('API_BASE_URL')

BOT_TOKEN, API_BASE_URL = load_config()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# /search command
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Usage: /search <anime name>')
        return
    query = ' '.join(context.args)
    try:
        resp = requests.get(f"{API_BASE_URL}/search", params={'key': query})
        data = resp.json().get('data', resp.json())
        if not data:
            await update.message.reply_text(f'No results for "{query}".')
            return
        results = data[:5]
        text = '\n'.join(
            [f"{i+1}. {anime['title']} (slug: {anime['id']})" for i, anime in enumerate(results)]
        )
        await update.message.reply_text(f"Top results for '{query}':\n{text}")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text('Error searching anime.')

# /get command
async def get_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Usage: /get <animeSlug> <episodeNumber>')
        return
    anime_slug = context.args[0]
    try:
        ep_num = int(context.args[1])
    except ValueError:
        await update.message.reply_text('Episode number must be an integer.')
        return

    # Fetch episodes list
    try:
        eps_res = requests.get(f"{API_BASE_URL}/episodes/{anime_slug}")
        eps_res.raise_for_status()
        episodes = eps_res.json()
        ep_item = next(
            (e for e in episodes if f"Episode {ep_num}" in e.get('title', '')), None
        )
        if not ep_item:
            await update.message.reply_text(f'Episode {ep_num} not found for {anime_slug}.')
            return

        # Fetch servers
        srv_res = requests.get(f"{API_BASE_URL}/servers", params={'id': ep_item['id']})
        srv_res.raise_for_status()
        hd2 = next((s for s in srv_res.json().get('sub', []) if s.get('name') == 'HD-2'), None)
        if not hd2:
            await update.message.reply_text('HD-2 server not available.')
            return

        # Fetch stream & subtitles
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
        logger.error(e)
        await update.message.reply_text('An error occurred. Please try again later.')

# Main
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('search', search))
    app.add_handler(CommandHandler('get', get_episode))

    logger.info('Bot is starting...')
    app.run_polling()
