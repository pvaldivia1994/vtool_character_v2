"""Fixtures compartidos para tests de integración."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from dataclasses import asdict

import pytest

from vtool_character_v2 import CharacterManager
from vtool_character_v2.types import (
    IdentityDNA,
    PersonalityDNA,
    SpeechDNA,
    RulesDNA,
    RuntimeState,
    PersonalityState,
    RelationshipState,
)


@pytest.fixture
def temp_base_dir() -> Path:
    """Crea un directorio temporal para characters de test."""
    path = Path(tempfile.mkdtemp(prefix="vtool_char_test_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def cm(temp_base_dir: Path) -> CharacterManager:
    return CharacterManager(base_dir=str(temp_base_dir))


@pytest.fixture
def create_test_character(cm: CharacterManager, temp_base_dir: Path) -> str:
    """Crea un personaje mínimo de prueba y retorna su nombre."""
    name = "test_personaje"
    identity = {
        "name": name,
        "role": "tester",
        "age": "30",
        "background": "Un personaje de prueba.",
    }
    personality = {
        "traits": ["curioso", "analitico"],
        "flaws": ["perfeccionista"],
        "motivations": ["aprender"],
    }
    speech = {
        "style": "formal",
        "verbosity": "normal",
        "tone": "neutral",
    }
    rules = {
        "core_rules": ["Siempre decir la verdad"],
    }
    cm.create_character(name, identity, personality, speech, rules)
    return name


@pytest.fixture
def loaded_cm(cm: CharacterManager, create_test_character: str) -> CharacterManager:
    """Fixture que carga un personaje y retorna el manager."""
    cm.load_character(create_test_character)
    return cm
