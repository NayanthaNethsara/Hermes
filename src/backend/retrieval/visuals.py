import json
from pathlib import Path
from typing import Any

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger("visuals")

MAX_INSCRIBED_TEXT_CHARS = 600
MAX_DESCRIPTION_CHARS = 900
MAX_ATTRIBUTE_CHARS = 1000

_catalog_cache: dict[str, Any] = {}
_catalog_mtime: float | None = None


def catalog_path() -> Path:
    return get_settings().extracted_assets_dir / "visual_catalog.json"


def load_visual_catalog() -> dict[str, Any]:
    global _catalog_cache, _catalog_mtime

    path = catalog_path()
    if not path.exists():
        return {}

    mtime = path.stat().st_mtime
    if _catalog_mtime == mtime:
        return _catalog_cache

    try:
        _catalog_cache = json.loads(path.read_text(encoding="utf-8"))
        _catalog_mtime = mtime
    except Exception as error:
        logger.warning("visual_catalog_load_failed", error=str(error))
        return {}

    return _catalog_cache


def lookup_visual(filename: str) -> dict[str, Any] | None:
    catalog = load_visual_catalog()
    clean_name = filename.split("/")[-1]
    if clean_name in catalog:
        return catalog[clean_name]
    for key, value in catalog.items():
        if clean_name in key or key in clean_name:
            return value
    return None


def asset_url(figure_path: str) -> str:
    return f"/assets/{figure_path.split('/')[-1]}"


def describe_available_figures(figure_paths: list[str]) -> str:
    if not figure_paths:
        return "No figures are available for this answer."

    entries: list[str] = []
    for index, figure_path in enumerate(figure_paths, start=1):
        url = asset_url(figure_path)
        details = lookup_visual(figure_path)
        lines = [f"[{index}] {url}"]

        if not details:
            lines.append("    No catalog description available for this figure.")
            entries.append("\n".join(lines))
            continue

        title = str(details.get("title", "")).strip()
        if title:
            lines.append(f"    Title: {title}")

        inscribed = str(details.get("extracted_text", "")).strip()
        if inscribed:
            lines.append(f"    Inscribed text: {inscribed[:MAX_INSCRIBED_TEXT_CHARS]}")

        description = str(details.get("visual_description", "")).strip()
        if description:
            lines.append(f"    Shows: {description[:MAX_DESCRIPTION_CHARS]}")

        attributes = details.get("attributes") or {}
        if isinstance(attributes, dict) and attributes:
            pairs: list[str] = []
            budget = MAX_ATTRIBUTE_CHARS
            for key, value in attributes.items():
                pair = f"{key}={value}"
                if len(pair) > budget:
                    break
                pairs.append(pair)
                budget -= len(pair) + 2
            if pairs:
                lines.append(f"    Recorded data: {'; '.join(pairs)}")

        entries.append("\n".join(lines))

    return "\n".join(entries)
