from __future__ import annotations

from fastapi import HTTPException

from app.services.project_service import production_settings


def test_production_settings_defaults_and_updates() -> None:
    defaults = production_settings({}, defaults=True)
    assert defaults["mode"] == "comic"
    assert defaults["aspect_ratio"] == "9:16"
    assert defaults["width"] == 1080
    assert defaults["height"] == 1920
    assert defaults["fps"] == 24

    updates = production_settings({"mode": "drama", "fps": 30, "targetDurationMs": 90000, "stylePrompt": "cinematic"})
    assert updates == {
        "mode": "drama",
        "fps": 30,
        "target_duration_ms": 90000,
        "style_prompt": "cinematic",
    }


def test_production_settings_reject_invalid_input() -> None:
    for payload in ({"mode": "other"}, {"fps": 25}, {"width": "wide"}, {"targetDurationMs": 1000}):
        try:
            production_settings(payload)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"expected invalid settings to fail: {payload}")


if __name__ == "__main__":
    test_production_settings_defaults_and_updates()
    test_production_settings_reject_invalid_input()
