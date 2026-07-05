import json
import os
import threading
import time
from uuid import uuid4


class SessionStore:
    def __init__(self, ttl_seconds, persist_path="sessions.json"):
        self.ttl_seconds = ttl_seconds
        self.persist_path = persist_path
        self.items = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    self.items = json.load(f)
            except Exception:
                self.items = {}

    def save(self):
        try:
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False)
        except Exception:
            pass

    def create(self, data):
        session_id = str(uuid4())
        now = time.time()
        with self.lock:
            self.items[session_id] = {"created_at": now, "last_seen": now, **data}
            self.save()
        return session_id

    def get(self, session_id):
        with self.lock:
            item = self.items.get(session_id)
            if not item:
                raise KeyError("Session expired or not found")
            item["last_seen"] = time.time()
            self.save()
            return item

    def update(self, session_id, **values):
        with self.lock:
            item = self.items.get(session_id)
            if not item:
                raise KeyError("Session expired or not found")
            item.update(values)
            item["last_seen"] = time.time()
            self.save()

    def delete(self, session_id):
        with self.lock:
            self.items.pop(session_id, None)
            self.save()

    def list_all(self):
        with self.lock:
            history = []
            for sid, item in self.items.items():
                if item.get("status") == "ready" and "video_meta" in item:
                    history.append({
                        "id": sid,
                        "created_at": item.get("created_at", 0),
                        "video_meta": item.get("video_meta", {}),
                    })
            history.sort(key=lambda x: x["created_at"], reverse=True)
            return history
