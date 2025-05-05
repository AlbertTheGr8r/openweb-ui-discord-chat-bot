import logging
from dotenv import load_dotenv
from interactions import Client, Intents, listen
from interactions.api.events import MessageCreate
import requests
import os

# Configure logging
LOG_LEVEL = os.getenv("BOT_LOG_LEVEL", "DEBUG").upper()
LOG_FILE = "bot.log"

# Set up logger
logger = logging.getLogger("discord_bot")
logger.setLevel(LOG_LEVEL)

# Create file handler
file_handler = logging.FileHandler(
    filename=LOG_FILE,
    encoding="utf-8",
    mode="w"
)

# Create console handler
console_handler = logging.StreamHandler()

# Set up formatter
formatter = logging.Formatter(
    fmt="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Add formatter to handlers
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Load environment variables
load_dotenv()

try:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    OPENWEB_API_URL = os.getenv("OPENWEB_API_URL")
    MODEL_NAME = os.getenv("MODEL_NAME")
    MONITORED_CHANNEL_ID = int(os.getenv("MONITORED_CHANNEL_ID"))
    OPENWEB_API_KEY = os.getenv("OPENWEB_API_KEY")

    logger.info(f"Loaded configuration variables successfully")
except Exception as e:
    logger.error(f"Failed to load environment variables: {str(e)}")
    raise

bot = Client(
    token=DISCORD_TOKEN,
    intents=Intents.ALL
)

@listen()
async def on_message_create(event: MessageCreate):
    """Listen for new messages"""
    message = event.message
    
    # Log message receipt
    logger.debug(f"Received message ID {message.id} from {message.author.username}")
    
    try:
        channel_id = message.channel.id
        parent_id = getattr(message.channel, "parent_id", None)

        # Log channel information
        logger.info(
            f"Message received in channel {channel_id} "
            f"(Parent: {parent_id}) from {message.author.username}"
        )

        if channel_id == MONITORED_CHANNEL_ID or parent_id == MONITORED_CHANNEL_ID:
            if not message.author.bot:
                await process_message(message)
                logger.debug("Message processed successfully")
        else:
            logger.debug("Channel not monitored, skipping message")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise

async def process_message(message):
    """Process incoming message and generate response"""
    question = message.content
    
    # Prepare API payload
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
    
    logger.debug(f"Preparing API request with model: {MODEL_NAME}")
    
    try:
        # Make API request
        response = requests.post(
            OPENWEB_API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Log response status
        logger.info(f"API response status: {response.status_code}")
        
        if response.status_code == 200:
            # Parse response
            answer = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No response.")
            
            # Log successful response
            logger.debug("Received valid API response")
            
            # Send reply
            await message.reply(answer)
            logger.info("Sent response to user")
        else:
            logger.warning(f"Invalid API response status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error processing API request: {str(e)}")

# Start bot
logger.info("Starting Discord bot...")
bot.start()
