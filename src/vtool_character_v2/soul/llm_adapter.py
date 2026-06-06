"""llm_adapter.py — Adaptador oficial entre VToolLlamaV2 y LLMClient protocol."""

from __future__ import annotations

from typing import Any, Optional


class VToolLlamaAdapter:
    """Adaptador que envuelve VToolLlamaV2 para cumplir el protocolo LLMClient.

    Uso:
        from vtool_llama_v2 import VToolLlamaV2
        from vtool_character_v2.soul import VToolLlamaAdapter

        llm = VToolLlamaV2()
        adapter = VToolLlamaAdapter(llm)
        soul = SoulGenerator(cm, llm.get_config(), llm_client=adapter)
    """

    def __init__(self, llm_client: Any):
        self._llm = llm_client

    @property
    def is_loaded(self) -> bool:
        mm = getattr(self._llm, '_default_model_manager', None)
        return mm is not None and mm.is_loaded

    def generate(self, messages: list[dict], **kwargs) -> dict:
        """Implementa el contrato LLMClient.generate() sobre generate_raw().

        Returns:
            dict con formato {"choices": [{"message": {"content": str}}]}
        """
        result = self._llm.generate_raw(messages=messages, **kwargs)

        # Si generate_raw devolvió un generador (streaming), consumirlo
        if hasattr(result, '__next__'):
            full_content = ""
            for chunk in result:
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {}) if "delta" in choice else choice.get("message", {})
                full_content += delta.get("content", "")
            return {"choices": [{"message": {"content": full_content}}]}

        # Ya viene en formato OpenAI (no-streaming)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)
