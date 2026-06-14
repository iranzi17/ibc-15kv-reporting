# IBC 15kV Reporting Platform

A Streamlit-based reporting workspace for infrastructure site supervision, contractor-to-consultant report conversion, Google Sheets review, site-photo handling, and final DOCX/ZIP report generation.

## Overview

This project supports daily reporting for engineering and utility-infrastructure supervision. It was designed around real project workflows where field information must be reviewed, cleaned, converted into consultant-ready records, linked with site photos, and exported into structured reports.

The platform combines reporting automation, spreadsheet review, document generation, and optional AI-assisted conversion tools while preserving a controlled engineering-reporting workflow.

## Problem addressed

Infrastructure supervision teams often receive site information from multiple sources, including contractor notes, field photos, spreadsheets, voice notes, and daily activity descriptions. Without a controlled workflow, reports become inconsistent, difficult to validate, and time-consuming to prepare.

This platform helps convert raw field information into structured reporting records and final deliverables.

## Target users

- site engineers
- supervisors
- consultants
- reporting staff
- project-control teams
- infrastructure and utility project teams

## Main workspaces

### 1. Reporting Workspace

- filter reports by discipline, site, and date
- review and edit rows from Google Sheets
- attach or paste site photos by site/date pair
- generate final ZIP exports using the canonical report engine

### 2. Contractor Conversion

- paste contractor text
- attach source documents, images, and audio
- convert contractor notes into consultant-ready rows
- refine records using strict source-grounded controls
- lock selected fields before refinement
- append approved rows to Google Sheets

### 3. Advanced AI Tools

- shared project-reference uploads
- reusable AI guidance
- research assistant
- spreadsheet analyst
- optional secondary assistant

### 4. System Diagnostics and Maintenance

- runtime issue history
- AI provider usage log
- safe maintenance actions
- maintenance backlog

## Canonical modules

These modules remain the core sources of truth:

- `report.py` — DOCX generation, gallery composition, signatories, captions, and ZIP export
- `report_structuring.py` — canonical report headers, parser, and alias resolution
- `sheets.py` — Google Sheets access, append operations, and offline cache helpers
- `config.py` — application configuration and environment/file overrides
- `api.py` — FastAPI/mobile/backend interface using the same report and schema assumptions

## Architecture

The previous single-file app structure was refactored into clearer layers:

- `app.py` — thin Streamlit orchestrator and compatibility surface
- `core/session_state.py` — session-state keys, persistent AI memory, runtime issue store, reset helpers
- `services/openai_client.py` — provider selection, key/model loading, SDK checks, and assistant requests
- `services/model_routing.py` — task-based routing profiles, provider-aware model defaults, fallback models, and plugin policy
- `services/converter_service.py` — contractor conversion, refinement, normalization, validation, locking, and change summaries
- `services/media_service.py` — file/input helpers, transcription, image captioning, and text-to-speech
- `services/research_service.py` — research assistant, tool routing, file search, and spreadsheet analysis
- `services/self_healing_service.py` — maintenance analysis helper
- `services/usage_logging.py` — lightweight JSONL usage log for AI-powered actions
- `streamlit_ui/` — reusable UI components and workspace screens

## Trust controls

The contractor workflow includes safeguards for source-grounded reporting:

- **Strict source-grounded mode** — unsupported fields remain empty instead of being invented
- **Field locking** — selected fields can be locked before reconversion or refinement
- **Change summaries** — refinements show compact field-level changes
- **Deterministic normalization** — formatting is cleaned without inventing missing information

## Configuration

The app can connect to Google Sheets using service-account credentials stored in Streamlit secrets or environment configuration. AI-assisted tools support provider configuration through environment variables and session-level settings.

## Skills demonstrated

- Streamlit application development
- engineering-report automation
- Google Sheets integration
- DOCX and ZIP report generation
- infrastructure project data workflows
- AI-assisted but source-controlled text conversion
- Python modularization and service-layer refactoring
- practical tool-building for utility and construction supervision

## Professional relevance

This is the strongest portfolio project in my GitHub because it connects software automation with real infrastructure supervision work. It demonstrates the ability to build practical tools for engineering teams, consultants, and utility-project workflows where data quality, reporting speed, and traceability matter.
