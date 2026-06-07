"""
Interactive example: create a character and converse with it.

This version keeps the historical logic inside vtool_character_v2:
- CharacterManager builds the full message list.
- vtool_llama_v2 only generates from explicit messages.
- SQLite persistence is handled by the character project.
"""

from __future__ import annotations

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

    # Use a lightweight runtime session only as a model wrapper.
    try:
        adapter = VToolLlamaAdapter(llm)
        soul = SoulGenerator(
            character_manager=cm,
            config=llm.get_config(),
            llm_client=adapter,
        )
        _ = soul
        session = llm.create_session(
            session_id=f"runtime_{name.lower()}",
            character_name=name,
            persistent=False,
        )
    except Exception as e:
        print(f"  Could not create chat session: {e}")
        return False

    print(f"\n  Chatting with {name}. Type 'quit' to exit.\n")

    history_limit = 10
    summary_system_prompt = cm.build_default_summary_system_prompt()
    memory_extraction_prompt = cm.build_default_memory_extraction_prompt()

    session_id = (
        str(cm.current_episode.episode_id)
        if cm.current_episode and getattr(cm.current_episode, "source", "") == "sqlite"
        else f"chat_{name.lower()}"
    )

    if cm.current_episode and getattr(cm.current_episode, "source", "") == "sqlite":
        backfilled = cm.backfill_context_summary(
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
        if backfilled:
            print(f"  Context summary backfilled in {len(backfilled)} step(s).")

    while True:
        try:
            text = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if text.lower() in ("quit", "exit", "salir"):
            break

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
            base_system_prompt=f"You are {name}, a writer and poet.",
            user_message=text,
            session_id=session_id,
            history_limit=history_limit,
            chat_query=text,
        )
        response = session.chat(messages=messages)
        safe_text = response.content.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(f"  {name}: {safe_text}")

        flow_steps = [
            "1. El character cargó el historial relevante desde SQLite.",
            "2. El character construyó la lista completa de mensajes.",
            "3. La lista se envió a session.chat(messages=...).",
            "4. El modelo generó la respuesta.",
        ]

        if response.success:
            assistant_message = {"role": "assistant", "content": response.content}
            if response.thinking:
                assistant_message["thinking"] = response.thinking
            if response.tool_calls:
                assistant_message["tool_calls"] = response.tool_calls

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
            response_message=response.content,
            messages_sent=messages,
            flow_steps=flow_steps,
            error=None if response.success else response.error,
            system_prompt=messages[0].get("content", ""),
            chat_query=text,
            context_summary=active_summary.summary if active_summary else "",
            summarized_message_count=active_summary.summarized_message_count if active_summary else 0,
            source_messages=history,
        )

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

    try:
        sessions = cm.list_chat_sessions()
        if sessions:
            print(f"\n  Saved sessions: {len(sessions)}")
            for s in sessions:
                print(f"    * {s['session_id']}: {s.get('title', 'untitled')}")
    except RuntimeError:
        pass


if __name__ == "__main__":
    main()
