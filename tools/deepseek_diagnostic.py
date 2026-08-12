"""One minimal DeepSeek response-shape diagnostic; never used for results."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key-file", type=Path, default=Path(r"C:\APP\project\deepseek_api_key.txt"))
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    args = parser.parse_args()
    key = args.api_key_file.read_text(encoding="utf-8").strip()
    payload = {"model": "deepseek-v4-flash", "messages": [{"role": "system", "content": "Return only JSON."}, {"role": "user", "content": "Reply with exactly {\"ok\":true}."}], "temperature": 0.0, "max_tokens": 128, "thinking": {"type": "disabled"}}
    request = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode())
    safe = {"id": data.get("id"), "model": data.get("model"), "usage": data.get("usage"), "choices": []}
    for choice in data.get("choices", []):
        message = choice.get("message") or {}
        safe["choices"].append({"finish_reason": choice.get("finish_reason"), "message_fields": sorted(message.keys()), "content": message.get("content"), "reasoning_content_chars": len(str(message.get("reasoning_content") or ""))})
    print(json.dumps(safe, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
