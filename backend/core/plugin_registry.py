"""Auto-discover and load plugins from backend/plugins/."""

import importlib
from pathlib import Path
from typing import Dict

from .plugin_base import PluginBase

_PRIORITY_PLUGINS = ["storage_plugin"]


def discover_plugins() -> Dict[str, PluginBase]:
    """Scan backend/plugins/ for PluginBase subclasses and instantiate them.

    Returns dict of {plugin_name: plugin_instance}.
    storage_plugin is always loaded first.
    """
    plugins_dir = Path(__file__).parent.parent / "plugins"
    if not plugins_dir.exists():
        return {}

    # Collect plugin module names
    module_names = []
    for f in sorted(plugins_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_names.append(f.stem)

    # Sort: priority plugins first, then alphabetical
    priority = [m for m in _PRIORITY_PLUGINS if m in module_names]
    rest = sorted([m for m in module_names if m not in _PRIORITY_PLUGINS])
    ordered = priority + rest

    plugins: Dict[str, PluginBase] = {}

    for module_name in ordered:
        module_path = f"backend.plugins.{module_name}"
        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            print(f"[plugin_registry] Failed to import {module_name}: {e}")
            continue

        # Find PluginBase subclass in module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
            ):
                try:
                    instance = attr()
                    plugins[instance.name] = instance
                    print(f"[plugin_registry] Loaded: {instance.name} — {instance.description}")
                except Exception as e:
                    print(f"[plugin_registry] Failed to instantiate {attr_name}: {e}")
                break  # One plugin class per module

    return plugins
