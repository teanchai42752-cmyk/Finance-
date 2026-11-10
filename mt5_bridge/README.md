# MT5 to Streamlit Community Cloud bridge

This integration is READ-ONLY. The Expert Advisor publishes prices and OHLC bars only; it does not place, modify, or close trades.

## Architecture
1. MT5 Terminal runs on a Windows PC/VPS logged in to your broker.
2. The EA publishes Bid/Ask and OHLC bars to the FastAPI receiver over HTTPS.
3. Streamlit Community Cloud reads the receiver API and calculates technical indicators.

Do not install the MetaTrader5 Python package in Streamlit Community Cloud. Its Python integration communicates with a locally running MT5 terminal, while Community Cloud runs on Debian Linux and does not host your MT5 desktop terminal.

## 1. Deploy receiver on Windows VPS
Use a Windows VPS that can run MT5 continuously. In PowerShell:

    cd mt5_bridge
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    $env:MT5_API_TOKEN = "REPLACE-WITH-A-LONG-RANDOM-SECRET"
    uvicorn receiver:app --host 127.0.0.1 --port 8000

Put a trusted HTTPS reverse proxy (for example Caddy or IIS with a valid TLS certificate) in front of port 8000. Expose HTTPS only; do not expose raw Uvicorn to the public internet.

Endpoints:
- GET /health
- POST /api/v1/ingest (Bearer token required)
- GET /api/v1/market-data?symbol=XAUUSD&timeframe=M5&limit=500 (Bearer token required)

Bars are stored in SQLite in mt5_bridge.db. Back up this file.

## 2. Configure MT5 EA
1. MT5 → File → Open Data Folder → MQL5/Experts. Copy mt5_price_publisher.mq5 there and compile it in MetaEditor.
2. Attach it to the broker's gold chart. Set InpIngestURL to your HTTPS ingest endpoint and InpApiToken to the same secret used by the API.
3. In MT5 → Tools → Options → Expert Advisors, enable Allow WebRequest for listed URL and add your HTTPS domain. WebRequest destinations must be explicitly allowed.
4. Confirm the Experts tab reports Bridge update OK.
5. The EA is read-only and does not need trading permissions.

## 3. Configure Streamlit Community Cloud
In app Settings → Secrets, add:

    MT5_API_URL = "https://YOUR-DOMAIN"
    MT5_API_TOKEN = "same-long-random-secret"

Reboot the app. In Trading Signals, select MetaTrader 5 Bridge, enter the exact broker symbol (may be XAUUSD.a or GOLD), and choose the same timeframe as the EA.

## Security
Use a strong unique token, valid HTTPS, VPS firewall rules, and backups. Never commit credentials or broker passwords to GitHub. The dashboard stops calculating MT5 signals when the last bridge heartbeat is older than 120 seconds. One EA instance publishes one symbol/timeframe.
