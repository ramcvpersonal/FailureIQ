"""
llm_client.py — LLM Provider Abstraction
-----------------------------------------
Priority:
  1. Ollama (free, local) → IBM Granite → Llama 3.1 → Mistral
  2. OpenAI (paid fallback) → GPT-4o

INTERVIEW TALKING POINT:
  Provider-agnostic design — agent logic never changes regardless
  of which LLM is underneath. Ollama exposes an OpenAI-compatible
  REST API so we reuse the same openai SDK for both, just pointing
  at localhost:11434 instead of api.openai.com.
"""

import os
import requests
from typing import Optional, Generator
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Preferred Ollama models in order (first installed one wins)
OLLAMA_MODELS = [
    "granite3.1-dense",    # IBM Granite — best for IBM interviews! (pull if needed)
    "granite3-dense",      # IBM Granite 3 alternative tag
    "deepseek-r1:8b",      # DeepSeek R1 8B — strong reasoning ✅ installed
    "qwen3:8b",            # Qwen3 8B — strong coder/analyst ✅ installed
    "llama3.1:8b",         # Meta Llama 3.1 8B ✅ installed
    "llama3:latest",       # Meta Llama 3 ✅ installed
    "qwen2.5-coder:7b",    # Qwen 2.5 Coder ✅ installed
    "mistral",             # Mistral 7B
]

OLLAMA_BASE_URL = "http://localhost:11434/v1"


class LLMClient:
    """
    Single client that auto-detects Ollama (free) or falls back to OpenAI.
    Use LLMClient.create() to initialize.
    """

    def __init__(self, client: OpenAI, provider: str, model: str):
        self._client = client
        self.provider = provider
        self.model = model

    @classmethod
    def create(cls) -> "LLMClient":
        """Auto-detect best available LLM provider."""
        # Try Ollama first (free, local)
        model = cls._detect_ollama_model()
        if model:
            client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
            print(f"✅ Using Ollama (local) → model: {model}")
            return cls(client, "ollama", model)

        # Fallback to OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            print(f"✅ Using OpenAI → model: {model}")
            return cls(client, "openai", model)

        raise RuntimeError(
            "\n❌ No LLM provider available!\n\n"
            "Option 1 — Free (recommended):\n"
            "  brew install ollama\n"
            "  ollama serve\n"
            "  ollama pull granite3.1-dense\n\n"
            "Option 2 — Paid:\n"
            "  Copy .env.example to .env and set OPENAI_API_KEY\n"
        )

    @staticmethod
    def _detect_ollama_model() -> Optional[str]:
        """Probe Ollama for installed models, return first preferred match."""
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/models", timeout=2)
            if not resp.ok:
                return None
            installed = [m["id"] for m in resp.json().get("data", [])]
            for preferred in OLLAMA_MODELS:
                if any(i.startswith(preferred) for i in installed):
                    return preferred
            # Use whatever is installed if nothing preferred
            return installed[0] if installed else None
        except Exception:
            return None  # Ollama not running

    def complete(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048) -> str:
        """
        Standard (non-streaming) completion.
        Returns full response as a string.
        Used for structured JSON output.
        """
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def stream(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048):
        """
        Streaming completion — yields tokens one by one.

        INTERVIEW TALKING POINT:
          Streaming uses chunked HTTP transfer encoding. The model sends
          each token as it generates it. We print immediately so the user
          sees the analysis appear word-by-word — exactly how ChatGPT works.
          This is key for perceived performance in AI applications.
        """
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
