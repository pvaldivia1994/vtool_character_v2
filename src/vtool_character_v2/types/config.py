"""
ConfigSchema mínima para el Character System.

Contiene solo los campos que CharacterCompiler y CharacterManager
necesitan para compilar system prompts. El resto de la configuración
(debug, rutas de modelos, etc.) vive en vtool_llama_v2.config.ConfigSchema.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfigSchema:
    """Configuración del Character System.

    Los campos que no se usan directamente desde character/compiler
    se omiten intencionalmente. Para configuración completa del
    runtime LLM, usar vtool_llama_v2.config.ConfigSchema.
    """
    system_prompt: str = "Eres un asistente útil y natural."
    compact_system_prompt: bool = False
    system_prompt_target_tokens: int = 800
    system_prompt_max_tokens: int = 1200
    inject_dynamic_state: bool = False
