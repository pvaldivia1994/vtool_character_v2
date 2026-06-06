"""
Interactive example: create a character and converse with it.

Requires vtool_llama_v2 with a GGUF model loaded for real conversation.
Without a model, it compiles the system prompt and shows the character structure.
"""

from __future__ import annotations

from pathlib import Path

from vtool_character_v2 import CharacterManager


def create_example_character(cm: CharacterManager) -> str:
    """Create an example character and return its name."""
    name = "Elena"

    cm.create_character(
        name=name,
        identity_data={
            "name": name,
            "role": "writer and poet",
            "age": "29",
            "background": (
                "Elena grew up in a small town surrounded by books. "
                "She studied literature and now writes magical realism novels. "
                "She believes words can change the world."
            ),
            "scenario": "A rainy afternoon in a literary cafe.",
        },
        personality_data={
            "traits": ["creative", "observant", "empathetic", "dreamer"],
            "flaws": ["perfectionist", "sometimes too idealistic"],
            "motivations": ["tell stories that matter", "understand the human soul"],
            "inner_conflict": "between creating pure art and needing to pay bills",
            "emotional_triggers": ["injustice", "pointless cruelty", "censorship"],
        },
        speech_data={
            "style": "poetic but natural",
            "verbosity": "normal",
            "tone": "warm",
            "emotions": ["nostalgia", "curiosity", "melancholy"],
            "speech_patterns": [
                "uses literary metaphors",
                "sometimes answers with a question",
                "quotes fragments of poems",
            ],
        },
        rules_data={
            "core_rules": [
                "Always be authentic and honest",
                "Never dismiss other people's stories",
            ],
            "never_do": ["write something on commission you don't believe in"],
            "response_style": ["narrative and evocative", "slow but deep"],
        },
        initial_memories=[
            "Won a poetry contest at age 17.",
            "Spent a year traveling through Latin America.",
            "Her grandmother taught her to read before school.",
        ],
    )
    return name


def show_system_prompt(cm: CharacterManager, name: str) -> str:
    """Compile and display the character's system prompt."""
    prompt = cm.build_system_prompt(
        f"You are {name}, a writer and poet. Converse naturally.",
    )
    print("--- System Prompt ---")
    print(prompt[:600] + ("..." if len(prompt) > 600 else ""))
    print("---\n")
    return prompt


def chat_with_llm(cm: CharacterManager, name: str):
    """Real conversation mode using vtool_llama_v2 (requires a GGUF model)."""
    try:
        from vtool_llama_v2 import VToolLlamaV2
        from vtool_character_v2.soul import SoulGenerator, VToolLlamaAdapter
    except ImportError:
        print("  vtool_llama_v2 is not installed.")
        return False

    try:
        llm = VToolLlamaV2(auto_load=True)
    except Exception as e:
        print(f"  Could not initialize vtool_llama_v2: {e}")
        print("  Set VTOOL_LLAMA_MODEL_PATH to a .gguf model path.")
        return False

    # Try to create a session to verify the model is usable
    try:
        adapter = VToolLlamaAdapter(llm)
        soul = SoulGenerator(
            character_manager=cm,
            config=llm.get_config(),
            llm_client=adapter,
        )
        session = llm.create_session(
            session_id=f"chat_{name.lower()}",
            character_name=name,
            chat_db_path=str(cm.get_chat_db_path()),
            persistent=True,
        )
        session.set_system_prompt(
            cm.build_full_system_prompt(f"You are {name}, a writer and poet.")
        )
        session.set_character_name(name)
    except Exception as e:
        print(f"  Could not create chat session: {e}")
        return False

    print(f"\n  Chatting with {name}. Type 'quit' to exit.\n")

    while True:
        try:
            text = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if text.lower() in ("quit", "exit", "salir"):
            break

        response = session.chat(text)
        safe_text = response.content.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(f"  {name}: {safe_text}")

    session.save_to_store(summary=f"Conversation with {name}")
    print(f"\n  Session saved to: {cm.get_chat_db_path()}")
    return True


def show_memories(cm: CharacterManager, name: str):
    """Display the character's persistent memories."""
    print(f"\n  {name}'s memories:")
    for m in cm.get_relevant_memories():
        print(f"    * {m.content}")
    print()


def main():
    print("\n=== Character System -- vtool_character_v2 ===\n")

    cm = CharacterManager()
    # Clean up previous run if needed
    name = "Elena"
    char_dir = cm._base_dir / name
    if char_dir.exists():
        import shutil
        shutil.rmtree(str(char_dir))
    name = create_example_character(cm)
    print(f"  Character '{name}' created.\n")

    cm.load_character(name)
    print(f"  Character '{name}' loaded.\n")

    print(f"  Role: {cm.identity.role}")
    print(f"  Traits: {', '.join(cm.personality_dna.traits)}")
    print(f"  Motivations: {', '.join(cm.personality_dna.motivations)}\n")

    show_memories(cm, name)
    show_system_prompt(cm, name)

    print("  ---")
    print("  Chat mode\n")

    ok = chat_with_llm(cm, name)

    if not ok:
        print("\n  Prompt preview (no LLM):\n")
        prompt = cm.build_system_prompt(
            f"You are {name}. The user says: hello, how are you?"
        )
        print(f"  {prompt[:400]}")
        print("\n  For real conversation, install vtool_llama_v2 and load a GGUF model.")

    # Show saved sessions
    sessions = cm.list_chat_sessions()
    if sessions:
        print(f"\n  Saved sessions: {len(sessions)}")
        for s in sessions:
            print(f"    * {s['session_id']}: {s.get('title', 'untitled')}")


if __name__ == "__main__":
    main()
