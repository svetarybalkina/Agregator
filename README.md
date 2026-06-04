# Telegram Channel Aggregator

Console app that collects top Telegram posts from the active channel collection and sends a report via a Telegram bot.

## Setup

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Create a local `.env` from `.env.example`.

3. Create a local `collections.json` from `collections.example.json`, or provide `COLLECTIONS_JSON` as an environment/GitHub Secret.

4. Run the app:

```powershell
python .\main.py
```

## Required Secrets

Do not commit these values. Keep them in local `.env` or in GitHub Secrets if the app is run from CI/CD:

- `BOT_TOKEN`
- `API_ID`
- `API_HASH`
- `ADMIN_IDS`
- `REPORT_CHAT_ID`
- `COLLECTIONS_JSON` if private channel lists are stored as a secret instead of `collections.json`

## Local Data

These files are local runtime data and are ignored by Git:

- `.env`
- `collections.json`
- `*.session`
- `aggregator.log`
- `posted*.json`
- `queue.json`

## Bot Commands

- `/podborki` - list collections
- `/tekushaya_podborka` - show active collection
- `/run_now` - run collection manually
- `/status` - show status
- `/chat_id` - show current chat ID
