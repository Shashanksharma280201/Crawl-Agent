#!/usr/bin/env python3
"""Entry point: launch the headless saved-content dashboard."""
from web import app

if __name__ == "__main__":
    # Port 5050 (not 5000) — macOS AirPlay Receiver squats on 5000.
    print("Headless dashboard -> http://localhost:5050")
    app.run(host="127.0.0.1", port=5050, threaded=True)
