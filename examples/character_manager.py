"""
Interactive character manager: list, create, load, and chat with characters.

Run:  python examples/character_manager.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from vtool_character_v2 import CharacterManager


# ── helpers ──────────────────────────────────────────────────────────

def _fmt(text: str) -> str:
    """Safe print for Windows cp1252."""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _input(prompt: str, default: str = "") -> str:
    val = input(prompt).strip()
    return val if val else default


# ── list / pick ──────────────────────────────────────────────────────

def pick_or_create(cm: CharacterManager) -> str | None:
    """Show existing characters, let user pick one or create new."""
    chars = cm.list_characters()

    print("\n--- Existing characters ---")
    if not chars:
        print("  (none)")
    else:
        for i, c in enumerate(chars, 1):
            has = " [soul]" if c.get("has_soul") else ""
            print(f"  {i}. {c['name']} ({c.get('role', '?')}){has}")

    print("\n  n. Create a NEW character")
    print("  q. Quit")
    choice = input("\nPick: ").strip().lower()

    if choice == "q":
        return None
    if choice == "n":
        return create_new(cm)

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(chars):
            return chars[idx]["name"]
    except ValueError:
        pass

    print("  Invalid choice.")
    return pick_or_create(cm)


# ── create ────────────────────────────────────────────────────────────

def create_new(cm: CharacterManager) -> str | None:
    """Walk through character creation."""
    name = _input("Character name: ")
    if not name:
        print("  Name is required.")
        return create_new(cm)

    if (cm._base_dir / name).exists():
        print(f"  Character '{name}' already exists.")
        overwrite = input("  Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            return pick_or_create(cm)
        shutil.rmtree(str(cm._base_dir / name))

    print("\n  Create with LLM auto-generate, or manual input?")
    print("  1. Auto-generate with LLM (needs GGUF model)")
    print("  2. Manual input (defaults when left blank)")

    mode = _input("Pick [1/2]: ", "2")

    if mode == "1":
        return _create_with_llm(cm, name)
    return _create_manual(cm, name)


def _create_with_llm(cm: CharacterManager, name: str) -> str:
    """Auto-generate character DNA using vtool_llama_v2."""
    try:
        from vtool_llama_v2 import VToolLlamaV2
        from vtool_character_v2.soul import SoulGenerator, VToolLlamaAdapter
    except ImportError:
        print("  vtool_llama_v2 not installed. Falling back to manual mode.")
        return _create_manual(cm, name)

    try:
        llm = VToolLlamaV2(auto_load=True)
        llm.get_config()  # smoke test
    except Exception as e:
        print(f"  Could not load LLM: {e}")
        print("  Falling back to manual mode.")
        return _create_manual(cm, name)

    role = _input(f"  Role for {name}: ", "character")
    background = _input("  Background (one line): ", "A mysterious traveler.")

    # Build a prompt that asks the LLM to generate character DNA as JSON
    gen_prompt = f"""
Generate character DNA for a fictional character named "{name}".
Role: {role}
Background: {background}

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "identity": {{"name": "{name}", "role": "...", "age": "...", "background": "..."}},
  "personality": {{"traits": [...], "flaws": [...], "motivations": [...], "inner_conflict": "...", "emotional_triggers": [...]}},
  "speech": {{"style": "...", "verbosity": "normal", "tone": "...", "emotions": [...], "speech_patterns": [...]}},
  "rules": {{"core_rules": [...], "never_do": [...], "response_style": [...]}}
}}
"""

    adapter = VToolLlamaAdapter(llm)
    session = llm.create_session(session_id=f"gen_{name}")
    session.set_system_prompt("You are a creative writer. Output only valid JSON.")

    print(f"\n  Generating DNA for '{name}' with LLM...")
    resp = session.chat(gen_prompt)
    raw = resp.content.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  LLM returned invalid JSON. Raw output:\n{_fmt(raw[:500])}")
        print("  Falling back to manual mode.")
        return _create_manual(cm, name)

    cm.create_character(
        name=name,
        identity_data=data.get("identity", {}),
        personality_data=data.get("personality", {}),
        speech_data=data.get("speech", {}),
        rules_data=data.get("rules", {}),
    )
    print(f"  Character '{name}' created from LLM.\n")
    return name


def _create_manual(cm: CharacterManager, name: str) -> str:
    """Manual input with defaults on blank."""

    print("\n  --- Identity ---")
    identity = {
        "name": name,
        "role": _input(f"  Role [{name}]: ", name),
        "age": _input("  Age [Unknown]: ", "Unknown"),
        "background": _input("  Background [A mysterious figure.]: ", "A mysterious figure."),
    }

    print("\n  --- Personality ---")
    traits_str = _input("  Traits (comma-separated) [curious]: ", "curious")
    traits = [t.strip() for t in traits_str.split(",") if t.strip()]
    flaws_str = _input("  Flaws (comma-separated) [none]: ", "")
    flaws = [t.strip() for t in flaws_str.split(",") if t.strip()]
    mot_str = _input("  Motivations (comma-sep) [explore]: ", "explore")
    motivations = [t.strip() for t in mot_str.split(",") if t.strip()]

    personality = {
        "traits": traits or ["curious"],
        "flaws": flaws,
        "motivations": motivations or ["explore"],
        "inner_conflict": _input("  Inner conflict [none]: ", ""),
        "emotional_triggers": [],
    }

    print("\n  --- Speech ---")
    speech = {
        "style": _input("  Style [natural]: ", "natural"),
        "verbosity": _input("  Verbosity (low/normal/high) [normal]: ", "normal"),
        "tone": _input("  Tone [neutral]: ", "neutral"),
        "emotions": [],
        "speech_patterns": [],
    }

    print("\n  --- Rules ---")
    rules_str = _input("  Core rules (comma-sep) [Be yourself.]: ", "Be yourself.")
    core_rules = [t.strip() for t in rules_str.split(",") if t.strip()]

    rules = {
        "core_rules": core_rules or ["Be yourself."],
        "never_do": [],
        "response_style": [],
    }

    print("\n  --- Initial memories ---")
    mems = []
    for i in range(3):
        m = input(f"  Memory #{i + 1} (or blank to skip): ").strip()
        if m:
            mems.append(m)

    cm.create_character(
        name=name,
        identity_data=identity,
        personality_data=personality,
        speech_data=speech,
        rules_data=rules,
        initial_memories=mems or None,
    )
    print(f"\n  Character '{name}' created.\n")
    return name


# ── chat ──────────────────────────────────────────────────────────────

def chat_loop(cm: CharacterManager, name: str):
    """Interactive chat with a loaded character."""
    cm.load_character(name)

    print(f"\n  Loaded '{name}' — {cm.identity.role}")
    print(f"  Prompt: {len(cm.build_system_prompt(f'You are {name}.'))} chars\n")

    try:
        from vtool_llama_v2 import VToolLlamaV2
        from vtool_character_v2.soul import VToolLlamaAdapter

        llm = VToolLlamaV2(auto_load=True)
        llm.get_config()

        adapter = VToolLlamaAdapter(llm)
        _ = adapter
        session = llm.create_session(
            session_id=f"runtime_{name.lower()}",
            character_name=name,
            persistent=False,
        )

        print(f"  Chatting with '{name}'. Type 'quit' to exit.\n")

        history_limit = 10
        summary_system_prompt = cm.build_default_summary_system_prompt()
        memory_extraction_prompt = cm.build_default_memory_extraction_prompt()

        if cm.current_episode and getattr(cm.current_episode, "source", "") == "sqlite":
            backfilled = cm.backfill_context_summary(
                session_id=str(cm.current_episode.episode_id),
                chat_callable=lambda messages: session.chat(messages=messages),
                summary_system_prompt=summary_system_prompt,
                extraction_system_prompt=memory_extraction_prompt,
                every_n_messages=history_limit,
                history_limit=80,
                title=f"Chat with {name}",
                model_name=llm.get_model_info().get("model_name", ""),
                character_name=name,
            )
            if backfilled:
                print(f"  Context summary backfilled in {len(backfilled)} step(s).")

        while True:
            try:
                text = input("  You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.lower() in ("quit", "exit", "q"):
                break

            session_id = (
                str(cm.current_episode.episode_id)
                if cm.current_episode and getattr(cm.current_episode, "source", "") == "sqlite"
                else f"chat_{name.lower()}"
            )
            if cm.should_summarize_before_next_message(session_id, history_limit=history_limit):
                refreshed = cm.backfill_context_summary(
                    session_id=session_id,
                    chat_callable=lambda messages: session.chat(messages=messages),
                    summary_system_prompt=summary_system_prompt,
                    extraction_system_prompt=memory_extraction_prompt,
                    every_n_messages=history_limit,
                    history_limit=80,
                    title=f"Chat with {name}",
                    model_name=llm.get_model_info().get("model_name", ""),
                    character_name=name,
                )
                if refreshed:
                    print(f"  Context summary refreshed in {len(refreshed)} step(s) before the next message.")

            history = cm.get_chat_history_messages(session_id=session_id, history_limit=history_limit)
            messages = cm.build_chat_messages_from_summary(
                base_system_prompt=f"You are {name}.",
                user_message=text,
                session_id=session_id,
                history_limit=history_limit,
                chat_query=text,
            )
            resp = session.chat(messages=messages)
            print(f"  {name}: {_fmt(resp.content)}")

            flow_steps = [
                "1. El character cargó el historial relevante desde SQLite.",
                "2. El character construyó la lista completa de mensajes.",
                "3. La lista se envió a session.chat(messages=...).",
                "4. El modelo generó la respuesta.",
            ]

            if resp.success:
                assistant_message = {"role": "assistant", "content": resp.content}
                if resp.thinking:
                    assistant_message["thinking"] = resp.thinking
                if resp.tool_calls:
                    assistant_message["tool_calls"] = resp.tool_calls
                cm.append_chat_session_messages(
                    session_id=session_id,
                    messages=[
                        {"role": "user", "content": text},
                        assistant_message,
                    ],
                    character_name=name,
                    model_name=llm.get_model_info().get("model_name", ""),
                )
                flow_steps.append("5. El turno se guardó en SQLite sin reemplazar el historial.")
                flow_steps.append("6. Si el bloque activo llega al limite, el resumen se recalcula antes del siguiente mensaje.")
            else:
                flow_steps.append("5. No se escribió en SQLite porque la generación falló.")

            active_summary = cm.get_context_summary(session_id)
            cm.write_chat_turn_log(
                session_id=session_id,
                turn_index=cm.count_chat_turn_logs() + 1,
                user_message=text,
                response_message=resp.content,
                messages_sent=messages,
                flow_steps=flow_steps,
                error=None if resp.success else resp.error,
                system_prompt=messages[0].get("content", ""),
                chat_query=text,
                context_summary=active_summary.summary if active_summary else "",
                summarized_message_count=active_summary.summarized_message_count if active_summary else 0,
                source_messages=history,
            )

    except (ImportError, Exception) as e:
        print(f"  LLM unavailable ({type(e).__name__}), showing prompt preview.")
        prompt = cm.build_full_system_prompt(f"You are {name}.")
        print(f"\n  System prompt:\n{_fmt(prompt[:500])}...\n")

    # Persist character state
    cm.save_state()
    cm.save_psychology_state()

    try:
        sessions = cm.list_chat_sessions()
        if sessions:
            print(f"  Saved sessions: {len(sessions)}")
    except RuntimeError:
        pass


# ── main ─────────────────────────────────────────────────────────────

def main():
    print("\n=== Character Manager ===\n")

    cm = CharacterManager()

    while True:
        name = pick_or_create(cm)
        if name is None:
            break
        chat_loop(cm, name)

        again = input("\n  Another character? (y/N): ").strip().lower()
        if again != "y":
            break

    print("\n  Bye.\n")


if __name__ == "__main__":
    main()
