import json
import re
import time
from functools import lru_cache

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.gemini_api_key)


def _parse(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def generate_json(prompt: str, temperature: float = 0.3, max_retries: int = 6) -> dict:
    """Gemini call that must return a JSON object. Backs off on 429/5xx and retries bad JSON."""
    bad_json = 0
    for attempt in range(max_retries):
        try:
            res = _client().models.generate_content(
                model=settings.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return _parse(res.text)
        except APIError as e:
            if e.code in (429, 500, 503) and attempt < max_retries - 1:
                time.sleep(min(5 * 2 ** attempt, 65))
                continue
            raise
        except json.JSONDecodeError:
            bad_json += 1
            if bad_json >= 3:
                raise
    raise RuntimeError("LLM did not return valid JSON")
