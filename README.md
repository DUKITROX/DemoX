# DemoX

AI-powered automated product demonstration system. An agent persona navigates web applications via a headless browser, answers questions, and demos features through a real-time streaming interface — all powered by Claude's Computer Use capabilities.

## Prerequisites

- Python 3.10+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

1. Clone the repository:

```bash
git clone https://github.com/DUKITROX/demogorgux.git
cd demogorgux
```

2. Create a `.env` file in the project root with your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
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

```
DEMO_LOGIN_EMAIL=your-email@example.com
DEMO_LOGIN_PASSWORD=your-password
```
