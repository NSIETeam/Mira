# Development

This page collects contributor-facing notes for extending Mira. User-facing setup and runtime options live in [`configuration.md`](./configuration.md).

## Contributor Roadmap

If you want to move Mira toward a mature execution-kernel product, work in this order:

1. **Kernel/runtime safety first**
   - Keep execution, session, memory, provider routing, and tool orchestration inside the reusable kernel.
   - Prefer changing `mira/kernel/`, `mira/agent/`, `mira/session/`, and `mira/providers/` before touching shell-specific UI code.
2. **Shell contract second**
   - Add or change product behavior through grouped shell contracts:
     - `chrome`
     - `surfaces`
     - `actions`
     - `composer`
     - `privilege`
   - Avoid reintroducing flat booleans or UI-only privilege guesses.
3. **Operator console third**
   - Expose runtime state, faults, modules, bridges, queues, and recovery actions through stable action ids.
   - Prefer named action lookup over positional indexing.
4. **Native boundary last**
   - Pull performance-sensitive or OS-facing work behind native boundaries only when the Python path is already structurally correct.
   - Treat Rust/C extraction as a kernel-boundary exercise, not a UI rewrite.

### Current release-oriented work order

Use the open GitHub issues as the shipping checklist:

1. `#3` Mature WebUI shell for kernel control and operator workflows
2. `#8` Docs, release path, and contributor roadmap for mature Mira agent
3. `#12` Native bridge ABI and runtime control pipeline
4. `#13` Runtime root/user boundary finalization
5. `#14` Compatibility leftovers and dead-code cleanup

When multiple tasks compete, prefer the item that most directly improves:

1. runtime correctness
2. operator recoverability
3. privilege clarity
4. removal of compatibility shims

## Release Path

For a fast path to a production-ready Mira release:

1. **Freeze shell shape**
   - Treat the current execution kernel + engineering shell + kernel console structure as the release baseline.
2. **Close blocking maturity gaps**
   - Finish root/user runtime boundaries.
   - Finish operator-console control surfaces.
   - Finish native bridge/runtime-control boundaries.
3. **Delete leftovers**
   - Remove compatibility shims, duplicate action paths, and dead wrappers after the runtime/control path is stable.
4. **Then validate and ship**
   - Run build/test/release verification.
   - Update docs and close linked issues.

This order is intentional: do not spend release time on visual polish before runtime boundaries and operator recovery paths are stable.

## Adding an LLM Provider

Mira uses the provider registry in `mira/providers/registry.py` as the source of truth for LLM provider metadata. Most OpenAI-compatible providers need only two changes.

1. Add a `ProviderSpec` entry to `PROVIDERS`:

```python
ProviderSpec(
    name="myprovider",
    keywords=("myprovider", "mymodel"),
    env_key="MYPROVIDER_API_KEY",
    display_name="My Provider",
    default_api_base="https://api.myprovider.com/v1",
)
```

2. Add a field to `ProvidersConfig` in `mira/config/schema.py`:

```python
class ProvidersConfig(BaseModel):
    ...
    myprovider: ProviderConfig = Field(default_factory=ProviderConfig)
```

Environment variables, config matching, provider status, and WebUI credential display derive from those two entries.

Useful `ProviderSpec` options:

| Field | Description |
|---|---|
| `default_api_base` | Default OpenAI-compatible base URL. |
| `env_extras` | Additional environment variables derived from the provider config. |
| `model_overrides` | Per-model request parameter overrides. |
| `is_gateway` | Provider can route many model families, like OpenRouter. |
| `detect_by_key_prefix` | Match configured gateways by API-key prefix. |
| `detect_by_base_keyword` | Match configured gateways by API base URL. |
| `strip_model_prefix` | Strip `provider/` before sending the model to the upstream API. |
| `supports_max_completion_tokens` | Use `max_completion_tokens` instead of `max_tokens`. |
| `is_transcription_only` | Provider has credentials but cannot serve chat completions. |

## Adding a Transcription Provider

Transcription is intentionally split into two layers:

- `mira/audio/transcription_registry.py` owns provider names, aliases, default models, and adapter loading.
- `mira/providers/transcription.py` owns provider-specific HTTP behavior.

Credentials still live under `providers.<provider>` so chat channels and WebUI resolve API keys and API bases the same way.

1. Add provider credentials to `ProvidersConfig`.

```python
class ProvidersConfig(BaseModel):
    ...
    my_stt: ProviderConfig = Field(default_factory=ProviderConfig)
```

2. Add a `ProviderSpec` in `mira/providers/registry.py`.

For transcription-only providers, set `is_transcription_only=True` so they show up in credential/settings surfaces but stay out of chat model selection.

```python
ProviderSpec(
    name="my_stt",
    keywords=("my_stt",),
    env_key="MY_STT_API_KEY",
    display_name="My STT",
    default_api_base="https://api.example.com/v1",
    is_transcription_only=True,
)
```

3. Add an adapter class in `mira/providers/transcription.py`.

Adapters receive resolved credentials and settings. They return an empty string for provider errors so channel voice messages fail quietly instead of crashing the agent loop.

```python
class MySTTTranscriptionProvider:
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        language: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("MY_STT_API_KEY")
        self.api_base = api_base or "https://api.example.com/v1"
        self.language = language or None
        self.model = model or "my-default-stt-model"

    async def transcribe(self, file_path: str | Path) -> str:
        ...
```

4. Register the adapter in `mira/audio/transcription_registry.py`.

```python
TranscriptionProviderSpec(
    name="my_stt",
    default_model="my-default-stt-model",
    adapter="mira.providers.transcription:MySTTTranscriptionProvider",
    aliases=("mystt",),
)
```

5. Add tests.

At minimum, cover:

- config resolution in `tests/providers/test_transcription.py`
- adapter request/response behavior and retry/error handling
- WebUI settings payload/update behavior in `tests/webui/test_settings_api.py`
- provider brand mapping if the provider appears in Settings

6. Update user-facing docs.

Add the provider to [`configuration.md`](./configuration.md) where users choose `transcription.provider`, but keep implementation details in this development guide.

## Shell Model and Host Contract Rules

Mira should behave like a reusable kernel with thin shells layered on top.

- Kernel behavior belongs in `mira/kernel/` and lower runtime layers.
- Shell behavior belongs in `mira/kernel/shell.py`, `webui/src/shells/registry.ts`, and shell layout/hooks under `webui/src/shells/`.
- UI must consume host-contract intent instead of inferring privileges from labels or button placement.

When extending shells:

1. change the backend descriptor in `mira/kernel/shell.py`
2. keep the frontend registry aligned in `webui/src/shells/registry.ts`
3. preserve grouped host-contract semantics
4. prefer deleting compatibility bridges instead of adding new ones

If you need a new shell mode, make the mode explicit and keep the default engineering shell as the general-purpose operator surface.
