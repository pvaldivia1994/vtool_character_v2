# vtool_character_v2

Character System para vtool_llama. Maneja personajes con DNA, alma simulada (Soul System), psicología runtime y compilación de system prompts.

## Dependencias

| Dependencia | Tipo | Propósito |
|---|---|---|
| **chromadb** | obligatoria | Almacenamiento vectorial de memorias |
| **vtool_llama_v2** | opcional (recomendada) | Inferencia LLM para SoulGenerator y Psychology |

> `vtool_llama_v2` es **opcional**: el proyecto funciona completo sin LLM usando heurísticas internas.
> El contrato de integración es `LLMClient` (`is_loaded` + `generate()`). Ver sección [Con LLM](#con-llm-soulgenerator).

## Límites del proyecto

- **Sí hace**: gestión de personajes, memoria episódica, alma simulada, psicología runtime, compilación de prompts, almacenamiento vectorial.
- **No hace**: inferencia LLM propia, tokenización, carga de modelos GGUF, servidores de chat.
- La inferencia LLM se delega a `vtool_llama_v2` a través del adaptador oficial `VToolLlamaAdapter`.

## Uso básico

```python
from vtool_character_v2 import CharacterManager

cm = CharacterManager()
cm.load_character("MiPersonaje")
prompt = cm.build_system_prompt("Eres un asistente.")
```

### Con LLM (SoulGenerator)

```python
from vtool_character_v2.soul import SoulGenerator, VToolLlamaAdapter
from vtool_llama_v2 import VToolLlamaV2

llm = VToolLlamaV2()
adapter = VToolLlamaAdapter(llm)  # adaptador oficial LLMClient
soul = SoulGenerator(
    character_manager=cm,
    config=llm.get_config(),
    llm_client=adapter,
)
soul.generate_soul("MiPersonaje")
```

> **Importante:** No pasar `VToolLlamaV2` directamente como `llm_client`. Usar siempre `VToolLlamaAdapter` para garantizar el contrato `LLMClient` (`is_loaded` + `generate()`).

## Historial conversacional (SQLite)

El transcript de conversaciones **no vive aquí**. Su dueño es `vtool_llama_v2` a través de `SQLiteChatStore`.
`vtool_character_v2` solo define la ruta y ofrece helpers de conveniencia.

### Ubicación

Cada personaje tiene su propia base SQLite:

```
characters/<personaje>/_memory/
├── long_term.json      ← recuerdos persistentes del personaje
├── chat_history.db     ← conversaciones guardadas (SQLite, dueño: vtool_llama_v2)
├── system_prompt.md    ← prompt compilado (referencia visual, se regenera automáticamente)
└── episodes/           ← legacy JSON (compatibilidad)
```

### Uso

```python
from vtool_character_v2 import CharacterManager
from vtool_llama_v2 import VToolLlamaV2

cm = CharacterManager()
cm.load_character("MiPersonaje")

# Obtener ruta al DB del personaje cargado
db_path = cm.get_chat_db_path()

# Listar sesiones guardadas
sesiones = cm.list_chat_sessions()

# Borrar una sesión
cm.delete_chat_session("chat_001")

# Renombrar
cm.rename_chat_session("chat_001", "Nuevo título")
```

### Crear una sesión persistente

```python
llm = VToolLlamaV2(auto_load=False)
session = llm.create_session(
    session_id="chat_001",
    character_name=cm.character_name,
    chat_db_path=str(cm.get_chat_db_path()),
    persistent=True,
)

session.chat("Hola")
session.save_to_store(summary="Conversación inicial")
```

### Compatibilidad legacy

Los métodos `list_episodes()`, `load_episode()`, `delete_episode()` en `CharacterManager`
siguen funcionando como wrappers que unifican sesiones SQLite y episodios JSON legacy.
Usan `source: "sqlite"` o `source: "legacy"` para distinguir el origen.

| Memoria | Archivo | Dueño |
|---|---|---|
| Recuerdos del personaje | `_memory/long_term.json` | `vtool_character_v2` |
| Prompt compilado (referencia) | `_memory/system_prompt.md` | `vtool_character_v2` |
| Transcript conversacional | `_memory/chat_history.db` | `vtool_llama_v2` |
| Línea de vida (soul) | `soul/` | `vtool_character_v2` |
