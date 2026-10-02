import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .extract import to_content_blocks
from .schema import Resume

load_dotenv()

PROVIDER = os.getenv("CV_PARSER_PROVIDER", "anthropic")  # anthropic | nvidia
MODELS = {"anthropic": "claude-sonnet-5-5", "nvidia": "google/gemma-4-31b-it"}
MODEL = os.getenv("CV_PARSER_MODEL", MODELS.get(PROVIDER, ""))
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
RULES = (
    "Rules: copy values faithfully, never invent information, use null for missing fields "
    "and [] for empty lists, keep the original language of the text, and order "
    "experience/education from most recent to oldest. Put only jobs and internships in experience; "
    "items from a projects section go in projects. Split skills into technical skills and soft skills, "
    "without duplicates."
)


def _anthropic(blocks: list[dict]) -> Resume:
    from anthropic import Anthropic

    tool = {
        "name": "save_resume",
        "description": "Save the structured data extracted from the resume.",
        "input_schema": Resume.model_json_schema(),
    }
    response = Anthropic().messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": blocks + [{"type": "text", "text": f"Extract the resume above into save_resume. {RULES}"}]}],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return Resume.model_validate(tool_use.input).normalize()


def _to_openai(block: dict) -> dict:
    if block["type"] == "image":
        src = block["source"]
        return {"type": "image_url", "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}}
    return block


def _nvidia(blocks: list[dict], attempts: int = 2) -> Resume:
    from openai import OpenAI

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=180)
    prompt = (
        f"Extract the resume above as a single JSON object matching this JSON schema. {RULES} "
        f"Respond with JSON only.\nSchema:\n{json.dumps(Resume.model_json_schema())}"
    )
    content = [_to_openai(b) for b in blocks] + [{"type": "text", "text": prompt}]
    last_error = None
    for _ in range(attempts):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=8000,
        )
        text = response.choices[0].message.content or ""
        try:
            return Resume.model_validate_json(text[text.find("{"): text.rfind("}") + 1]).normalize()
        except ValueError as e:
            last_error = e
    raise ValueError(f"Model did not return valid resume JSON: {last_error}")


def parse_resume(path: str | Path) -> Resume:
    blocks = to_content_blocks(path)
    if PROVIDER == "nvidia":
        return _nvidia(blocks)
    if PROVIDER == "anthropic":
        return _anthropic(blocks)
    raise ValueError(f"Unknown CV_PARSER_PROVIDER '{PROVIDER}' (use anthropic or nvidia)")
