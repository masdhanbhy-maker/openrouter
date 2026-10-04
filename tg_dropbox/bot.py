"""Telegram -> Dropbox uploader.

Watches Telegram group(s) and uploads documents that match a filter
(file extension / name keyword / sender) to a Dropbox folder. The Dropbox
desktop app on Windows then syncs that folder to the PC.
"""
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("tg-dropbox")

TG = "https://api.telegram.org"
TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024  # Bot API getFile limit


def env_list(name, cast=str):
    return [cast(x.strip()) for x in os.getenv(name, "").split(",") if x.strip()]


class Config:
    def __init__(self):
        self.token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_ids = set(env_list("ALLOWED_CHAT_IDS", int))
        self.user_ids = set(env_list("ALLOWED_USER_IDS", int))
        self.extensions = {e.lower().lstrip(".") for e in env_list("ALLOWED_EXTENSIONS")}
        self.keywords = [k.lower() for k in env_list("FILENAME_KEYWORDS")]
        self.app_key = os.environ["DROPBOX_APP_KEY"]
        self.app_secret = os.environ["DROPBOX_APP_SECRET"]
        self.refresh_token = os.environ["DROPBOX_REFRESH_TOKEN"]
        self.folder = "/" + os.getenv("DROPBOX_FOLDER", "/TelegramUploads").strip("/")
        self.by_chat = os.getenv("SUBFOLDER_PER_CHAT", "true").lower() == "true"
        self.confirm = os.getenv("CONFIRM_IN_CHAT", "true").lower() == "true"
        self.state_file = Path(os.getenv("STATE_FILE", "state.json"))


class Dropbox:
    def __init__(self, cfg):
        self.cfg, self.token, self.expires = cfg, None, 0

    def _access_token(self):
        if time.time() > self.expires - 60:
            r = requests.post(
                "https://api.dropbox.com/oauth2/token",
                data={"grant_type": "refresh_token", "refresh_token": self.cfg.refresh_token},
                auth=(self.cfg.app_key, self.cfg.app_secret),
                timeout=30,
            )
            r.raise_for_status()
            j = r.json()
            self.token, self.expires = j["access_token"], time.time() + j["expires_in"]
        return self.token

    def upload(self, path, data):
        """Upload bytes (<=150MB) to `path`; never overwrites (autorename)."""
        r = requests.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Dropbox-API-Arg": json.dumps(
                    {"path": path, "mode": "add", "autorename": True, "mute": True},
                    ensure_ascii=True,
                ),
                "Content-Type": "application/octet-stream",
            },
            data=data,
            timeout=300,
        )
        r.raise_for_status()
        return r.json()["path_display"]


def safe(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "unnamed"


class Bot:
    def __init__(self, cfg):
        self.cfg, self.dbx = cfg, Dropbox(cfg)
        self.api = f"{TG}/bot{cfg.token}"
        self.seen = set()
        if cfg.state_file.exists():
            self.seen = set(json.loads(cfg.state_file.read_text()).get("seen", []))

    def _save(self):
        self.cfg.state_file.write_text(json.dumps({"seen": sorted(self.seen)}))

    def call(self, method, **params):
        r = requests.post(f"{self.api}/{method}", json=params, timeout=70)
        r.raise_for_status()
        return r.json()["result"]

    def reply(self, msg, text):
        try:
            self.call("sendMessage", chat_id=msg["chat"]["id"], text=text,
                      reply_to_message_id=msg["message_id"])
        except Exception:
            log.exception("reply failed")

    def wanted(self, msg, doc):
        c = self.cfg
        if c.chat_ids and msg["chat"]["id"] not in c.chat_ids:
            return False
        if c.user_ids and msg.get("from", {}).get("id") not in c.user_ids:
            return False
        name = doc.get("file_name", "")
        if c.extensions and name.rsplit(".", 1)[-1].lower() not in c.extensions:
            return False
        if c.keywords and not any(k in name.lower() for k in c.keywords):
            return False
        return True

    def handle(self, msg):
        text = msg.get("text", "")
        if text.startswith("/id"):
            self.reply(msg, f"chat_id: {msg['chat']['id']}\nuser_id: {msg.get('from', {}).get('id')}")
            return
        doc = msg.get("document")
        if not doc or not self.wanted(msg, doc):
            return
        uid = doc["file_unique_id"]
        if uid in self.seen:
            return
        name = safe(doc.get("file_name", uid))
        if doc.get("file_size", 0) > TG_DOWNLOAD_LIMIT:
            self.reply(msg, f"❌ {name} is over Telegram's 20 MB bot download limit.")
            return
        try:
            info = self.call("getFile", file_id=doc["file_id"])
            data = requests.get(f"{TG}/file/bot{self.cfg.token}/{info['file_path']}", timeout=120)
            data.raise_for_status()
            parts = [self.cfg.folder]
            if self.cfg.by_chat:
                parts.append(safe(msg["chat"].get("title") or str(msg["chat"]["id"])))
            saved = self.dbx.upload("/".join(parts + [name]), data.content)
        except Exception as e:
            log.exception("upload failed for %s", name)
            self.reply(msg, f"❌ Upload failed for {name}: {e}")
            return
        self.seen.add(uid)
        self._save()
        log.info("uploaded %s -> %s", name, saved)
        if self.cfg.confirm:
            self.reply(msg, f"✅ Saved to Dropbox: {saved}")

    def run(self):
        offset = None
        log.info("Bot started. Filters: chats=%s exts=%s keywords=%s",
                 self.cfg.chat_ids or "any", self.cfg.extensions or "any", self.cfg.keywords or "any")
        while True:
            try:
                updates = self.call("getUpdates", offset=offset, timeout=50,
                                    allowed_updates=["message", "channel_post"])
            except Exception:
                log.exception("polling error")
                time.sleep(5)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                m = u.get("message") or u.get("channel_post")
                if m:
                    self.handle(m)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        Bot(Config()).run()
    except KeyError as e:
        sys.exit(f"Missing env var {e}. Copy .env.example to .env and fill it in.")
