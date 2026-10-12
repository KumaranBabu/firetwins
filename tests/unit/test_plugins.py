"""Unit tests — pyfds.plugins (base protocols + loader/registry)."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest
from pyfds.plugins.base import PluginBase, PluginMetadata
from pyfds.plugins.loader import PluginRegistry, PluginLoader, get_registry


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------

class TestPluginMetadata:
    def test_basic_creation(self):
        m = PluginMetadata(name="test_plugin", version="1.0", author="Dev", description="A test")
        assert m.name == "test_plugin"
        assert m.version == "1.0"

    def test_tags_default_empty(self):
        m = PluginMetadata(name="p", version="0.1", author="A", description="D")
        assert m.tags == []

    def test_requires_default_empty(self):
        m = PluginMetadata(name="p", version="0.1", author="A", description="D")
        assert m.requires == []


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------

class _SimplePlugin(PluginBase):
    """A minimal plugin for testing."""
    def __init__(self, name="simple_plugin"):
        self.metadata = PluginMetadata(
            name=name, version="0.1", author="Test", description="Simple test plugin"
        )


class TestPluginRegistry:
    def setup_method(self):
        self.registry = PluginRegistry()

    def test_register_plugin(self):
        plugin = _SimplePlugin()
        self.registry.register(plugin)
        assert "simple_plugin" in [p.metadata.name for p in self.registry.all_plugins()]

    def test_all_plugins_returns_all(self):
        self.registry.register(_SimplePlugin("p1"))
        self.registry.register(_SimplePlugin("p2"))
        names = [p.metadata.name for p in self.registry.all_plugins()]
        assert "p1" in names
        assert "p2" in names

    def test_get_by_name(self):
        self.registry.register(_SimplePlugin("alpha"))
        plugin = self.registry.get("alpha")
        assert plugin is not None
        assert plugin.metadata.name == "alpha"

    def test_get_nonexistent_returns_none(self):
        assert self.registry.get("nonexistent") is None

    def test_unregister_plugin(self):
        self.registry.register(_SimplePlugin("to_remove"))
        self.registry.unregister("to_remove")
        assert self.registry.get("to_remove") is None

    def test_register_duplicate_overwrites(self):
        """Registering with same name should replace the existing entry."""
        self.registry.register(_SimplePlugin("dup"))
        self.registry.register(_SimplePlugin("dup"))
        plugins = [p for p in self.registry.all_plugins() if p.metadata.name == "dup"]
        assert len(plugins) == 1

    def test_emits_plugin_loaded_event(self):
        from pyfds.core.events import EventType, get_global_bus
        received = []
        get_global_bus().subscribe(EventType.PLUGIN_LOADED, received.append)
        self.registry.register(_SimplePlugin("evt_plugin"))
        assert len(received) == 1

    def test_emits_plugin_unloaded_event(self):
        from pyfds.core.events import EventType, get_global_bus
        received = []
        self.registry.register(_SimplePlugin("unload_plugin"))
        get_global_bus().subscribe(EventType.PLUGIN_UNLOADED, received.append)
        self.registry.unregister("unload_plugin")
        assert len(received) == 1

    def test_get_by_type_writer_plugin(self):
        from pyfds.plugins.base import WriterPlugin
        # No writer plugins registered → empty list
        writers = self.registry.get_by_type(WriterPlugin)
        assert isinstance(writers, list)


# ---------------------------------------------------------------------------
# PluginLoader
# ---------------------------------------------------------------------------

class TestPluginLoader:
    def test_load_directory_with_valid_plugin(self, tmp_path):
        """A .py file with PYFDS_PLUGIN=True and register() should be loaded."""
        plugin_code = textwrap.dedent("""
            PYFDS_PLUGIN = True

            class MyPlugin:
                class metadata:
                    name = "loaded_plugin"
                    version = "0.1"
                    author = "Test"
                    description = "Auto-loaded"
                    tags = []
                    requires = []

            def register(registry):
                registry.register(MyPlugin())
        """)
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(plugin_code)

        registry = PluginRegistry()
        loader = PluginLoader(registry)
        loader.load_directory(tmp_path)
        assert registry.get("loaded_plugin") is not None

    def test_load_directory_ignores_non_plugin_files(self, tmp_path):
        """A .py file without PYFDS_PLUGIN should be silently ignored."""
        (tmp_path / "not_a_plugin.py").write_text("x = 1\n")
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        loader.load_directory(tmp_path)
        assert len(registry.all_plugins()) == 0

    def test_load_directory_recursive(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        plugin_code = textwrap.dedent("""
            PYFDS_PLUGIN = True

            class SubPlugin:
                class metadata:
                    name = "sub_plugin"
                    version = "0.1"
                    author = "T"
                    description = "Sub"
                    tags = []
                    requires = []

            def register(registry):
                registry.register(SubPlugin())
        """)
        (subdir / "sub_plugin.py").write_text(plugin_code)
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        loader.load_directory(tmp_path, recursive=True)
        assert registry.get("sub_plugin") is not None

    def test_load_directory_bad_plugin_does_not_crash(self, tmp_path):
        """A plugin file that raises on import should be swallowed gracefully."""
        (tmp_path / "bad_plugin.py").write_text(
            "PYFDS_PLUGIN = True\nraise RuntimeError('intentional crash')\n"
        )
        registry = PluginRegistry()
        loader = PluginLoader(registry)
        loader.load_directory(tmp_path)  # should not raise
        assert len(registry.all_plugins()) == 0


# ---------------------------------------------------------------------------
# get_registry() singleton
# ---------------------------------------------------------------------------

class TestGetRegistry:
    def test_returns_same_instance(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_is_plugin_registry(self):
        assert isinstance(get_registry(), PluginRegistry)
