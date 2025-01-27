# Discord Bot with OpenWeb-UI Integration

This repository contains a Discord bot script that listens to messages in specific channels or threads within Discord and processes these messages using the OpenWeb API for AI-driven responses.

## Features

- Listens to messages in a designated channel or threads within that channel.
- Sends user messages to the OpenWeb API for processing.
- Replies with AI-generated responses based on the user's input.
- Ignores messages from bot users to prevent loops or spam.

## Prerequisites

To run this bot, ensure you have the following:

1. **Python 3.8 or higher** installed.
2. Required Python packages installed (see [Installation](#installation)).
3. A Discord bot token.
4. Access to the OpenWeb API, including your API key and endpoint URL.

## Setup

1. Clone the repository:
    ```bash
    git clone https:/github.com/ajarmoszuk/openweb-ui-discord-chat-bot
    cd openweb-ui-discord-chat-bot
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Configure your environment:
    - Replace the placeholders in the script with your actual values:
      - `DISCORD_TOKEN`: Your Discord bot token.
      - `OPENWEB_API_URL`: The OpenWeb API endpoint.
      - `MODEL_NAME`: The name of the model to use in the OpenWeb API.
      - `MONITORED_CHANNEL_ID`: The ID of the channel to monitor.
      - `OPENWEB_API_KEY`: Your OpenWeb API key.

## Usage

1. Run the bot:
    ```bash
    python bot.py
    ```

2. Add the bot to your Discord server with appropriate permissions, ensuring it has access to the monitored channel.

3. The bot will now listen to messages in the specified channel and threads, send them to the OpenWeb API, and reply with the generated response.

## File Details

### `bot.py`
The main script for the bot. It includes:
- Initialization of the bot client.
- Listener for new messages (`on_message_create`).
- Integration with the OpenWeb API (`process_message`).

## Environment Variables

Instead of hardcoding sensitive information, you can use environment variables for configuration:

```bash
export DISCORD_TOKEN="your-discord-bot-token"
export OPENWEB_API_URL="http://your-openweb-api-endpoint/api/chat/completions"
export MODEL_NAME="your-model-name"
export MONITORED_CHANNEL_ID=123456789012345678
export OPENWEB_API_KEY="your-openweb-user-jwt-api-key"
```

Modify the script to retrieve these values using `os.getenv`:
```python
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENWEB_API_URL = os.getenv("OPENWEB_API_URL")
MODEL_NAME = os.getenv("MODEL_NAME")
MONITORED_CHANNEL_ID = int(os.getenv("MONITORED_CHANNEL_ID"))
OPENWEB_API_KEY = os.getenv("OPENWEB_API_KEY")
```

## Dependencies

- `interactions`: For Discord bot interactions.
- `requests`: For making HTTP requests to the OpenWeb API.

Install these packages via:
```bash
pip install interactions requests
```

## License

This project is licensed under the [MIT License](LICENSE).

## Troubleshooting

- **Bot not responding:**
  - Check that the bot is added to the server and has permissions to read and send messages in the monitored channel.
  - Verify the `MONITORED_CHANNEL_ID` is correctly set.

- **Error with OpenWeb API:**
  - Confirm that your API URL, key, and model name are correctly configured.
  - Check the OpenWeb API documentation for additional troubleshooting steps.

- **Timeouts or delays:**
  - The OpenWeb API request includes a 30-second timeout. Ensure the API is responsive and capable of handling the request load.

---

Feel free to contribute by submitting issues or pull requests!


