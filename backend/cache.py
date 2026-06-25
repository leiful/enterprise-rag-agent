import hashlib
import threading


class ResponseCache:
    def __init__(self, maxsize=256):
        self._cache = {}
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def make_key(self, user_input, departments, knowledge_version):
        deps = tuple(sorted(departments or []))
        raw = f"{user_input}|{deps}|{knowledge_version}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get(self, key):
        with self._lock:
            return self._cache.get(key)

    def set(self, key, value):
        with self._lock:
            if len(self._cache) >= self._maxsize:
                self._cache.pop(next(iter(self._cache)), None)
            self._cache[key] = value


response_cache = ResponseCache()
