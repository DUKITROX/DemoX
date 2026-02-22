# DemoX

AI agent for automating demos so you can focus on things that matter.

## Prerequisites

- Python 3.10+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)
- An [Eleven labs API key](https://elevenlabs.io/)

## Setup

1. Clone the repository:

```bash
git clone https://github.com/DUKITROX/demogorgux.git
cd demogorgux
```

2. Create a `.env` file in the project root with your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=sk_...
```

3. Run the app:

```bash
./run.sh
```

This will automatically:
- Create a Python virtual environment (`.venv`)
- Install all Python dependencies from `requirements.txt`
- Download the Playwright Chromium browser
- Build the React frontend
- Start the server

> **Note:** The first run takes a bit longer since it needs to install dependencies and build the frontend. Wait until you see `DemoX running on http://localhost:8000` before opening the browser.

4. Open [http://localhost:8000](http://localhost:8000) and click **Launch Demo**.

## Optional environment variables

You can also add these to your `.env` file to start already logged in to Monkeytype:
