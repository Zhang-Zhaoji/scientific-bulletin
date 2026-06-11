"""
Central configuration for LLM provider selection.

Edit this file for day-to-day defaults. Command-line arguments in main.py can
still override PLATFORM and MODEL for one-off runs.
"""

PLATFORM = "DeepSeek"  # "DeepSeek" or "Aliyuncs"

DEFAULT_MODELS = {
    "DeepSeek": "deepseek-v4-flash",
    "Aliyuncs": "qwen3.7-plus",
}

BASE_URLS = {
    "DeepSeek": "https://api.deepseek.com",
    "Aliyuncs": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

API_KEY_ENV = {
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Aliyuncs": "DASHSCOPE_API_KEY",
}

BASE_URL_ENV = {
    "DeepSeek": "DEEPSEEK_API_URL",
    "Aliyuncs": "API_BASE_URL",
}

ENV_FILES = [
    ".env",
    f".env.{PLATFORM}",
]


def default_model(platform: str | None = None) -> str:
    platform = platform or PLATFORM
    try:
        return DEFAULT_MODELS[platform]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported LLM platform: {platform}") from exc


def supported_platforms() -> tuple[str, ...]:
    return tuple(DEFAULT_MODELS.keys())
