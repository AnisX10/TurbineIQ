"""Environment-backed provider settings and documented model presets."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "cerebras": ("https://api.cerebras.ai/v1", "gpt-oss-120b"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-oss-120b"),
    "ollama": ("http://localhost:11434/v1", "gpt-oss:20b"),
    "openai": ("https://api.openai.com/v1", "gpt-5.5"),
    "custom": ("", ""),
}

_PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "openai": "OPENAI_API_KEY",
    "custom": "TURBINEIQ_CUSTOM_API_KEY",
}


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-5.5"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 30.0
    max_tokens: int = 1200
    max_tool_rounds: int = 3

    @classmethod
    def from_environment(cls) -> "LLMSettings":
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)
        except ImportError:
            pass

        provider = os.getenv("TURBINEIQ_LLM_PROVIDER", "openai").strip().lower()
        if provider not in PROVIDER_PRESETS:
            provider = "custom"
        preset_url, preset_model = PROVIDER_PRESETS[provider]
        provider_key = _PROVIDER_KEYS[provider]
        legacy_base = (
            os.getenv("TURBINEIQ_OPENAI_BASE_URL", "").strip() if provider == "openai" else ""
        )
        legacy_model = (
            os.getenv("TURBINEIQ_OPENAI_MODEL", "").strip() if provider == "openai" else ""
        )
        default_model = legacy_model or preset_model
        if provider == "openai" and not os.getenv("TURBINEIQ_LLM_PROVIDER"):
            default_model = legacy_model or "gpt-5.5"
        key = (
            os.getenv("TURBINEIQ_LLM_API_KEY", "").strip()
            or os.getenv(provider_key, "").strip()
            or (
                os.getenv("HF_TOKEN", "").strip()
                or os.getenv("HUGGINGFACEHUB_API_TOKEN", "").strip()
                if provider == "custom"
                else ""
            )
            or (os.getenv("OPENAI_API_KEY", "").strip() if provider == "openai" else "")
        )
        if provider == "ollama" and not key:
            key = "ollama"
        try:
            timeout = max(1.0, min(float(os.getenv("TURBINEIQ_LLM_TIMEOUT_SECONDS", "30")), 180.0))
        except ValueError:
            timeout = 30.0
        try:
            max_tokens = max(64, min(int(os.getenv("TURBINEIQ_LLM_MAX_TOKENS", "1200")), 8192))
        except ValueError:
            max_tokens = 1200
        try:
            max_rounds = max(1, min(int(os.getenv("TURBINEIQ_LLM_MAX_TOOL_ROUNDS", "3")), 3))
        except ValueError:
            max_rounds = 3
        return cls(
            provider=provider,
            api_key=key,
            model=os.getenv("TURBINEIQ_LLM_MODEL", "").strip() or default_model,
            base_url=(
                os.getenv("TURBINEIQ_LLM_BASE_URL", "").strip()
                or (legacy_base if provider == "openai" else "")
                or preset_url
            ),
            timeout_seconds=timeout,
            max_tokens=max_tokens,
            max_tool_rounds=max_rounds,
        )

    @property
    def configured(self) -> bool:
        if self.provider == "ollama":
            return bool(self.base_url)
        if self.provider == "custom":
            return bool(self.base_url and self.model)
        return bool(self.api_key)
