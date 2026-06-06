"""persistence.py — Carga y guardado de DNA, Memory, State y Mods."""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from .base import CharacterManager
from ..types import (
    CharacterMod,
    IdentityDNA,
    MemoryEntry,
    PersonalityDNA,
    PersonalityState,
    RelationshipState,
    RuntimeState,
    SpeechDNA,
    RulesDNA,
)


def _load_dna(self: CharacterManager) -> None:
    if not self._char_dir:
        return
    dna_dir = self._char_dir / "dna"

    self.identity = IdentityDNA(**self._read_json(dna_dir / "identity.json", IdentityDNA))
    self.personality_dna = PersonalityDNA(**self._read_json(dna_dir / "personality.json", PersonalityDNA))
    self.speech = SpeechDNA(**self._read_json(dna_dir / "speech.json", SpeechDNA))
    self.rules = RulesDNA(**self._read_json(dna_dir / "rules.json", RulesDNA))

CharacterManager._load_dna = _load_dna


def _load_memory(self: CharacterManager) -> None:
    if not self._char_dir:
        return
    mem_file = self._char_dir / "_memory" / "long_term.json"
    data = self._read_json_dict(mem_file)

    self._needs_rebuild = data.get("rebuild", True)

    raw_mems = data.get("memories", [])
    self.memories = [
        MemoryEntry(**{k: v for k, v in m.items() if k in MemoryEntry.__dataclass_fields__})
        for m in raw_mems
    ]

CharacterManager._load_memory = _load_memory


def _load_state(self: CharacterManager) -> None:
    if not self._char_dir:
        return
    state_dir = self._char_dir / "state"

    meta = self._read_json_dict(state_dir / "state_meta.json")
    self._cached_prompt_hash = meta.get("prompt_hash", "")

    rs = self._read_json(state_dir / "runtime_state.json", RuntimeState)
    self.runtime_state = RuntimeState(**rs)

    ps = self._read_json(state_dir / "personality_state.json", PersonalityState)
    self.personality_state = PersonalityState(**ps)

    rels = self._read_json(state_dir / "relationship_state.json", RelationshipState)
    self.relationship_state = RelationshipState(**rels)

CharacterManager._load_state = _load_state


def _load_mods(self: CharacterManager) -> None:
    if not self._char_dir:
        return
    mods_file = self._char_dir / "mods" / "active_mods.json"
    data = self._read_json_dict(mods_file)

    self.active_mods = {}
    for k, v in data.items():
        self.active_mods[k] = CharacterMod(**{
            key: val for key, val in v.items() if key in CharacterMod.__dataclass_fields__
        })

CharacterManager._load_mods = _load_mods


def save_state(self: CharacterManager) -> None:
    if not self._char_dir:
        return
    with self._lock:
        mem_data = {
            "rebuild": self._needs_rebuild,
            "memories": [asdict(m) for m in self.memories],
        }
        self._write_json(self._char_dir / "_memory" / "long_term.json", mem_data)

        meta_data = {"prompt_hash": self._cached_prompt_hash}
        self._write_json(self._char_dir / "state" / "state_meta.json", meta_data)

        self._write_json(self._char_dir / "state" / "runtime_state.json", asdict(self.runtime_state))
        self._write_json(self._char_dir / "state" / "personality_state.json", asdict(self.personality_state))
        self._write_json(self._char_dir / "state" / "relationship_state.json", asdict(self.relationship_state))

        mods_data = {k: asdict(v) for k, v in self.active_mods.items()}
        self._write_json(self._char_dir / "mods" / "active_mods.json", mods_data)

CharacterManager.save_state = save_state


def mark_rebuild_done(self: CharacterManager, prompt: str) -> None:
    with self._lock:
        import hashlib
        self._cached_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self._needs_rebuild = False
        self.save_state()
        self._log("CHAR", f"KV Cache sincronizado. Hash: {self._cached_prompt_hash[:8]}")

CharacterManager.mark_rebuild_done = mark_rebuild_done


def add_memory(
    self: CharacterManager,
    content: str,
    priority: float = 0.5,
    always_include: bool = False,
    tags: Optional[list[str]] = None,
) -> MemoryEntry:
    with self._lock:
        entry = MemoryEntry(content=content, priority=priority, always_include=always_include, tags=tags or [])
        self.memories.append(entry)
        self._needs_rebuild = True
        self._prompt_dirty = True
        self.save_state()
        self._log("CHAR", f"Memoria añadida: '{content[:50]}...'")
        return entry

CharacterManager.add_memory = add_memory


def set_mod(self: CharacterManager, mod: CharacterMod) -> None:
    with self._lock:
        self.active_mods[mod.id] = mod
        self._prompt_dirty = True
        self.save_state()
        self._log("CHAR", f"Mod aplicado: {mod.id}")

CharacterManager.set_mod = set_mod


def remove_mod(self: CharacterManager, mod_id: str) -> None:
    with self._lock:
        if mod_id in self.active_mods:
            del self.active_mods[mod_id]
            self._prompt_dirty = True
            self.save_state()

CharacterManager.remove_mod = remove_mod
