"""Abstract base class for all plugins."""

from abc import ABC, abstractmethod
from fastapi import APIRouter


class PluginBase(ABC):
    def __init__(self):
        self.router = APIRouter()
        self._register_routes()

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name — used as route prefix: /api/{name}/..."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this plugin."""

    @abstractmethod
    def _register_routes(self):
        """Register FastAPI routes on self.router."""

    def get_mcp_tools(self) -> list:
        """Return MCP tool definitions (optional)."""
        return []
