from dotenv import load_dotenv
from interactions import Client, Intents, listen
from interactions.api.events import MessageCreate
import requests
import os

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENWEB_API_URL = os.getenv("OPENWEB_API_URL")
MODEL_NAME = os.getenv("MODEL_NAME")
MONITORED_CHANNEL_ID = int(os.getenv("MONITORED_CHANNEL_ID"))
OPENWEB_API_KEY = os.getenv("OPENWEB_API_KEY")

bot = Client(
    token=DISCORD_TOKEN,
    intents=Intents.ALL
)

@listen()
async def on_message_create(event: MessageCreate):
    message = event.message
    try:
        channel_id = message.channel.id
        parent_id = getattr(message.channel, "parent_id", None) 

        if channel_id == MONITORED_CHANNEL_ID or parent_id == MONITORED_CHANNEL_ID:
            if not message.author.bot:
                await process_message(message)
    except Exception:
        pass

async def process_message(message):
    question = message.content
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": question}
        ]
    }
    headers = {
        "Authorization": f"Bearer {OPENWEB_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            OPENWEB_API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        if response.status_code == 200:
            answer = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No response.")
            await message.reply(answer)
    except Exception:
        pass
      
bot.start()
