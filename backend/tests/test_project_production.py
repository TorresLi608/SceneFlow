from __future__ import annotations

from fastapi import HTTPException

from app.services.generation_service import build_image_prompt
from app.services.project_service import production_settings


def test_production_settings_defaults_and_updates() -> None:
    defaults = production_settings({}, defaults=True)
    assert defaults["mode"] == "comic"
    assert defaults["aspect_ratio"] == "9:16"
    assert defaults["width"] == 1080
    assert defaults["height"] == 1920
    assert defaults["fps"] == 24
    landscape = production_settings({"aspectRatio": "16:9"}, defaults=True)
    assert (landscape["width"], landscape["height"]) == (1920, 1080)

    updates = production_settings({"mode": "drama", "fps": 30, "targetDurationMs": 90000, "stylePrompt": "cinematic"})
    assert updates == {
        "mode": "drama",
        "fps": 30,
        "target_duration_ms": 90000,
        "style_prompt": "cinematic",
    }


def test_production_settings_reject_invalid_input() -> None:
    for payload, defaults in (
        ({"mode": "other"}, False),
        ({"fps": 25}, False),
        ({"width": "wide"}, False),
        ({"targetDurationMs": 1000}, False),
        ({"aspectRatio": "9:16", "width": 1920, "height": 1080}, True),
    ):
        try:
            production_settings(payload, defaults=defaults)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"expected invalid settings to fail: {payload}")


def test_the_projects_house_style_actually_reaches_the_image_prompt() -> None:
    """These two columns were stored, edited, and serialized for a while without ever being
    read by the renderer, which is the one place they exist to affect."""
    prompt = build_image_prompt(
        {
            "narration": "少年抬头望向石阶",
            "visual_prompt": "low angle, stone steps",
            "style_prompt": "水墨风格",
            "negative_prompt": "text, watermark",
        }
    )

    assert "水墨风格" in prompt
    assert "text, watermark" in prompt

    # A project that set neither must not grow empty trailing clauses.
    plain = build_image_prompt({"narration": "少年抬头望向石阶"})
    assert "Overall style" not in plain
    assert "Avoid" not in plain


if __name__ == "__main__":
    test_production_settings_defaults_and_updates()
    test_production_settings_reject_invalid_input()
    test_the_projects_house_style_actually_reaches_the_image_prompt()
