import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

class ConfigManager:
    def __init__(self, config_path: str = "config.json", history_path: str = "posted.json", queue_path: str = "queue.json"):
        self.config_path = config_path
        self.history_path = history_path
        self.queue_path = queue_path
        self.config = self._load_config()
        self.posted_history = self._load_history()
        self.queue = self._load_queue()
    
    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Создайте файл {self.config_path} по шаблону")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_history(self) -> List[Dict]:
        if not os.path.exists(self.history_path):
            return []
        with open(self.history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        cutoff_date = datetime.now() - timedelta(days=30)
        filtered = []
        for h in history:
            try:
                post_date = datetime.fromisoformat(h['date'])
                if post_date.tzinfo is not None:
                    post_date = post_date.replace(tzinfo=None)
                if post_date > cutoff_date:
                    filtered.append(h)
            except (ValueError, KeyError):
                continue
        return filtered
    
    def save_history(self):
        with open(self.history_path, 'w', encoding='utf-8') as f:
            json.dump(self.posted_history, f, ensure_ascii=False, indent=2)
    
    def save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def _load_queue(self) -> List[Dict]:
        if not os.path.exists(self.queue_path):
            return []
        with open(self.queue_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_queue(self):
        with open(self.queue_path, 'w', encoding='utf-8') as f:
            json.dump(self.queue, f, ensure_ascii=False, indent=2)
    
    def get_queue(self) -> List[Dict]:
        return self.queue
    
    def set_queue(self, items: List[Dict]):
        self.queue = items
        self.save_queue()
    
    def pop_queue(self) -> Dict:
        if not self.queue:
            return None
        item = self.queue.pop(0)
        self.save_queue()
        return item
    
    def get_setting(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set_setting(self, key: str, value: Any):
        self.config[key] = value
        self.save_config()
    
    def add_source_channel(self, channel: str):
        channel = channel.strip()
        if not channel.startswith('@'):
            channel = '@' + channel
        if channel not in self.config['source_channels']:
            if len(self.config['source_channels']) >= 10:
                raise ValueError("Максимум 10 каналов")
            self.config['source_channels'].append(channel)
            self.save_config()
            return True
        return False
    
    def remove_source_channel(self, channel: str):
        if channel in self.config['source_channels']:
            self.config['source_channels'].remove(channel)
            self.save_config()
            return True
        return False
    
    def is_posted(self, channel_id: int, message_id: int) -> bool:
        return any(
            h.get('channel_id') == channel_id and h.get('message_id') == message_id
            for h in self.posted_history
        )
    
    def add_posted(self, channel_id: int, message_id: int, channel_title: str):
        self.posted_history.append({
            'channel_id': channel_id,
            'message_id': message_id,
            'channel_title': channel_title,
            'date': datetime.now().isoformat()
        })
        self.save_history()