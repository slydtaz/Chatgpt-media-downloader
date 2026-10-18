from pathlib import Path


def test_default_config_has_theme_and_baseline_api(tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "APP_DATA", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config" / "config.json")
    monkeypatch.setattr(cfg, "BASELINE_CONFIG_PATH", tmp_path / "config" / "installation_baseline.json")
    monkeypatch.setattr(cfg, "INSTALL_ID_PATH", tmp_path / "install_id.txt")
    monkeypatch.setattr(cfg, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(cfg, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(cfg, "TOOLS_DIR", tmp_path / "tools")

    data = cfg.load_config()
    assert data["theme"] == "system"
    cfg.save_installation_baseline(data)
    baseline = cfg.load_installation_baseline()
    assert baseline["auto_video_quality"] == 1080
    assert baseline["audio_bitrate"] == 192


def test_system_theme_returns_valid_value():
    from app.platform import detect_system_theme
    assert detect_system_theme() in {"light", "dark"}
