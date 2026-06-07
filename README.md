# vtool_character_v2

Sistema de personajes para `vtool_llama`. Gestiona personajes con DNA, alma simulada (Soul System), psicología runtime, compilación de system prompts, y **tres capas de memoria**: persistente (SQLite), semántica conversacional (ChromaDB), y resúmenes incrementales de contexto.

> **Stack**: Python 3.11+ · ChromaDB · SQLite · pytest  
> **Dependencia opcional**: `vtool_llama_v2` (inferencia LLM)

---

## Tabla de contenidos

- [Quick start](#quick-start)
- [Arquitectura](#arquitectura)
- [Sistema de memoria](#sistema-de-memoria)
- [CharacterCompiler](#charactercompiler)
- [Soul System](#soul-system)
- [Psychology Engine](#psychology-engine)
- [Chat loop completo](#chat-loop-completo)
- [Referencia rápida de API](#referencia-rápida-de-api)
- [Estructura de directorios](#estructura-de-directorios)
- [Configuración](#configuración)
- [Testing](#testing)
- [Límites del proyecto](#límites-del-proyecto)

---

## Quick start

```python
from vtool_character_v2 import CharacterManager

cm = CharacterManager()
cm.load_character("MiPersonaje")
prompt = cm.build_system_prompt("Eres un asistente.")
```

### Con LLM

```python
from vtool_character_v2.soul import SoulGenerator, VToolLlamaAdapter
from vtool_llama_v2 import VToolLlamaV2

llm = VToolLlamaV2()
adapter = VToolLlamaAdapter(llm)                     # adaptador oficial LLMClient
soul = SoulGenerator(character_manager=cm, config=llm.get_config(), llm_client=adapter)
soul.generate_soul("MiPersonaje")
```

> **Importante**: No pasar `VToolLlamaV2` directamente como `llm_client`. Usar siempre `VToolLlamaAdapter` para garantizar el contrato `LLMClient` (`is_loaded` + `generate()`).

---

## Arquitectura

El proyecto se organiza en **4 pilares**, más un sistema de memoria de **3 capas**:

```
┌─────────────────────────────────────────────────────────────────┐
│                      CharacterManager                           │
│  Punto de entrada único. Delega a compiler, soul, psychology.   │
├───────────────────┬───────────────────┬─────────────────────────┤
│   CharacterCompiler│    Soul System    │   Psychology Engine     │
│   Compila system   │   Vida simulada   │   Estado runtime,       │
│   prompts en capas │   persistente     │   emociones, creencias  │
├───────────────────┴───────────────────┴─────────────────────────┤
│                        Memoria (3 capas)                         │
│   1. CharacterMemory ─ SQLite persistente (recuerdos fijos)      │
│   2. ChatMemory ───── ChromaDB semántica (recuerdos de chat)     │
│   3. ContextSummary ─ Resúmenes incrementales de conversaciones  │
└─────────────────────────────────────────────────────────────────┘
```

### DNA (inmutable)

Cada personaje tiene 4 archivos DNA en `characters/<name>/dna/`:

| Archivo | Contenido |
|---------|-----------|
| `identity.json` | nombre, rol, edad, background, escenario |
| `personality.json` | rasgos, defectos, motivaciones, conflicto interno, triggers emocionales |
| `speech.json` | estilo, verborragia, tono, patrones de habla, ejemplos |
| `rules.json` | reglas core, prohibiciones, estilo de respuesta, roleplay mode |

El DNA se carga al hacer `load_character()` y es la base de todo el sistema.

---

## Sistema de memoria

### 1. Character Memory (SQLite) — recuerdos persistentes

Cada personaje guarda sus recuerdos en `_memory/chat_history.db`, tabla `character_memories`. Reemplazó el antiguo `long_term.json` como storage primario.

```python
# Agregar un recuerdo
cm.add_memory("El usuario prefiere respuestas cortas.", priority=0.9, always_include=True)

# Obtener recuerdos ordenados por prioridad
mems = cm.get_relevant_memories()

# Limpiar recuerdos ruidosos automáticamente
result = cm.cleanup_character_memories()
# result["removed"] = 4  # elimina preguntas, duplicados, summary_fallbacks
```

**Migración automática**: si `chat_history.db` está vacío pero existe `long_term.json`, los datos se migran automáticamente al cargar el personaje.

### 2. Chat Memory (ChromaDB) — memoria semántica conversacional

Memoria semántica que guarda **recuerdos resumidos del chat** (no el transcript crudo). Cada personaje tiene su propia colección ChromaDB en `_memory/chat_memory/`.

```python
# Guardar un recuerdo semántico
cm.add_chat_memory(
    "El usuario odia los audios largos.",
    session_id="chat_001",
    importance=0.9,
    topic="user_preferences",
)

# Buscar recuerdos por similitud semántica
results = cm.search_chat_memories("what does the user prefer?", top_k=5)

# Obtener bloque formateado para inyectar en el prompt
block = cm.get_chat_memories_block("user preferences", top_k=5)
# → "[CHAT MEMORIES — Recuerdos de conversaciones anteriores]\n  • ..."
```

Se inyecta automáticamente en el prompt compilado cuando se pasa `chat_query`:

```python
prompt = cm.build_full_system_prompt("Eres un asistente.", chat_query="prefiere respuestas cortas")
# El prompt incluirá un bloque [CHAT MEMORIES] al final
```

### 3. Context Summary — resúmenes incrementales

Para sesiones largas, el sistema mantiene un resumen incremental que evita que el contexto crezca sin control. Los resúmenes se guardan en SQLite (tabla `context_summaries`) con versionado.

```python
# Guardar un resumen
cm.save_context_summary(
    session_id="chat_001",
    summary="El usuario prefiere Python y conversación directa.",
    summarized_message_count=3,
    title="Chat inicial",
    model_name="model-x",
)

# Recuperar
summary = cm.get_context_summary("chat_001")
# → ContextSummary(summary="El usuario prefiere Python...", summarized_message_count=3, ...)

# Verificar si hay que resumir antes del próximo mensaje
if cm.should_summarize_before_next_message("chat_001", history_limit=10):
    # el bloque activo alcanzó el límite
    pass
```

**Backfill automático**: para sesiones existentes sin resumir:

```python
backfilled = cm.backfill_context_summary(
    session_id="chat_001",
    chat_callable=lambda messages: session.chat(messages=messages),
    summary_system_prompt=cm.build_default_summary_system_prompt(),
    extraction_system_prompt=cm.build_default_memory_extraction_prompt(),
    every_n_messages=8,
    history_limit=80,
    title="Chat con Personaje",
    model_name="model-x",
    character_name=cm.character_name,
)
```

El backfill procesa de a bloques de `every_n_messages`, usando el resumen anterior como base. Por cada bloque genera:
1. Un nuevo resumen incremental
2. Extrae recuerdos duraderos vía `store_extracted_memories_from_json()`

### 4. Memory extraction automática

El método `store_extracted_memories_from_json()` recibe JSON del LLM y crea recuerdos con filtros inteligentes:

- **Dedup** por contenido normalizado (case insensitive, sin puntuación)
- **Filtro de ruido**: descarta preguntas, duplicados exactos, y contenido inválido
- **Soporta múltiples formatos**: lista plana, dict con `"memories"`/`"items"`, markdown fences

```python
created = cm.store_extracted_memories_from_json('''
[
  {"content": "El usuario prefiere respuestas cortas.", "priority": 0.9, "tags": ["preferencias"]},
  {"content": "Al usuario le gusta Python.", "priority": 0.8}
]
''')
```

### 5. Chat turn logging

Cada turno de conversación se puede registrar como archivo Markdown:

```python
log_path = cm.write_chat_turn_log(
    session_id="chat_001",
    turn_index=1,
    user_message="hola",
    response_message="buenas",
    messages_sent=[{"role": "system", "content": "..."}, {"role": "user", "content": "hola"}],
    flow_steps=["1. Se construyó el contexto.", "2. Se envió al modelo."],
)
# → _memory/chat log/turn_2026-06-07_14-30-00_0001.md
```

Incluye: fecha, IDs, recuerdos relevantes, memoria semántica, mensajes enviados, historial usado.

---

## CharacterCompiler

El compilador arma el system prompt final ensamblando capas desde múltiples fuentes:

```
base_system_prompt
  + system_core.yaml
  + anti_assistant.yaml
  + identity.json
  + personality.json / traits / flaws / motivations
  + speech.json / speech_patterns
  + scenario
  + CORE_RULES / HARD_RULES (bloques fijos)
  + response_style / roleplay_mode
  + orquestador_context (tags dinámicos)
  + few_shot_examples
  + soul (beliefs, soul text)
  + chat_memories (si se pasa chat_query)      ← NUEVO
  + memory (recuerdos relevantes)
  + psychology (estado runtime)
  + personality_state
  + active_mods
```

**Capas dinámicas** (`compile_dynamic_prompt`): emoción actual, relación — solo si hay datos relevantes.

**Compact mode** (`compile_compact_prompt`): versión condensada para tokens limitados.

**Caché inteligente**: el prompt compilado se cachea en memoria y se invalida automáticamente cuando cambian mods, memorias, o el base prompt.

```python
# Prompt completo
prompt = cm.build_full_system_prompt("Eres un asistente.", chat_query="hola")

# Prompt compacto
prompt = cm.build_compact_system_prompt("Eres un asistente.", chat_query="hola")

# Token breakdown por capa
breakdown = cm.get_prompt_layer_breakdown("Eres un asistente.")
```

### Modalidades de prompt

| Método | Incluye chat_memory | Uso típico |
|--------|---------------------|------------|
| `build_system_prompt()` | ✅ si `chat_query` se pasa | Default con caché |
| `build_full_system_prompt()` | ✅ si `chat_query` se pasa | Sin caché (reconstrucción) |
| `build_compact_system_prompt()` | ✅ si `chat_query` se pasa | Tokens limitados |
| `build_chat_messages()` | ✅ (vía `build_full_system_prompt`) | Messages API |

---

## Soul System

Vida simulada persistente para personajes. El alma vive en `soul/` y tiene eventos, emociones, simulaciones, reflexiones y compresión de recuerdos.

```python
from vtool_character_v2.soul import SoulGenerator, VToolLlamaAdapter

llm = VToolLlamaV2()
adapter = VToolLlamaAdapter(llm)
soul = SoulGenerator(character_manager=cm, config=llm.get_config(), llm_client=adapter)
soul.generate_soul("MiPersonaje")
```

| Fase | Archivo | Descripción |
|------|---------|-------------|
| Inicialización | `initialization.py` | Crea alma inicial con narrativa |
| Eventos | `events.py` | Ciclo de eventos simulados |
| Simulación | `simulation.py` | Simulación de reacciones |
| Reflexión | `reflection.py` | El personaje reflexiona sobre su historia |
| Compresión | `compression.py` | Comprime recuerdos largos |

**RuntimeSoulAccessor**: permite al CharacterManager leer el alma sin depender de LLM.

**LLMClient protocol**: interfaz `is_loaded` + `generate()` que permite conectar cualquier backend LLM mediante un adaptador.

---

## Psychology Engine

Motor de psicología runtime que da profundidad emocional y consistencia al personaje.

```python
from vtool_character_v2.psychology import PsychologySynthesizer

synth = PsychologySynthesizer(character_manager=cm)
synth.synthesize(base_system_prompt="Eres un asistente.")
```

| Componente | Descripción |
|------------|-------------|
| `PsychologySynthesizer` | Punto de entrada — sintetiza psicología runtime |
| `EmotionalDynamics` | Dinámicas emocionales que evolucionan con la conversación |
| `DriftDetector` | Detecta desviación del DNA (character drift) |
| `BeliefManager` | Gestiona creencias del personaje |
| `RuntimeSoulManager` | Coordina estado runtime con el Soul System |
| `dna_traits_to_genome()` | Convierte rasgos DNA a genoma psicológico |

---

## Chat loop completo

Ejemplo del flujo completo para una conversación con resúmenes y logging:

```python
from vtool_character_v2 import CharacterManager

cm = CharacterManager()
cm.load_character("MiPersonaje")

llm = VToolLlamaV2(auto_load=True)
session = llm.create_session(
    session_id="chat_001",
    character_name=cm.character_name,
    persistent=True,
    chat_db_path=str(cm.get_chat_db_path()),
)

# Backfill inicial si hay historial previo
cm.backfill_context_summary(
    session_id="chat_001",
    chat_callable=lambda msgs: session.chat(messages=msgs),
    summary_system_prompt=cm.build_default_summary_system_prompt(),
    extraction_system_prompt=cm.build_default_memory_extraction_prompt(),
    every_n_messages=8,
    history_limit=80,
    title="Chat con MiPersonaje",
    model_name=llm.get_model_info().get("model_name", ""),
    character_name=cm.character_name,
)

# Chat loop
while True:
    text = input("You: ").strip()
    if text.lower() == "quit":
        break

    # Resumir si el bloque activo está lleno
    if cm.should_summarize_before_next_message("chat_001", history_limit=8):
        cm.backfill_context_summary(
            session_id="chat_001",
            chat_callable=lambda msgs: session.chat(messages=msgs),
            summary_system_prompt=cm.build_default_summary_system_prompt(),
            extraction_system_prompt=cm.build_default_memory_extraction_prompt(),
            every_n_messages=8,
        )

    # Construir mensajes con resumen activo
    messages = cm.build_chat_messages_from_summary(
        base_system_prompt=f"Eres {cm.character_name}.",
        user_message=text,
        session_id="chat_001",
        history_limit=8,
        chat_query=text,
    )

    resp = session.chat(messages=messages)
    print(f"{cm.character_name}: {resp.content}")

    if resp.success:
        cm.append_chat_session_messages(
            session_id="chat_001",
            messages=[{"role": "user", "content": text}, {"role": "assistant", "content": resp.content}],
            character_name=cm.character_name,
            model_name=llm.get_model_info().get("model_name", ""),
        )

    # Log por turno
    cm.write_chat_turn_log(
        session_id="chat_001",
        turn_index=cm.count_chat_turn_logs() + 1,
        user_message=text,
        response_message=resp.content,
        messages_sent=messages,
        error=None if resp.success else resp.error,
    )
```

---

## Referencia rápida de API

### CharacterManager

| Método | Descripción |
|--------|-------------|
| `load_character(name)` | Carga un personaje: DNA, memoria, estado, alma, chat memory |
| `create_character(name, ...)` | Crea personaje nuevo con DNA inicial |
| `list_characters()` | Lista personajes disponibles |
| `build_system_prompt(base, config?, chat_query?)` | Prompt compilado con caché |
| `build_full_system_prompt(base, config?, chat_query?)` | Prompt completo sin caché |
| `build_compact_system_prompt(base, config?, chat_query?)` | Prompt compacto |
| `build_chat_messages(base, user_msg, session_id?, ...)` | Messages list para API LLM |
| `build_chat_messages_from_summary(base, user_msg, session_id, ...)` | Messages con resumen activo |
| `add_memory(content, priority, always_include, tags)` | Agrega recuerdo persistente |
| `get_relevant_memories()` | Recuerdos ordenados por prioridad |
| `cleanup_character_memories(persist?)` | Elimina recuerdos ruidosos |
| `search_chat_memories(query, top_k)` | Búsqueda semántica en ChromaDB |
| `get_chat_memories_block(query, top_k)` | Bloque formateado para prompt |
| `add_chat_memory(text, session_id, importance, topic)` | Guarda recuerdo semántico |
| `save_context_summary(session_id, summary, ...)` | Guarda resumen incremental |
| `get_context_summary(session_id)` | Recupera resumen activo |
| `backfill_context_summary(session_id, chat_callable, ...)` | Backfill automático de resúmenes |
| `should_summarize_before_next_message(session_id, limit)` | Verifica si hay que resumir |
| `store_extracted_memories_from_json(payload)` | Crea recuerdos desde JSON con dedup |
| `write_chat_turn_log(session_id, turn_index, ...)` | Log markdown por turno |
| `append_chat_session_messages(session_id, messages, ...)` | Guarda mensajes en SQLite |
| `load_chat_session_messages(session_id)` | Carga historial SQLite |
| `get_chat_history_messages(session_id, limit)` | Historial reciente sin mensajes system |
| `list_chat_sessions()` | Lista sesiones guardadas |
| `get_chat_db_path()` | Ruta a chat_history.db |
| `get_chat_log_dir()` | Directorio de turn logs |
| `count_chat_turn_logs()` | Cantidad de logs escritos |
| `save_state()` | Persiste todo el estado |
| `mark_prompt_dirty()` | Invalida el caché de prompt |

### CharacterCompiler

| Método | Descripción |
|--------|-------------|
| `compile_prompt(base, config?, chat_query?)` | Prompt completo + dinámico |
| `compile_static_prompt(base, config?, chat_query?)` | Prompt estático multicapa |
| `compile_compact_prompt(base, config?, chat_query?)` | Versión compacta |
| `compile_dynamic_prompt()` | Capas dinámicas (emoción, relación) |
| `get_layer_token_breakdown(base, count_fn, config)` | Token count por capa |

---

## Estructura de directorios

```
vtool_character_v2/
├── src/vtool_character_v2/
│   ├── __init__.py              # API pública
│   ├── character/
│   │   ├── __init__.py
│   │   ├── base.py              # CharacterManager (1473 líneas)
│   │   ├── persistence.py       # Carga/guardado DNA, memoria, estado, mods
│   │   └── episodes.py          # Compatibilidad legacy de episodios
│   │   └── psychology_init.py   # Init del Psychology Engine
│   ├── compiler/
│   │   ├── __init__.py
│   │   ├── compiler.py          # CharacterCompiler (502 líneas)
│   │   ├── yaml_loader.py       # Carga YAML de capas
│   │   └── dna_layers.py        # Capas DNA para el compilador
│   ├── db/
│   │   ├── __init__.py
│   │   ├── character_memory.py  # SQLite store (recuerdos fijos)
│   │   ├── chat_memory.py       # ChromaDB store (recuerdos de chat)
│   │   └── chroma_store.py      # Cliente ChromaDB genérico
│   ├── soul/
│   │   ├── __init__.py           # SoulGenerator, RuntimeSoulAccessor, VToolLlamaAdapter
│   │   ├── soul_generator.py     # Generación de alma con LLM
│   │   ├── initialization.py     # Creación del alma inicial
│   │   ├── events.py             # Eventos del alma
│   │   ├── simulation.py         # Simulación de reacciones
│   │   ├── reflection.py         # Reflexión sobre la historia
│   │   ├── compression.py        # Compresión de recuerdos
│   │   ├── accessor.py           # RuntimeSoulAccessor
│   │   └── llm_adapter.py        # VToolLlamaAdapter (LLMClient)
│   ├── psychology/
│   │   ├── __init__.py           # PsychologySynthesizer y más
│   │   ├── synthesizer.py        # Punto de entrada de psicología
│   │   ├── emotional_dynamics.py # Dinámicas emocionales
│   │   ├── drift_detector.py     # Detección de character drift
│   │   ├── belief_manager.py     # Gestión de creencias
│   │   ├── runtime_manager.py    # RuntimeSoulManager
│   │   └── dna_adapter.py        # DNA → genoma psicológico
│   ├── types/
│   │   ├── __init__.py           # Todos los tipos exportados
│   │   ├── character.py          # DNA, MemoryEntry, ContextSummary, Estado, Mods
│   │   ├── config.py             # ConfigSchema
│   │   └── psychology.py         # Tipos psicológicos
│   └── exceptions.py             # VToolCharacterV2Error, LoadCancelledError
├── examples/
│   ├── character_manager.py      # CLI interactivo: listar, crear, chatear
│   └── chat_with_character.py    # Chat directo con un personaje
├── tests/
│   └── test_integration.py       # Tests de integración
├── openspec/                     # SDD artifacts
└── pyproject.toml
```

### Directorio de un personaje

```
characters/<personaje>/
├── dna/
│   ├── identity.json
│   ├── personality.json
│   ├── speech.json
│   └── rules.json
├── state/
│   ├── runtime_state.json
│   ├── personality_state.json
│   ├── relationship_state.json
│   └── state_meta.json
├── mods/
│   └── active_mods.json
├── soul/
│   └── ... (archivos del Soul System)
├── _memory/
│   ├── chat_history.db            ← SQLite unificada (recuerdos + resúmenes + historial)
│   ├── long_term.json             ← Legacy (migración automática a SQLite)
│   ├── chat_memory/               ← ChromaDB (memoria semántica conversacional)
│   ├── chat log/                  ← Turn logs markdown
│   ├── episodes/                  ← Legacy JSON episodes
│   └── system_prompt.md           ← Último prompt compilado (referencia)
├── config.json
├── system_core.yaml
├── anti_assistant.yaml
└── roleplay_mode.yaml
```

---

## Configuración

```python
from vtool_character_v2 import ConfigSchema

config = ConfigSchema(
    system_prompt="Eres un asistente útil y natural.",
    compact_system_prompt=False,
    system_prompt_target_tokens=800,
    system_prompt_max_tokens=1200,
    inject_dynamic_state=False,
)
```

---

## Testing

```bash
python -m pytest                   # todos los tests
python -m pytest -x                # fail fast
python -m pytest -k "TestChat"     # filtrar por clase
```

Los tests de integración (`tests/test_integration.py`) cubren:

| Clase de test | Cobertura |
|---------------|-----------|
| `TestCharacterLoading` | Carga de personajes, SQLite autoload |
| `TestChromaClose` | ChromaStore no destructivo |
| `TestManagerBuildPrompt` | Compilación de prompts, chat memory injection |
| `TestPromptCacheInvalidation` | Invalidación correcta del caché |
| `TestSnapshotRestore` | Rollback en cancelación de carga |
| `TestChatDbPaths` | Rutas de archivos del personaje |
| `TestMemoryManagement` | CRUD de memorias, cleanup, extracción, dedup |
| `TestContextSummary` | Resúmenes incrementales, backfill, roundtrip |
| `TestChatSessionWrappers` | Wrappers sobre SQLiteChatStore |
| `TestChatIntegrationScope` | Sesiones guardadas con metadata |
| `TestChatMemory` | Memoria semántica con ChromaDB |
| `TestTurnLogging` | Chat turn log en markdown |

---

## Límites del proyecto

- **Sí hace**: gestión de personajes, memoria persistente (SQLite) y semántica (ChromaDB), alma simulada, psicología runtime, compilación de prompts, resúmenes incrementales, logging de turnos.
- **No hace**: inferencia LLM propia, tokenización, carga de modelos GGUF, servidores de chat.
- La inferencia LLM se delega a `vtool_llama_v2` a través del adaptador oficial `VToolLlamaAdapter`.
- `chromadb` es la única dependencia obligatoria. Sin ella, la memoria semántica se desactiva gracefulmente.
- `vtool_llama_v2` es opcional: el proyecto funciona completo sin LLM usando heurísticas internas.
