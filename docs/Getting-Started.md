# Getting Started

`tgcf` is an advanced Telegram chat forwarding automation tool.

## Operating Modes

`tgcf` features two distinct operating modes depending on your specific requirements:

- **Live Mode**: The system continuously listens for incoming messages in real-time and forwards them based on your rules.
- **Past Mode**: The system performs a one-time operation to dump the existing historical messages from a source chat and forward them.

## Account Types

You can authenticate `tgcf` using one of two account types:

1. **User Account**: Operates as a regular Telegram user. Ideal for forwarding from private groups or channels where you are just a regular member.
2. **Bot Account**: Operates using a bot token obtained from [@BotFather](https://telegram.me/BotFather). 
   - **Important for Bots**: The bot *must* have its "Privacy Mode" disabled via @BotFather if you want it to listen to standard messages in groups.

## Generating a Session String

To authenticate securely without exposing credentials, `tgcf` uses session strings.

1. Ensure you have Python installed.
2. Run the session generator in your terminal:
   ```shell
   pip install tg-login
   tg-login
   ```
3. Follow the prompts. The system will print a safe session string. **Never share this string with anyone.** Save it to your `tgcf` configuration.

## Basic Invocation

If you prefer the command line over the Web UI, you can invoke your forwards directly:

```shell
# Set required environment variables
export TGCF_MODE=live
# or export TGCF_MODE=past

# Run the system
tgcf
```
