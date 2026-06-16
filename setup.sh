#!/usr/bin/env bash
# Setup for the headless Saved-Content Collector.
# Installs Python deps + agent-browser, finds Chrome, prepares .env.
set -u
cd "$(dirname "$0")" || exit 1

echo "================================================="
echo "  Saved-Content Collector — setup"
echo "================================================="

# 1) Python dependencies -----------------------------------------------------
echo
echo "[1/4] Python dependencies (flask, websocket-client, openai)…"
if command -v python3 >/dev/null 2>&1; then
  if python3 -m pip install --quiet --upgrade -r requirements.txt; then
    echo "      ✓ Python packages installed"
  else
    echo "      ! pip install failed — try:  python3 -m pip install -r requirements.txt"
  fi
else
  echo "      ✗ python3 not found. Install Python 3.8+ and re-run."
  exit 1
fi

# 2) agent-browser (headless browser driver) --------------------------------
echo
echo "[2/4] agent-browser (headless Chrome driver)…"
if command -v agent-browser >/dev/null 2>&1; then
  echo "      ✓ already installed ($(agent-browser --version 2>/dev/null | head -1))"
elif command -v npm >/dev/null 2>&1; then
  if npm install -g agent-browser >/dev/null 2>&1; then
    echo "      ✓ installed agent-browser (npm)"
  else
    echo "      ! npm global install failed (permissions?). Try one of:"
    echo "          sudo npm install -g agent-browser"
    echo "          brew install agent-browser     # macOS"
  fi
elif command -v brew >/dev/null 2>&1; then
  if brew install agent-browser >/dev/null 2>&1; then
    echo "      ✓ installed agent-browser (brew)"
  else
    echo "      ! brew install failed. Try:  npm install -g agent-browser"
  fi
else
  echo "      ✗ neither npm nor brew found."
  echo "        macOS:  brew install agent-browser   (or install Node, then npm i -g agent-browser)"
  echo "        Linux:  install Node.js 18+, then:  npm install -g agent-browser"
fi

# 3) Chrome ------------------------------------------------------------------
echo
echo "[3/4] Google Chrome…"
CHROME=""
for b in "/opt/google/chrome/chrome" \
         "$(command -v google-chrome 2>/dev/null)" \
         "$(command -v google-chrome-stable 2>/dev/null)" \
         "$(command -v chromium 2>/dev/null)" \
         "$(command -v chromium-browser 2>/dev/null)" \
         "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  if [ -n "$b" ] && [ -x "$b" ]; then CHROME="$b"; break; fi
done
if [ -n "$CHROME" ]; then
  echo "      ✓ found: $CHROME"
  echo "        (the app auto-detects this on Linux & macOS — no config needed."
  echo "         For a non-standard install, set:  export CHROME_BIN=\"/path/to/chrome\")"
else
  echo "      ✗ Chrome/Chromium not found. Install Google Chrome, then re-run."
fi

# 4) .env (OpenAI key for the optional 'Summarize with AI' feature) ----------
echo
echo "[4/4] Config (.env)…"
if [ -f .env ]; then
  echo "      ✓ .env already exists"
else
  printf 'OPENAI_API_KEY=\nOPENAI_MODEL=gpt-4o\n' > .env
  echo "      ✓ created .env"
  echo "      → (optional) add your OpenAI key for 'Summarize with AI':"
  echo "          edit .env and set OPENAI_API_KEY=sk-..."
fi

mkdir -p data .profile

echo
echo "================================================="
echo "  Setup complete."
echo
echo "  Launch the web app:"
echo "      python3 app.py        →  open http://localhost:5000"
echo
echo "  Then in the browser: click 'Log in' on a platform card,"
echo "  sign in once, and hit 'Crawl'. Data is saved to data/<platform>.json"
echo "================================================="
