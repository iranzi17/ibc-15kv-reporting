from __future__ import annotations

import streamlit as st

from streamlit_ui.helpers import safe_markdown


def apply_professional_theme() -> None:
    """Apply a restrained reporting-focused theme."""
    safe_markdown(
        """
        <style>
        :root {
            --app-bg: #f4f6f8;
            --panel-bg: #ffffff;
            --panel-border: #d7dde5;
            --ink: #17212b;
            --muted: #5d6b79;
            --accent: #24405a;
            --accent-soft: #eef3f7;
            --success-soft: #edf7f1;
            --warning-soft: #fff6e8;
            --danger-soft: #fff0ef;
        }

        html, body, [data-testid="stAppViewContainer"], .stApp {
            background: var(--app-bg);
            color: var(--ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2.2rem;
            max-width: 1320px;
        }

        [data-testid="stSidebar"] > div:first-child {
            background: #eef2f5;
            border-right: 1px solid var(--panel-border);
        }

        div[data-testid="stVerticalBlock"] > div:has(> .ops-section-title) {
            margin-top: 0;
        }

        .ops-page-header {
            background: linear-gradient(180deg, #ffffff 0%, #f7f9fb 100%);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.1rem 1.25rem;
            margin-bottom: 1rem;
        }

        .ops-page-title {
            font-size: 1.8rem;
            font-weight: 700;
            margin: 0 0 0.25rem 0;
            color: var(--ink);
            letter-spacing: -0.02em;
        }

        .ops-page-subtitle {
            margin: 0;
            color: var(--muted);
            font-size: 0.97rem;
            line-height: 1.55;
        }

        .ops-section-title {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--ink);
            margin: 1.4rem 0 0.15rem 0;
        }

        .ops-section-subtitle {
            color: var(--muted);
            margin: 0 0 0.9rem 0;
            line-height: 1.5;
        }

        .ops-subsection {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 0.9rem 1rem 1rem 1rem;
            margin: 0.85rem 0;
        }

        .ops-subsection h4 {
            margin: 0 0 0.25rem 0;
            font-size: 1rem;
            color: var(--accent);
        }

        .ops-subsection p {
            margin: 0;
            color: var(--muted);
            line-height: 1.45;
            font-size: 0.92rem;
        }

        div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            background: #fff;
        }

        .stButton > button {
            border-radius: 8px;
            border: 1px solid #aeb7c2;
            background: #ffffff;
            color: var(--ink);
            font-weight: 600;
            box-shadow: none;
        }

        .stDownloadButton > button {
            border-radius: 8px;
        }

        .ops-note {
            background: var(--accent-soft);
            border-left: 4px solid var(--accent);
            border-radius: 8px;
            padding: 0.7rem 0.85rem;
            color: var(--ink);
            margin: 0.75rem 0;
            font-size: 0.93rem;
        }

        .ops-kpi-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.75rem;
            margin: 0.85rem 0 1rem 0;
        }

        .ops-kpi {
            background: #fff;
            border: 1px solid var(--panel-border);
            border-radius: 10px;
            padding: 0.75rem 0.85rem;
        }

        .ops-kpi-label {
            color: var(--muted);
            font-size: 0.8rem;
            margin-bottom: 0.2rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .ops-kpi-value {
            color: var(--ink);
            font-size: 1.25rem;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    """Render a restrained product header."""
    safe_markdown(
        """
        <div class="ops-page-header">
          <div class="ops-page-title">IBC Reporting Platform</div>
          <p class="ops-page-subtitle">
            Daily site reporting, contractor conversion, report generation, and operational diagnostics.
            AI features are available where they support the workflow, but the reporting process remains the primary product path.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

