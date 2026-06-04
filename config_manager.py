import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any


class ConfigManager:
    def __init__(self, config_path: str = "config.json", history_dir: str = "."):
        self.config_path = config_path
        self.history_dir = history_dir
        self.config = self._load_config()
        self.collections = self._load_collections()
        self._migrate_if_needed()

    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Создайте файл {self.config_path} по шаблону")
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        self._apply_env_overrides(config)
        return config

    def _load_env_file(self, path: str) -> Dict[str, str]:
        if not os.path.exists(path):
            return {}
        result: Dict[str, str] = {}
        # utf-8-sig handles BOM so first key is parsed correctly on Windows.
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip().strip('"').strip("'")
        return result

    def _apply_env_overrides(self, config: dict):
        env = self._load_env_file(".env")

        def pick(key: str):
            return env.get(key) or os.getenv(key)

        bot_token = pick("BOT_TOKEN")
        if bot_token:
            config["bot_token"] = bot_token

        api_id = pick("API_ID")
        if api_id:
            config["api_id"] = int(api_id)

        api_hash = pick("API_HASH")
        if api_hash:
            config["api_hash"] = api_hash

        admin_ids = pick("ADMIN_IDS")
        if admin_ids:
            config["admin_ids"] = [int(x.strip()) for x in admin_ids.split(",") if x.strip()]

        target_channel = pick("TARGET_CHANNEL")
        if target_channel:
            config["target_channel"] = target_channel

        report_chat_id = pick("REPORT_CHAT_ID")
        if report_chat_id:
            try:
                config["report_chat_id"] = int(report_chat_id)
            except ValueError as exc:
                raise ValueError(
                    "REPORT_CHAT_ID в .env должен быть числом, например -1001234567890. "
                    f"Сейчас указано: {report_chat_id!r}"
                ) from exc

        post_limit = pick("POST_LIMIT")
        if post_limit:
            config["post_limit"] = int(post_limit)

        schedule_time = pick("SCHEDULE_TIME")
        if schedule_time:
            config["schedule_time"] = schedule_time

        session_name = pick("SESSION_NAME")
        if session_name:
            config["session_name"] = session_name

        active_collection = pick("ACTIVE_COLLECTION")
        if active_collection:
            config["active_collection"] = active_collection

        collections_path = pick("COLLECTIONS_PATH")
        if collections_path:
            config["collections_path"] = collections_path

        collections_json = pick("COLLECTIONS_JSON")
        if collections_json:
            try:
                config["collections_json"] = json.loads(collections_json)
            except json.JSONDecodeError as exc:
                raise ValueError("COLLECTIONS_JSON в .env должен быть валидным JSON") from exc

    def _load_collections(self) -> dict:
        if self.config.get("collections_json"):
            return self.config["collections_json"]
        collections_path = self.config.get("collections_path", "collections.json")
        if not os.path.exists(collections_path):
            default_channels = self.config.get("source_channels", [])
            collections = {
                "collections": {
                    "default": default_channels
                },
                "active": "default"
            }
            with open(collections_path, "w", encoding="utf-8") as f:
                json.dump(collections, f, ensure_ascii=False, indent=2)
            return collections
        with open(collections_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_collections(self):
        collections_path = self.config.get("collections_path", "collections.json")
        with open(collections_path, "w", encoding="utf-8") as f:
            json.dump(self.collections, f, ensure_ascii=False, indent=2)

    def _migrate_if_needed(self):
        if os.path.exists("posted.json") and not os.path.exists("posted_default.json"):
            os.rename("posted.json", "posted_default.json")

    def get_active_collection_name(self) -> str:
        return self.config.get("active_collection") or self.collections.get("active", "default")

    def get_active_channels(self) -> List[str]:
        name = self.get_active_collection_name()
        return self.collections.get("collections", {}).get(name, [])

    def set_active_collection(self, name: str):
        if name not in self.collections.get("collections", {}):
            raise ValueError(f"Подборка '{name}' не существует")
        self.collections["active"] = name
        self.save_collections()

    def get_all_collections(self) -> Dict[str, List[str]]:
        return self.collections.get("collections", {})

    def add_collection(self, name: str, channels: List[str] = None):
        if channels is None:
            channels = []
        if name in self.collections.get("collections", {}):
            raise ValueError(f"Подборка '{name}' уже существует")
        self.collections["collections"][name] = channels
        self.save_collections()
        posted_path = f"posted_{name}.json"
        if not os.path.exists(posted_path):
            with open(posted_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def delete_collection(self, name: str):
        if name == "default":
            raise ValueError("Подборку 'default' нельзя удалить")
        if name not in self.collections.get("collections", {}):
            raise ValueError(f"Подборка '{name}' не существует")
        del self.collections["collections"][name]
        if self.collections.get("active") == name:
            self.collections["active"] = "default"
        self.save_collections()
        posted_path = f"posted_{name}.json"
        if os.path.exists(posted_path):
            os.remove(posted_path)

    def add_channel_to_collection(self, collection_name: str, channel: str):
        channel = channel.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        collections = self.collections.get("collections", {})
        if collection_name not in collections:
            raise ValueError(f"Подборка '{collection_name}' не существует")
        if channel not in collections[collection_name]:
            collections[collection_name].append(channel)
            self.save_collections()
            return True
        return False

    def remove_channel_from_collection(self, collection_name: str, channel: str):
        collections = self.collections.get("collections", {})
        if collection_name not in collections:
            raise ValueError(f"Подборка '{collection_name}' не существует")
        if channel in collections[collection_name]:
            collections[collection_name].remove(channel)
            self.save_collections()
            return True
        return False

    def _get_posted_path(self) -> str:
        name = self.get_active_collection_name()
        return f"posted_{name}.json"

    def _load_posted_history(self) -> List[Dict]:
        path = self._get_posted_path()
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_posted_history(self, history: List[Dict]):
        path = self._get_posted_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_posted_history(self) -> List[Dict]:
        return self._load_posted_history()

    def is_posted(self, channel_id: int, message_id: int) -> bool:
        history = self._load_posted_history()
        cutoff_date = datetime.now() - timedelta(days=30)
        filtered = []
        for h in history:
            try:
                post_date = datetime.fromisoformat(h["date"])
                if post_date.tzinfo is not None:
                    post_date = post_date.replace(tzinfo=None)
                if post_date > cutoff_date:
                    filtered.append(h)
            except (ValueError, KeyError):
                continue
        if len(filtered) != len(history):
            self._save_posted_history(filtered)
        return any(
            h.get("channel_id") == channel_id and h.get("message_id") == message_id
            for h in filtered
        )

    def add_posted(self, channel_id: int, message_id: int, channel_title: str):
        history = self._load_posted_history()
        history.append(
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "channel_title": channel_title,
                "date": datetime.now().isoformat(),
            }
        )
        self._save_posted_history(history)

    def get_setting(self, key: str, default=None):
        return self.config.get(key, default)

    def set_setting(self, key: str, value: Any):
        self.config[key] = value
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_source_channels(self) -> List[str]:
        return self.get_active_channels()
