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

# === /get command (defensive JSON unwrapping) ===
async def get_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        return await update.message.reply_text(
            'Usage: /get <animeSlug> <episodeNumber>'
        )

    # Clean up the slug (remove any ?ref=…)
    raw_slug   = context.args[0]
    anime_slug = raw_slug.split('?', 1)[0]

    # Parse episode number
    try:
        ep_num = int(context.args[1])
    except ValueError:
        return await update.message.reply_text('Episode number must be an integer.')

    # 1) Fetch the “episodes” endpoint
    try:
        eps_res = requests.get(f"{API_BASE_URL}/episodes/{anime_slug}")
        # Try to parse JSON no matter what status code
        try:
            raw_eps = eps_res.json()
        except ValueError:
            logger.error("Could not JSON-decode episodes for %s: %s",
                         anime_slug, eps_res.text[:200])
            raise

        # Figure out where the episode array lives:
        if isinstance(raw_eps, list):
            episodes_list = raw_eps
        elif isinstance(raw_eps, dict):
            # { success: bool, data: [...] }
            if raw_eps.get('success') and isinstance(raw_eps.get('data'), list):
                episodes_list = raw_eps['data']
            # { success: bool, data: { response: [...] } }
            elif (raw_eps.get('success')
                  and isinstance(raw_eps.get('data'), dict)
                  and isinstance(raw_eps['data'].get('response'), list)):
                episodes_list = raw_eps['data']['response']
            # Maybe it’s directly { data: [...] }
            elif isinstance(raw_eps.get('data'), list):
                episodes_list = raw_eps['data']
            else:
                # Last ditch: flatten any single‐level lists inside data
                val = raw_eps.get('data')
                episodes_list = val if isinstance(val, list) else []
        else:
            episodes_list = []

        if not episodes_list:
            return await update.message.reply_text(
                f"No episodes found for \"{anime_slug}\"."
            )

        # Find the one matching “Episode {number}”
        ep_item = next(
            (e for e in episodes_list
             if isinstance(e, dict)
             and f"Episode {ep_num}" in e.get('title', "")),
            None
        )
        if not ep_item:
            return await update.message.reply_text(
                f'Episode {ep_num} not found for "{anime_slug}".'
            )

        # 2) Fetch servers
        srv_res = requests.get(
            f"{API_BASE_URL}/servers",
            params={'id': ep_item['id']}
        )
        srv_res.raise_for_status()
        servers = srv_res.json().get('sub', [])
        hd2 = next((s for s in servers if s.get('name') == 'HD-2'), None)
        if not hd2:
            return await update.message.reply_text(
                'HD-2 server not available for this episode.'
            )

        # 3) Fetch the stream + subtitles
        str_res = requests.get(
            f"{API_BASE_URL}/stream",
            params={
                'id':     ep_item['id'],
                'server': hd2['name'],
                'type':   'sub'
            }
        )
        str_res.raise_for_status()
        stream_data = str_res.json()

        # Send download link
        await update.message.reply_text(
            f"📥 *Download Link*:\n{stream_data['streamingLink']}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Send any English subtitles
        subs = stream_data.get('subtitles', [])
        if subs:
            for sub in subs:
                await update.message.reply_text(
                    f"💬 *Subtitle ({sub.get('lang','??')})*:\n{sub.get('src')}",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await update.message.reply_text('No English subtitles found.')

    except Exception as e:
        logger.error("Get error for %s ep %s: %s", anime_slug, ep_num, e)
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
