import os

from innieme.cli.run_unified_bot import (
    resolve_discord_config_path,
    DISCORD_CONFIG_NAME,
    LEGACY_DISCORD_CONFIG_NAME,
)


def _touch(path):
    with open(path, "w") as f:
        f.write("")


def test_prefers_discord_config_when_present(tmp_path):
    _touch(tmp_path / DISCORD_CONFIG_NAME)
    _touch(tmp_path / LEGACY_DISCORD_CONFIG_NAME)
    resolved = resolve_discord_config_path(str(tmp_path))
    assert resolved == os.path.join(str(tmp_path), DISCORD_CONFIG_NAME)


def test_falls_back_to_legacy_config(tmp_path, caplog):
    _touch(tmp_path / LEGACY_DISCORD_CONFIG_NAME)
    with caplog.at_level("WARNING"):
        resolved = resolve_discord_config_path(str(tmp_path))
    assert resolved == os.path.join(str(tmp_path), LEGACY_DISCORD_CONFIG_NAME)
    assert "deprecated" in caplog.text


def test_defaults_to_discord_config_when_neither_exists(tmp_path):
    resolved = resolve_discord_config_path(str(tmp_path))
    assert resolved == os.path.join(str(tmp_path), DISCORD_CONFIG_NAME)
