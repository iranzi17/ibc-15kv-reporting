# IBC Reporting Platform

Professional reporting workspace for daily site supervision, contractor-to-consultant report conversion, Google Sheets review, and final DOCX report generation.

The app is designed first for operational users:
- site engineers
- supervisors
- consultants
- reporting and controls staff

AI features remain available, but they now sit behind the reporting workflow instead of defining the product identity.

## Product Structure

The Streamlit app is organized into four workspaces:

1. **Reporting Workspace**
   - discipline, site, and date filters
   - review and edit rows from Google Sheets
   - attach or paste site photos by site/date pair
   - generate final ZIP exports with the canonical report engine

2. **Contractor Conversion**
   - paste contractor text
   - attach source documents, images, and audio
   - convert to consultant rows
   - refine with strict source-grounded controls and field locking
   - append approved rows to Google Sheets

3. **Advanced AI Tools**
   - shared project reference uploads
   - saved reusable AI guidance
   - research assistant
   - secondary general AI assistant
   - spreadsheet analyst

4. **System Diagnostics & Maintenance**
   - runtime issue history
   - AI provider usage log
   - safe maintenance actions
   - maintenance backlog

## Canonical Modules Preserved

These modules remain the canonical sources of truth:

- `report.py`
  DOCX generation, gallery composition, signatories, captions, ZIP export
- `report_structuring.py`
  canonical `REPORT_HEADERS`, local parser, alias resolution
- `sheets.py`
  Google Sheets access, append operations, offline cache helpers
- `config.py`
  application configuration and env/file overrides
- `api.py`
  FastAPI/mobile/backend interface that shares the same report and schema assumptions

The refactor builds around those files instead of creating parallel implementations.

## New Architecture

The previous `app.py` god-file was split into clearer layers:

- `app.py`
  thin Streamlit orchestrator and compatibility surface
- `core/session_state.py`
  session-state keys, persistent AI memory, runtime issue store, reset helpers
- `services/openai_client.py`
  OpenRouter/OpenAI provider selection, key/model loading, SDK checks, general assistant requests
- `services/model_routing.py`
  task-based routing profiles, provider-aware model defaults, fallback models, OpenRouter plugin policy
- `services/converter_service.py`
  contractor conversion/refinement logic, normalization, validation, locking, change summaries
- `services/media_service.py`
  file/input helpers, transcription, image captioning, text-to-speech
- `services/research_service.py`
  research assistant, tool routing, file search, spreadsheet analysis
- `services/self_healing_service.py`
  maintenance analysis helper
- `services/usage_logging.py`
  lightweight JSONL usage log for AI-powered actions
- `streamlit_ui/theme.py`
  restrained professional theme
- `streamlit_ui/layout.py`
  reusable section, note, and KPI helpers
- `streamlit_ui/reporting_workspace.py`
  main reporting workflow
- `streamlit_ui/converter_workspace.py`
  contractor conversion/refinement workflow
- `streamlit_ui/advanced_ai_workspace.py`
  optional AI support tools
- `streamlit_ui/diagnostics_workspace.py`
  diagnostics and maintenance console

## AI Provider Configuration

OpenRouter is the default AI provider. Add your OpenRouter API key either to Streamlit secrets or the environment:

```toml
# .streamlit/secrets.toml
OPENROUTER_API_KEY = "your-openrouter-api-key"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
AI_PROVIDER = "openrouter"
```

Or:

```powershell
$env:OPENROUTER_API_KEY = "your-openrouter-api-key"
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
$env:AI_PROVIDER = "openrouter"
```

The **AI Provider & Model** panel also accepts a session-only API key and model in the browser.

OpenAI remains supported as an optional secondary provider for workflows that still require OpenAI Responses tools:

```toml
OPENAI_API_KEY = "your-openai-api-key"
OPENAI_MODEL = "gpt-4o-mini"
AI_PROVIDER = "openai"
```

Provider behavior:

- OpenRouter mode uses Chat Completions for contractor conversion/refinement, structured JSON output, research, web plugin calls, image captioning, PDF/image/text attachments, and audio-input transcription on compatible models.
- OpenAI mode remains available for Responses-only tools such as vector-store file search, Code Interpreter spreadsheet analysis, and text-to-speech readback.

### Routing Profiles

OpenRouter support is controlled through `services/model_routing.py`, not by scattering model names through UI code. The current routing profiles are:

- `conversion_strict`
  Structured contractor-to-consultant conversion with strict JSON output, file-parser support, and response-healing support.
- `refinement_strict`
  Structured refinement of converted rows with strict JSON output, file-parser support, and response-healing support.
- `captioning_vision`
  Site-photo captions with structured JSON output and optional one-retry fallback.
- `general_chat_economy`
  Secondary general assistant chat with lower token budget.
- `research_tooling`
  Research assistant routing with optional web/file-parser support.
- `transcription_audio`
  Voice-note transcription routing for OpenRouter audio input or OpenAI transcription.

Each profile defines provider-specific primary and fallback models, temperature, token budget, structured-output requirements, and allowed OpenRouter plugins.

Fallback behavior is intentionally limited:

- Contractor conversion and contractor refinement retry once on transient provider/model availability failures.
- Image captioning also retries once when the configured fallback model differs from the primary model.
- Schema mismatches, validation errors, unsupported content, and deterministic parsing failures are not retried indefinitely.

To override models without changing workflow code, set profile-specific environment variables:

```powershell
$env:OPENROUTER_CONVERSION_STRICT_PRIMARY_MODEL = "openai/gpt-4o-mini"
$env:OPENROUTER_CONVERSION_STRICT_FALLBACK_MODEL = "openai/gpt-4o"
$env:OPENROUTER_CAPTIONING_VISION_PRIMARY_MODEL = "openai/gpt-4o-mini"
$env:OPENAI_RESEARCH_TOOLING_PRIMARY_MODEL = "gpt-5.4-mini"
```

The naming pattern is:

```text
<PROVIDER>_<ROUTING_PROFILE>_PRIMARY_MODEL
<PROVIDER>_<ROUTING_PROFILE>_FALLBACK_MODEL
```

Profile-specific environment overrides take precedence over the general browser/session model field, so production model changes can be made without editing Streamlit workspace code.

## Google Credentials

The app needs access to the reporting Google Sheet. Add the service account JSON to Streamlit secrets:

```toml
GOOGLE_CREDENTIALS = """
{ "type": "service_account", "project_id": "...", ... }
"""
```

The legacy `gcp_service_account` secret is still accepted for backward compatibility.

## Trust Controls In Contractor Conversion

The contractor workflow includes stronger controls than the earlier implementation:

- **Strict source-grounded mode**
  When enabled, AI is instructed to leave unsupported fields empty instead of inventing or expanding content.
- **Field locking**
  Lock `Date`, `Site_Name`, `District`, `Work_Executed`, `Comment_on_work`, or `challenges` before reconversion or refinement.
- **Change summaries**
  Refinements show compact field-level change summaries so updates do not happen silently.
- **Deterministic normalization**
  Whitespace, repeated punctuation, and obvious placeholder values are normalized without inventing data.

## Diagnostics And Usage Logging

AI-powered features write lightweight local usage events to:

- `ai_usage_log.jsonl`

Each event records only known values:

- timestamp
- feature name
- model
- provider
- routing profile
- resolved model
- whether fallback was used
- enabled plugin flags
- whether files were present
- whether images were present
- status

The diagnostics workspace also shows:

- recent usage events
- recent runtime issues
- safe maintenance actions
- maintenance backlog items

Persistent reusable AI guidance and runtime issue state are stored locally in:

- `ai_memory_store.json`

Both local store files are ignored by Git.

## Running The App

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run Streamlit:

```powershell
streamlit run app.py
```

For consistency on Windows, using the project virtual environment is preferred:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## FastAPI / Mobile Entry Point

The FastAPI service in `api.py` is still available for mobile or backend integration:

```powershell
uvicorn api:app --reload --port 8000
```

Shared behaviors remain intact:

- `/schema` exposes the same canonical `REPORT_HEADERS`
- report exports still use `report.py`
- mobile submissions still write to the same Google Sheet

## Testing

Run the test suite with:

```powershell
py -3.12 -m pytest -q
```

The refactor adds direct tests for:

- converter validation and field locking
- change summary behavior
- usage logging summaries
- routing profile resolution and fallback behavior
- non-sensitive provider/routing usage metadata
- existing AI helper flows
- OpenRouter provider routing through the shared AI service layer
- reporting/export compatibility

