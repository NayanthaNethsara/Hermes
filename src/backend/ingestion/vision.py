import base64
import json
from pathlib import Path
import time
from typing import Any

import google.auth
from google.auth.transport.requests import Request
import requests
from pydantic import BaseModel, Field

from src.backend.core.config import get_settings
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


class VisionAnalysisResult(BaseModel):
    title: str = Field(description="Title or subject of the visual plate or illustration")
    extracted_text: str = Field(default="", description="Verbatim text, numbers, gauges, or labels")
    visual_description: str = Field(description="Detailed visual scene description including objects, attire, and symbols")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Extracted key-value facts like ratings or counts")
    rich_content: str = Field(description="Complete Markdown content combining all visual intelligence for search")


class VisionAnalyzer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.project_id = self.settings.gcp_project_id
        self.location = self.settings.gcp_location or "global"
        self.model_name = self.settings.gemini_model or "gemini-2.5-flash"
        self._credentials = None

    def _get_auth_token(self) -> str:
        if not self._credentials:
            self._credentials, _ = google.auth.default()
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token

    def analyze_image(self, image_path: Path) -> VisionAnalysisResult:
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        token = self._get_auth_token()
        with open(image_path, "rb") as image_file:
            base64_encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

        suffix = image_path.suffix.lower().replace(".", "")
        mime_type = "image/jpeg" if suffix in ["jpg", "jpeg"] else "image/png"

        prompt = (
            "Analyze this archival image with extreme precision.\n"
            "Identify whether it is a technical/diagrammatic plate (e.g. threat gauge, garrison count, attunement chart) "
            "or an illustrated artwork (e.g. portrait, heraldic banner, relic, battle painting).\n\n"
            "Extract:\n"
            "1. Specific title or name of the subject (character name, relic name, creature name, or location name).\n"
            "2. All text, numbers, gauge readings, attunement costs, or garrison numbers verbatim.\n"
            "3. Thorough visual details: attire, crowns/headwear, held items, weapons, heraldic emblems, engraved motifs, colors, physical traits, and background elements.\n"
            "4. Structured key-value attributes (e.g. threat_rating, scale, garrison_total, attunement_cost, held_object, central_emblem).\n\n"
            "Output JSON with this exact schema:\n"
            "{\n"
            '  "title": "string (specific name of the subject or document)",\n'
            '  "extracted_text": "string (all words/numbers on image)",\n'
            '  "visual_description": "string (dense descriptive paragraph)",\n'
            '  "attributes": {"key": "value"}\n'
            "}"
        )

        api_endpoint = (
            f"https://aiplatform.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.location}/publishers/google/models/{self.model_name}:generateContent"
        )

        request_payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": base64_encoded_image}}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            }
        }

        max_attempts = 5
        base_delay = 8.0

        for attempt in range(1, max_attempts + 1):
            token = self._get_auth_token()
            try:
                response = requests.post(
                    api_endpoint,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json=request_payload,
                    timeout=90,
                )
            except requests.exceptions.Timeout:
                sleep_seconds = base_delay * attempt
                logger.warning(
                    "vertex_ai_request_timeout_retrying",
                    file=image_path.name,
                    attempt=attempt,
                    retry_in_seconds=round(sleep_seconds, 1),
                )
                time.sleep(sleep_seconds)
                continue
            except requests.exceptions.RequestException as network_error:
                sleep_seconds = base_delay * attempt
                logger.warning(
                    "vertex_ai_network_error_retrying",
                    file=image_path.name,
                    attempt=attempt,
                    error=str(network_error),
                    retry_in_seconds=round(sleep_seconds, 1),
                )
                time.sleep(sleep_seconds)
                continue

            if response.status_code == 200:
                break

            if response.status_code in [429, 503]:
                sleep_seconds = base_delay * (attempt * 1.5)
                logger.warning(
                    "vertex_ai_rate_limit_pausing",
                    file=image_path.name,
                    attempt=attempt,
                    status=response.status_code,
                    retry_in_seconds=round(sleep_seconds, 1),
                )
                time.sleep(sleep_seconds)
                continue

            logger.error("vision_analysis_api_failed", status=response.status_code, body=response.text[:200])
            raise RuntimeError(f"Vertex AI Vision call failed ({response.status_code}): {response.text[:200]}")
        else:
            raise RuntimeError(f"Vertex AI Vision call failed after {max_attempts} attempts due to rate limits or timeouts.")

        response_json = response.json()
        raw_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
        parsed_data = json.loads(raw_text)

        title = parsed_data.get("title", image_path.stem.replace("_", " ").title())
        extracted_text = parsed_data.get("extracted_text", "")
        visual_description = parsed_data.get("visual_description", "")
        attributes = parsed_data.get("attributes", {})

        attributes_markdown = "\n".join([f"- **{key.replace('_', ' ').title()}**: {val}" for key, val in attributes.items()])

        rich_content = (
            f"# Visual Asset: {title}\n\n"
            f"**File**: {image_path.name}\n"
            f"**Asset Path**: /assets/{image_path.name}\n\n"
            f"### Extracted Text & Data\n"
            f"{extracted_text if extracted_text else 'No inscribed text detected.'}\n\n"
            f"### Visual Scene Analysis\n"
            f"{visual_description}\n\n"
            f"### Key Attributes\n"
            f"{attributes_markdown if attributes_markdown else 'None recorded.'}"
        )

        return VisionAnalysisResult(
            title=title,
            extracted_text=extracted_text,
            visual_description=visual_description,
            attributes=attributes,
            rich_content=rich_content,
        )
