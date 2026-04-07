"""Thread-safe TTL cache with named namespaces."""

import threading
import time
from typing import Any, Optional


class CacheNamespace:
    def __init__(self, ttl: int = 300):
        self._data: dict = {}
        self._expiry: dict = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._data:
                if time.time() < self._expiry[key]:
                    return self._data[key]
                else:
                    del self._data[key]
                    del self._expiry[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        with self._lock:
            self._data[key] = value
            self._expiry[key] = time.time() + (ttl if ttl is not None else self._ttl)

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()
            self._expiry.clear()


class Cache:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._namespaces = {}
                    cls._instance._ns_lock = threading.Lock()
        return cls._instance

    def namespace(self, name: str, ttl: int = 300) -> CacheNamespace:
        with self._ns_lock:
            if name not in self._namespaces:
                self._namespaces[name] = CacheNamespace(ttl=ttl)
            return self._namespaces[name]

    def clear_all(self):
        with self._ns_lock:
            for ns in self._namespaces.values():
                ns.clear()


cache = Cache()
