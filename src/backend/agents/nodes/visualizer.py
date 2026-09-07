from pathlib import Path
from typing import Any

from src.backend.agents.state.models import AgentState


async def resolve_visual_assets(state: AgentState) -> dict[str, Any]:
    figures = state.get("figures", [])
    resolved_urls: list[str] = []

    for figure_path_str in figures:
        path_obj = Path(figure_path_str)
        filename = path_obj.name
        asset_url = f"/assets/{filename}"
        if asset_url not in resolved_urls:
            resolved_urls.append(asset_url)

    return {
        "figure_urls": resolved_urls,
        "referenced_figures": resolved_urls,
    }
