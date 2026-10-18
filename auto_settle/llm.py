import base64
import re

import requests

DEFAULT_HOST = "http://localhost:11434"


def chat(model: str, prompt: str, images: list | None = None, host: str = DEFAULT_HOST,
         as_json: bool = False, timeout: int = 180) -> str:
    """Single-turn call to a local Ollama server (small open models, no data leaves the machine)."""
    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = [base64.b64encode(i).decode() for i in images]
    body = {"model": model, "stream": False, "messages": [message], "options": {"temperature": 0}}
    if as_json:
        body["format"] = "json"
    try:
        r = requests.post(f"{host}/api/chat", json=body, timeout=timeout)
    except requests.ConnectionError as e:
        raise RuntimeError(f"Ollama is not running at {host}. Install it from ollama.com and start it.") from e
    if r.status_code == 404:
        raise RuntimeError(f"Model '{model}' is not installed. Run: ollama pull {model}")
    r.raise_for_status()
    return r.json()["message"]["content"]


def rephrase(model: str, text: str, allowed_amounts: set, host: str = DEFAULT_HOST) -> str:
    """Friendlier wording of a fixed reply. Falls back to the original if any amount changes."""
    prompt = (
        "Rewrite this insurance chat reply in a warm, concise tone (max 2 sentences). "
        "Keep every rupee amount exactly as written and add no new numbers or promises.\n\n" + text
    )
    try:
        out = chat(model, prompt, host=host, timeout=60).strip()
    except (requests.RequestException, RuntimeError):
        return text
    found = {m.replace(",", "") for m in re.findall(r"\d[\d,]*", out)}
    return out if found <= allowed_amounts else text
