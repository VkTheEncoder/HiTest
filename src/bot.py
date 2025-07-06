import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
t = load_dotenv()  # loads .env file
BOT_TOKEN = os.getenv('BOT_TOKEN')
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

# /search command
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        return await update.message.reply_text('Usage: /search <anime name>')

    query = ' '.join(context.args)
    try:
        resp = requests.get(
            f"{API_BASE_URL}/search",
            params={'keyword': query}
        )
        raw = resp.json()
    except Exception as e:
        logger.error("Search HTTP error: %s", e)
        return await update.message.reply_text('Error searching anime.')

    # Handle API wrapper
    if not raw.get('success'):
        return await update.message.reply_text(f'No results for "{query}".')
    results = raw.get('data', {}).get('response', [])
    if not isinstance(results, list) or not results:
        return await update.message.reply_text(f'No results for "{query}".')

    # Top 5
    top5 = results[:5]
    lines = [
        f"{i+1}. {item.get('title','–')} (slug: {item.get('id','–')})"
        for i, item in enumerate(top5)
    ]
    await update.message.reply_text(
        f"Top results for '{query}':\n\n" + "\n".join(lines)
    )

# /get command with positional indexing
async def get_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        return await update.message.reply_text(
            'Usage: /get <animeSlug> <episodeNumber>'
        )

    # Clean the slug
    raw_slug = context.args[0]
    anime_slug = raw_slug.split('?', 1)[0]
    try:
        ep_num = int(context.args[1])
    except ValueError:
        return await update.message.reply_text('Episode number must be an integer.')

    try:
        # 1) Episodes list
        eps_res = requests.get(f"{API_BASE_URL}/episodes/{anime_slug}")
        eps_res.raise_for_status()
        raw_eps = eps_res.json()

        # Unwrap JSON envelope
        if isinstance(raw_eps, dict) and raw_eps.get('success'):
            data = raw_eps.get('data', {})
            if isinstance(data, list):
                episodes_list = data
            elif isinstance(data, dict) and isinstance(data.get('response'), list):
                episodes_list = data['response']
            else:
                episodes_list = []
        elif isinstance(raw_eps, list):
            episodes_list = raw_eps
        else:
            episodes_list = []

        # Validate index
        if ep_num < 1 or ep_num > len(episodes_list):
            return await update.message.reply_text(
                f'Episode {ep_num} not found for "{anime_slug}".'
            )
        # Pick by order
        ep_item = episodes_list[ep_num - 1]

        # 2) Fetch servers and pick HD-2 by its index=1
        srv_res = requests.get(
            f"{API_BASE_URL}/servers",
            params={'id': ep_item['id']}
        )
        srv_res.raise_for_status()
        sub_servers = srv_res.json().get('sub', [])
        # HD-2 is always the one with index === 1
        hd2 = next((s for s in sub_servers if s.get('index') == 1), None)
        if not hd2:
            return await update.message.reply_text(
                'HD-2 server not available for this episode.'
            )

        # 3) Fetch stream + subtitles using the server.id that the API expects
        str_res = requests.get(
            f"{API_BASE_URL}/stream",
            params={
              'id':     ep_item['id'],
              'server': hd2['id'],    # !!! use hd2['id'], not hd2['name']
              'type':   'sub'
            }
        )
        # Send download link
        await update.message.reply_text(
            f"📥 *Download Link*:\n{stream_data['streamingLink']}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Send subtitles
        subs = stream_data.get('subtitles', []) or []
        if subs:
            for sub in subs:
                await update.message.reply_text(
                    f"💬 *Subtitle ({sub.get('lang','en')})*:\n{sub.get('src')}",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await update.message.reply_text('No English subtitles found.')

    except Exception as e:
        logger.error("Get error for %s ep %s: %s", anime_slug, ep_num, e)
        await update.message.reply_text(
            'An error occurred while fetching the episode. Please try again later.'
        )

# Main loop
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('search', search))
    app.add_handler(CommandHandler('get', get_episode))
    logger.info('Bot is starting...')
    app.run_polling()
