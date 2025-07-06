import dotenv from 'dotenv';
import TelegramBot from 'node-telegram-bot-api';
import axios from 'axios';

dotenv.config();

const BOT_TOKEN = process.env.BOT_TOKEN!;
const API_BASE = process.env.API_BASE_URL!;

if (!BOT_TOKEN || !API_BASE) {
  console.error('Error: BOT_TOKEN and API_BASE_URL must be set in .env');
  process.exit(1);
}

const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// /search command
bot.onText(/\/search (.+)/, async (msg, match) => {
  const chatId = msg.chat.id;
  const query = match![1].trim();

  try {
    const res = await axios.get(`${API_BASE}/search`, {
      params: { key: query }
    });
    const results: Array<{ title: string; id: string }> = res.data.data || res.data;
    if (!results.length) {
      return bot.sendMessage(chatId, `No results found for "${query}".`);
    }

    // List top 5
    const top5 = results.slice(0, 5);
    const list = top5
      .map((anime, i) => `${i + 1}. ${anime.title} (slug: ${anime.id})`)
      .join('\n');

    await bot.sendMessage(
      chatId,
      `Top results for "${query}":\n\n${list}`
    );
  } catch (err) {
    console.error(err);
    bot.sendMessage(chatId, 'Error searching anime. Please try again later.');
  }
});

// /get command
bot.onText(/\/get (\S+) (\d+)/, async (msg, match) => {
  const chatId = msg.chat.id;
  const animeSlug = match![1];
  const epNum = parseInt(match![2], 10);

  try {
    // Fetch episodes
    const epsRes = await axios.get(`${API_BASE}/episodes/${animeSlug}`);
    const episodes: Array<{ id: string; title: string }> = epsRes.data;
    const ep = episodes.find(e => {
      const m = e.title.match(/Episode\s*(\d+)/i);
      return m && parseInt(m[1], 10) === epNum;
    });
    if (!ep) {
      return bot.sendMessage(chatId, `Episode ${epNum} not found for ${animeSlug}.`);
    }

    // Fetch servers
    const srvRes = await axios.get(`${API_BASE}/servers`, { params: { id: ep.id } });
    const hd2 = srvRes.data.sub.find((s: any) => s.name === 'HD-2');
    if (!hd2) {
      return bot.sendMessage(chatId, 'HD-2 server not available for this episode.');
    }

    // Fetch stream & subtitles
    const strRes = await axios.get(`${API_BASE}/stream`, {
      params: { id: ep.id, server: hd2.name, type: 'sub' }
    });
    const { streamingLink, subtitles } = strRes.data;

    await bot.sendMessage(
      chatId,
      `📥 *Download Link*:\n${streamingLink}`,
      { parse_mode: 'Markdown' }
    );

    if (subtitles?.length) {
      const subMsg = subtitles
        .map((s: any) => `💬 *Subtitle (${s.lang})*:\n${s.src}`)
        .join('\n\n');
      await bot.sendMessage(chatId, subMsg, { parse_mode: 'Markdown' });
    } else {
      await bot.sendMessage(chatId, 'No English subtitles found.', { parse_mode: 'Markdown' });
    }
  } catch (err) {
    console.error(err);
    bot.sendMessage(chatId, 'An error occurred. Please try again later.');
  }
});

console.log('Bot is up and running.');
