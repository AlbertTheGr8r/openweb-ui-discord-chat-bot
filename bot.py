import logging
import os
import asyncio
import aiohttp
import re
from dotenv import load_dotenv
from interactions import (
    Client, Intents, listen, Activity, ActivityType, Status,
    Message, Embed, ActionRow, Button, ButtonStyle, ComponentContext,
    component_callback, ThreadChannel, User
)
from interactions.api.events import MessageCreate

# --- Configuration ---
load_dotenv()

# Logging Setup
LOG_LEVEL = os.getenv("BOT_LOG_LEVEL", "INFO").upper()
LOG_FILE = "bot.log"
logger = logging.getLogger("discord_bot")
logger.setLevel(LOG_LEVEL)
formatter = logging.Formatter(
    fmt="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
# File Handler
file_handler = logging.FileHandler(filename=LOG_FILE, encoding="utf-8", mode="w")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Environment Variables Loading
try:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    OPENWEB_API_URL = os.getenv("OPENWEB_API_URL")
    MODEL_NAME = os.getenv("MODEL_NAME")
    MONITORED_CHANNEL_ID = int(os.getenv("MONITORED_CHANNEL_ID")) # Ensure this is an integer
    OPENWEB_API_KEY = os.getenv("OPENWEB_API_KEY")
    API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", 180))
    CONTEXT_MESSAGES_COUNT = int(os.getenv("CONTEXT_MESSAGES_COUNT", 5))
    EMBED_COLOR_STR = os.getenv("EMBED_COLOR", "#FFA500")
    DISPLAY_SOURCES = os.getenv("DISPLAY_SOURCES", "True").lower() == "true"
    ENABLE_FEEDBACK_REACTIONS = os.getenv("ENABLE_FEEDBACK_REACTIONS", "True").lower() == "true"
    # RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 5)) # Rate limit logic not fully implemented below

    # Basic check for essential vars
    if not all([DISCORD_TOKEN, OPENWEB_API_URL, MODEL_NAME, MONITORED_CHANNEL_ID, OPENWEB_API_KEY]):
        raise ValueError("One or more essential environment variables are missing.")

    logger.info("Loaded configuration variables successfully.")
    logger.info(f"Monitored Channel ID: {MONITORED_CHANNEL_ID}")
    logger.info(f"Model Name: {MODEL_NAME}")
    logger.info(f"Context Message Count: {CONTEXT_MESSAGES_COUNT}")

except Exception as e:
    logger.error(f"Failed to load or validate environment variables: {str(e)}")
    raise SystemExit("Configuration Error")

# --- Global Variables ---
aiohttp_session = None
# Placeholder for storing data needed for refresh button.
# WARNING: Global dict is simple but not robust for multiple simultaneous requests or scaling.
# Consider a more advanced cache (e.g., using cachetools library) or database if needed.
feedback_cache = {}

# --- Bot Initialization ---
bot = Client(
    token=DISCORD_TOKEN,
    intents=Intents.DEFAULT | Intents.GUILD_MESSAGES | Intents.MESSAGE_CONTENT, # Specific intents
    status=Status.ONLINE,
    activity=Activity(name="documents...", type=ActivityType.WATCHING) # Optional status
)

# --- Event Listeners ---
@listen()
async def on_startup():
    """Initialize resources on bot startup."""
    global aiohttp_session
    if not aiohttp_session or aiohttp_session.closed:
         aiohttp_session = aiohttp.ClientSession()
         logger.info("aiohttp session created.")
    logger.info(f"Bot logged in as {bot.user}. Ready!")

@listen()
async def on_shutdown():
    """Clean up resources on bot shutdown."""
    global aiohttp_session
    if aiohttp_session:
        await aiohttp_session.close()
        logger.info("aiohttp session closed.")

@listen(MessageCreate)
async def on_message_create(event: MessageCreate):
    """Listen for new messages and trigger processing if relevant."""
    message = event.message

    # Ignore messages from bots (including self)
    if message.author.bot:
        return

    logger.debug(f"Received message ID {message.id} from {message.author.username} in channel {message.channel.id}")

    try:
        # Check channel first
        in_monitored_channel = message.channel.id == MONITORED_CHANNEL_ID
        # Check if it's a thread within the monitored channel
        if not in_monitored_channel and isinstance(message.channel, ThreadChannel) and message.channel.parent_id == MONITORED_CHANNEL_ID:
            in_monitored_channel = True

        if not in_monitored_channel:
            logger.debug(f"Message {message.id} not in monitored channel/thread {MONITORED_CHANNEL_ID}.")
            return

        # Check if bot was mentioned or if it's a reply to the bot
        is_mention = False
        if bot.user:
            # Standard mention and nickname mention
            mention_formats = [f'<@{bot.user.id}>', f'<@!{bot.user.id}>']
            
            # Check if any of the mention formats appear in the message content
            for fmt in mention_formats:
                if fmt in message.content:
                    is_mention = True
                    logger.debug(f"Detected bot mention using format '{fmt}' in message {message.id}")
                    break
        else:
             logger.warning("Bot user object not available for mention check.")

        is_reply_to_bot = False
        if message.message_reference and message.message_reference.message_id:
            try:
                referenced_message = await message.fetch_referenced_message()
                if referenced_message.author.id == bot.user.id:
                    is_reply_to_bot = True
                    logger.debug(f"Message {message.id} is a reply to the bot.")
            except Exception as fetch_err:
                logger.warning(f"Could not fetch referenced message for {message.id}: {fetch_err}")

        if is_mention or is_reply_to_bot:
            logger.info(f"Processing message {message.id} from {message.author.username} (Mention: {is_mention}, Reply: {is_reply_to_bot})")
            if not bot.user:
                 logger.warning("Bot user object not available yet. Skipping processing.")
                 return
            await process_message(message) # Call the main processing function
            logger.debug(f"Finished processing message {message.id}")
        else:
            logger.debug(f"Message {message.id} is not a mention or reply to the bot, skipping.")

    except Exception as e:
        logger.exception(f"Error in on_message_create handler for message {message.id}:")

# --- Core Processing Function ---
async def process_message(message: Message):
    """Process incoming message, query Open WebUI, and generate response."""
    global aiohttp_session, feedback_cache
    if not aiohttp_session:
        logger.error("aiohttp session not initialized!")
        await message.reply("Sorry, there was an internal error (HTTP session).")
        return

    if not bot.user:
         logger.error("Bot user object not found during process_message!")
         return # Avoid errors if bot user isn't set somehow

    thinking_message = None

    try:
        # Start Typing Indicator
        await message.channel.trigger_typing()

        # Send thinking message
        thinking_message = await message.reply("AIbert is thinking... 🤔🤔🤔")
        logger.debug(f"Sent 'Thinking' message with ID {thinking_message.id}")

        # Query Preprocessing (Remove Mention)
        bot_mention_patterns = [f'<@!{bot.user.id}>', f'<@{bot.user.id}>']
        question = message.content
        for pattern in bot_mention_patterns:
            question = question.replace(pattern, '')
        question = question.strip()

        if not question: # Ignore if message was just a mention
            logger.debug("Message contained only mention, ignoring.")
            # Clean up thinking message
            if thinking_message: await thinking_message.delete()
            return

        # Fetch Context Messages
        context_messages = []
        if CONTEXT_MESSAGES_COUNT > 0:
            try:
                history = await message.channel.history(limit=CONTEXT_MESSAGES_COUNT, before=message).flatten()
                history.reverse() # Oldest to newest

                for msg in history:
                    role = "user" if msg.author.id != bot.user.id else "assistant"
                    content = msg.content.strip()
                    if content:
                        for pattern in bot_mention_patterns: # Remove mentions from context too
                            content = content.replace(pattern, '')
                        content = content.strip()
                        if content:
                            context_messages.append({"role": role, "content": content})
                logger.debug(f"Fetched {len(context_messages)} messages for context.")
            except Exception as hist_err:
                logger.warning(f"Could not fetch message history for context: {hist_err}")

        # Prepare API Payload
        api_messages = context_messages + [{"role": "user", "content": question}]
        payload = {
            "model": MODEL_NAME,
            "messages": api_messages
            # Add "stream": False here if your API defaults to streaming and you don't want it
        }

        headers = {
            "Authorization": f"Bearer {OPENWEB_API_KEY}",
            "Content-Type": "application/json"
        }

        logger.debug(f"Preparing API request with model: {MODEL_NAME}. Query: '{question[:100]}...' Context messages: {len(context_messages)}")

        # Make ASYNC API request
        async with aiohttp_session.post(
            OPENWEB_API_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)
        ) as response:
            logger.info(f"API response status: {response.status}")

            # Delete the "Thinking" message now that we have a response (or error)
            if thinking_message:
                try:
                    await thinking_message.delete()
                    logger.debug(f"Deleted 'Thinking' message {thinking_message.id}")
                except Exception as del_err:
                    logger.warning(f"Could not delete 'Thinking' message {thinking_message.id}: {del_err}")
                thinking_message = None

            if response.status == 200:
                response_data = await response.json()
                logger.debug(f"Raw API response data: {response_data}") # Log for investigation

                # Parse response safely
                choices = response_data.get("choices", [{}])
                first_choice = choices[0] if choices else {}
                message_data = first_choice.get("message", {})
                answer = message_data.get("content", "").strip()

                if not answer:
                    answer = "I received an empty response from the knowledge base."
                    logger.warning("API returned status 200 but content was empty.")
                    await message.reply(answer)
                else:
                    logger.debug("Received valid API response content.")
                    # Create Embed
                    try:
                        embed_color = int(EMBED_COLOR_STR.lstrip('#'), 16)
                    except ValueError:
                        embed_color = 0xFFA500
                        logger.warning(f"Invalid EMBED_COLOR '{EMBED_COLOR_STR}', using default.")

                    embed = Embed(description=answer, color=embed_color)

                    # --- Add Sources Placeholder ---
                    # TODO: Replace this with actual source parsing based on API investigation
                    sources_text = None
                    if DISPLAY_SOURCES:
                        # Example: Check a custom field (replace 'custom_sources' with actual field name if found)
                        # custom_sources = response_data.get("custom_sources")
                        # if custom_sources and isinstance(custom_sources, list):
                        #    sources_text = ", ".join([str(s) for s in custom_sources])

                        # Example: Parse from content (requires a robust function)
                        # parsed_sources = parse_sources_from_content(answer) # Implement this function
                        # if parsed_sources:
                        #    sources_text = ", ".join(parsed_sources)

                        # If no structured sources found, maybe add a generic note?
                        # sources_text = "Check text for source references."
                        pass # Remove pass when logic is added

                    if sources_text:
                        embed.set_footer(text=f"Sources: {sources_text}")
                    # --- End Sources Placeholder ---

                    # Add Feedback Buttons
                    components = []
                    if ENABLE_FEEDBACK_REACTIONS:
                        feedback_buttons = ActionRow(
                            Button(style=ButtonStyle.SUCCESS, label="👍", custom_id=f"feedback_good_{message.id}"),
                            Button(style=ButtonStyle.DANGER, label="👎", custom_id=f"feedback_bad_{message.id}"),
                            Button(style=ButtonStyle.SECONDARY, label="🔄", custom_id=f"feedback_refresh_{message.id}")
                        )
                        components.append(feedback_buttons)

                    # Send Reply with Embed and Buttons
                    bot_reply_message = await message.reply(embeds=embed, components=components)
                    logger.info(f"Sent embed response with ID {bot_reply_message.id} to user {message.author.username}")

                    # --- Store data for refresh ---
                    # TODO: Implement reliable storage for refresh context
                    if ENABLE_FEEDBACK_REACTIONS:
                         feedback_cache[bot_reply_message.id] = {"api_messages": api_messages}
                         logger.debug(f"Stored context for refresh under ID {bot_reply_message.id}")
                         # Clean up old entries from cache periodically if using global dict


            else: # Handle API errors (non-200 status)
                error_text = await response.text()
                logger.warning(f"API error status: {response.status}. Response: {error_text[:500]}") # Log beginning of error
                await message.reply(f"Sorry, I encountered an error ({response.status}) communicating with the knowledge base.")

    except asyncio.TimeoutError:
        logger.error(f"API request timed out after {API_TIMEOUT_SECONDS} seconds.")
        # --- Delete the "Thinking" message on timeout ---
        if thinking_message:
            try:
                await thinking_message.delete()
                logger.debug(f"Deleted 'Thinking' message {thinking_message.id} on timeout")
            except Exception as del_err:
                logger.warning(f"Could not delete 'Thinking' message {thinking_message.id} on timeout: {del_err}")
        # Send final error as a new reply
        await message.reply(f"Sorry, the request to the knowledge base timed out after {API_TIMEOUT_SECONDS} seconds.")
    except aiohttp.ClientError as e:
        logger.error(f"aiohttp client error: {str(e)}")
        if thinking_message: await thinking_message.delete()
        await message.reply("Sorry, there was a network error connecting to the knowledge base.")
    except Exception as e:
        logger.exception(f"Error processing message {message.id} or sending reply:")
        if thinking_message:
            try: await thinking_message.delete()
            except: pass # Ignore delete error during general exception
        try:
            await message.reply("Sorry, an unexpected error occurred while processing your request.")
        except Exception as reply_err:
            logger.error(f"Failed to send error reply for message {message.id}: {reply_err}")


# --- Component Callbacks ---
@component_callback(re.compile(r"feedback_.*")) # Listen for button interactions
async def handle_feedback(ctx: ComponentContext):
    """Handle interactions from feedback buttons."""
    global feedback_cache
    try:
        custom_id_parts = ctx.custom_id.split("_")
        feedback_type = custom_id_parts[1]
        # Original user message ID is encoded in the custom_id
        original_user_message_id = int(custom_id_parts[2])

        logger.info(f"Feedback received: User {ctx.author.username} ({ctx.author.id}) clicked {feedback_type} for bot message {ctx.message.id}")

        if feedback_type == "good" or feedback_type == "bad":
            # Log feedback more formally if needed (e.g., to a file or database)
            logger.info(f"Feedback recorded: {feedback_type.upper()} for bot message {ctx.message.id} (orig user msg: {original_user_message_id})")
            # Acknowledge ephemerally
            await ctx.send(f"Feedback ({feedback_type}) registered.", ephemeral=True)
            # Optional: Disable buttons on the original message after feedback
            # try:
            #    await ctx.edit_origin(components=[]) # Removes all components
            # except Exception as edit_err:
            #    logger.warning(f"Could not disable buttons after feedback: {edit_err}")


        elif feedback_type == "refresh":
            # --- Regenerate Response ---
            await ctx.defer(edit_origin=True) # Acknowledge interaction, will edit original embed

            # Retrieve original query data from cache
            original_data = feedback_cache.get(ctx.message.id)

            if not original_data or "api_messages" not in original_data:
                logger.warning(f"Could not find original context in cache for refresh (Bot Msg ID: {ctx.message.id})")
                await ctx.send("Sorry, I can't find the context to refresh this response.", ephemeral=True)
                return

            logger.debug(f"Refreshing response for bot message {ctx.message.id}")

            # --- TODO: Refactor API call logic into a reusable function ---
            # This section largely duplicates the API call logic from process_message
            # It's better to have a function like:
            # async def query_knowledge_base(messages: list) -> tuple[str | None, dict | None]:
            #     # ... performs API call, returns (answer_text, full_response_data) or (None, None) on error
            # answer, response_data = await query_knowledge_base(original_data["api_messages"])
            # if answer:
            #    # Rebuild embed, potentially parse sources again from response_data
            #    new_embed = Embed(...)
            #    # Potentially update footer with new sources
            #    await ctx.edit_origin(embeds=new_embed, components=ctx.message.components) # Keep buttons
            #    logger.info(f"Refreshed response for message {ctx.message.id}")
            # else:
            #    await ctx.send("Failed to refresh the response from the knowledge base.", ephemeral=True)

            # Placeholder until refactoring:
            await ctx.send("Refresh logic needs refactoring. Placeholder acknowledgment.", ephemeral=True)
            logger.warning("Refresh logic triggered but needs refactoring from process_message.")
            # --- End Placeholder ---

        else:
            logger.warning(f"Unknown feedback action type: {feedback_type}")
            await ctx.send("Unknown feedback action.", ephemeral=True)

    except Exception as e:
        logger.exception(f"Error handling component interaction {ctx.custom_id}:")
        try:
            await ctx.send("An error occurred while handling this interaction.", ephemeral=True)
        except Exception as reply_err:
             logger.error(f"Failed to send error reply for interaction {ctx.custom_id}: {reply_err}")


# --- Start Bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set. Bot cannot start.")
    else:
        logger.info("Starting Discord bot...")
        bot.start()
