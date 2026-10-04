# Telegram → Dropbox uploader

A small bot that watches your Telegram group and uploads matching documents to
Dropbox. The Dropbox desktop app on your Windows PC syncs the folder down
automatically (default: `Dropbox/TelegramUploads/<group name>/`).

## Setup

1. **Telegram bot**: message [@BotFather](https://t.me/BotFather) → `/newbot`, copy the token.
   Add the bot to your group. Either make it a group admin or disable privacy
   (`/setprivacy` → Disable), otherwise it can't see documents posted in the group.
2. **Dropbox app**: https://www.dropbox.com/developers/apps → *Create app* → Scoped access →
   App folder (or Full Dropbox). Under *Permissions* enable `files.content.write`, then Submit.
   Copy the app key and secret.
3. **Refresh token**: `python get_dropbox_token.py` and follow the prompts.
4. `pip install -r requirements.txt`, copy `.env.example` to `.env`, fill it in.
5. Send `/id` in the group to get its chat id → put it in `ALLOWED_CHAT_IDS`.
6. `python bot.py`

## Choosing which documents get uploaded

Set in `.env` (all optional, combined with AND):

- `ALLOWED_CHAT_IDS` – only these groups
- `ALLOWED_USER_IDS` – only files sent by these people
- `ALLOWED_EXTENSIONS` – e.g. `pdf,docx,xlsx`
- `FILENAME_KEYWORDS` – file name must contain one of these (e.g. `invoice,contract`)

## Notes

- Telegram's bot API only lets bots download files up to **20 MB**; larger files get a ❌ reply.
- Existing Dropbox files are never overwritten (Dropbox auto-renames); already-uploaded
  files are remembered in `state.json` to avoid duplicates.
- To run on Windows permanently: Task Scheduler → run `python bot.py` at logon, or host it on any always-on machine.
- Only sent as *documents/files* are handled (photos sent compressed are ignored).
