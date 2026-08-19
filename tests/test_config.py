"""Cấu hình: hợp nhất khoan dung, lưu/nạp, preset. Không cần GPU."""
from __future__ import annotations

import json

import pytest

from aicampro.config import AppConfig, resolve_asset


def test_defaults_are_sane():
    cfg = AppConfig()
    assert cfg.capture.width > 0 and cfg.capture.height > 0
    assert cfg.background.mode in {"none", "blur", "image", "color",
                                   "greenscreen", "transparent"}
    assert 0.0 <= cfg.autoframe.smoothing < 1.0
    assert cfg.output.width == 0 and cfg.output.height == 0   # 0 = như nguồn


def test_merge_ignores_unknown_keys_and_coerces_types():
    cfg = AppConfig()
    cfg.apply_dict({
        "capture": {"width": "1920", "height": 1080, "khong_ton_tai": 1},
        "khong_ton_tai": {"a": 1},
        "background": {"color": [1, 2, 3]},
    })
    assert (cfg.capture.width, cfg.capture.height) == (1920, 1080)
    assert cfg.background.color == (1, 2, 3)      # list trong JSON -> tuple


def test_merge_skips_none_and_bad_values():
    cfg = AppConfig()
    before = (cfg.capture.fps, cfg.capture.fourcc)
    cfg.apply_dict({"capture": {"fps": None, "fourcc": {"khong": "phai chuoi"}}})
    assert (cfg.capture.fps, cfg.capture.fourcc) == before


def test_roundtrip(tmp_path):
    cfg = AppConfig()
    cfg.filters.saturation = 0.42
    cfg.background.mode = "greenscreen"
    path = cfg.save(tmp_path / "config.json")

    loaded = AppConfig.load(path)
    assert loaded.filters.saturation == pytest.approx(0.42)
    assert loaded.background.mode == "greenscreen"


def test_load_survives_corrupt_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ khong phai json")
    assert AppConfig.load(path).capture.width == AppConfig().capture.width


def test_load_survives_missing_file(tmp_path):
    assert AppConfig.load(tmp_path / "chua-ton-tai.json").capture.fps > 0


def test_saved_config_is_valid_json(tmp_path):
    cfg = AppConfig()
    data = json.loads(cfg.save(tmp_path / "c.json").read_text())
    assert set(data) == {"capture", "segmentation", "background", "filters",
                         "beauty", "autoframe", "output"}


def test_resolve_asset_finds_repo_relative_path():
    assert resolve_asset("assets/luts/01_warm_studio.cube") is not None
    assert resolve_asset("assets/khong/ton/tai.cube") is None
    assert resolve_asset("") is None
