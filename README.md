<h1 align="center">tgcf - Telegram Custom Forwarder</h1>

<p align="center">
  <strong>A pragmatic, highly customizable, and reliable tool for forwarding Telegram messages.</strong>
</p>

> **Note:** Maintained by [YuanSheng Chiu (@yschiu11)](https://github.com/yschiu11). This is a continuation of the original project by [Aahnik Daw](https://github.com/aahnik), engineered to keep it alive and functional.

## What is this?
At its core, `tgcf` is a message pipeline. It takes messages from a source and pipes them to a destination. 

It operates in two modes:
1. **Live:** Listens for new messages and forwards them in real-time.
2. **Past:** Dumps existing message history from designated chats.

It works with both standard User accounts and Bot accounts.

## Why use it?
Most forwarding tools are bloated, paid, or abandoned. `tgcf` provides a clean architecture built around plugins. It intercepts messages, mutates them based on rules, and forwards them. 

- **Filters:** Whitelist or blacklist messages based on logic, not guesses.
- **Mutators:** Regex search and replace, strip formatting, or append metadata (headers/footers).
- **Media Processing:** Apply watermarks to images and videos, or run OCR to extract text.

There is no cloud lock-in. You run it on your own hardware, manage your own config via JSON, or use the provided Web UI.

## Quick Start

You need Python 3.10 or newer. A virtual environment is strictly recommended.

```shell
git clone https://github.com/yschiu11/tgcf.git tgcf-server
cd tgcf-server
python3 -m venv .venv
source .venv/bin/activate

# Install the package locally
pip install .

# Set a secure password for the web interface
echo "PASSWORD=your_secure_password" >> .env

# Start the daemon
tgcf-web
```
Now open your browser, log in, configure your pipelines, and let it run.

## Getting Help

- **Documentation:** [Read the Docs](https://github.com/yschiu11/tgcf/tree/main/docs)
- **Visual Guides:** [Video Tutorials](https://www.youtube.com/channel/UCcEbN0d8iLTB6ZWBE_IDugg)

If the software fails or you encounter legitimate bugs, report them on the [Issue Tracker](https://github.com/yschiu11/tgcf/issues/new).

## Code & Contributions

Keep it simple. Write clean plugins. Don't submit unreadable code.

## License

MIT License.
Copyright (c) 2025 YuanSheng Chiu
Copyright (c) 2020 Aahnik Daw
