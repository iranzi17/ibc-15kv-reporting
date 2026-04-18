from __future__ import annotations

from streamlit_ui.helpers import safe_markdown


def apply_professional_theme() -> None:
    """Apply a restrained enterprise theme for operational reporting workflows."""
    safe_markdown(
        """
        <style>
        :root {
            --app-bg: #f3f5f7;
            --panel-bg: #ffffff;
            --panel-bg-soft: #f8fafb;
            --panel-border: #d7dfe7;
            --panel-border-strong: #c4cfdb;
            --ink: #15202b;
            --muted: #66788a;
            --accent: #1f4e6d;
            --accent-soft: #eaf2f7;
            --success-soft: #edf6ef;
            --warning-soft: #fff7e8;
            --danger-soft: #fff1ef;
            --radius-sm: 10px;
            --radius-md: 14px;
            --radius-lg: 18px;
            --shadow-soft: 0 10px 30px rgba(18, 32, 45, 0.05);
            --shadow-card: 0 4px 16px rgba(18, 32, 45, 0.04);
        }

        html, body, [data-testid="stAppViewContainer"], .stApp {
            background: var(--app-bg);
            color: var(--ink);
            font-family: "Aptos", "Segoe UI", sans-serif;
        }

        [data-testid="stHeader"] {
            background: rgba(243, 245, 247, 0.92);
            border-bottom: 1px solid rgba(21, 32, 43, 0.05);
            backdrop-filter: blur(6px);
        }

        .block-container {
            max-width: 1240px;
            padding-top: 1rem;
            padding-bottom: 2.5rem;
        }

        [data-testid="stSidebar"] > div:first-child {
            background: #f7f9fb;
            border-right: 1px solid var(--panel-border);
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--ink);
            letter-spacing: -0.02em;
        }

        p, label, span {
            color: inherit;
        }

        .ops-page-header,
        .ops-workspace-topbar {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-soft);
        }

        .ops-page-header {
            padding: 1rem 1.15rem 1.05rem 1.15rem;
            margin-bottom: 1rem;
        }

        .ops-page-eyebrow {
            display: inline-flex;
            align-items: center;
            padding: 0.32rem 0.68rem;
            border-radius: 999px;
            background: var(--accent-soft);
            color: var(--accent);
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.65rem;
        }

        .ops-page-title {
            font-size: 1.7rem;
            font-weight: 700;
            margin: 0 0 0.28rem 0;
            color: var(--ink);
        }

        .ops-page-subtitle {
            max-width: 72ch;
            margin: 0;
            color: var(--muted);
            font-size: 0.96rem;
            line-height: 1.55;
        }

        .ops-workspace-topbar {
            padding: 1rem 1.1rem;
            margin: 0.2rem 0 0.9rem 0;
        }

        .ops-topbar-row,
        .ops-card-header-row {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.9rem;
            flex-wrap: wrap;
        }

        .ops-topbar-copy,
        .ops-card-copy {
            display: flex;
            flex-direction: column;
            gap: 0.3rem;
            min-width: 0;
        }

        .ops-topbar-title {
            font-size: 1.4rem;
            font-weight: 700;
            line-height: 1.15;
            color: var(--ink);
        }

        .ops-topbar-subtitle {
            color: var(--muted);
            line-height: 1.5;
            max-width: 70ch;
            font-size: 0.95rem;
        }

        .ops-topbar-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            justify-content: flex-end;
        }

        .ops-topbar-meta-item {
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            background: var(--panel-bg-soft);
            border: 1px solid var(--panel-border);
            color: var(--muted);
            font-size: 0.8rem;
            font-weight: 600;
        }

        .ops-section-title {
            font-size: 1.22rem;
            font-weight: 700;
            color: var(--ink);
            margin: 1.35rem 0 0.15rem 0;
        }

        .ops-section-subtitle {
            color: var(--muted);
            margin: 0 0 0.85rem 0;
            line-height: 1.5;
        }

        .ops-subsection {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            padding: 0.85rem 0.95rem 0.95rem 0.95rem;
            margin: 0.8rem 0;
        }

        .ops-subsection h4 {
            margin: 0 0 0.24rem 0;
            font-size: 1rem;
            color: var(--accent);
        }

        .ops-subsection p {
            margin: 0;
            color: var(--muted);
            line-height: 1.45;
            font-size: 0.92rem;
        }

        .ops-card-header {
            margin-bottom: 0.85rem;
        }

        .ops-card-step {
            color: var(--muted);
            font-size: 0.76rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .ops-card-title {
            font-size: 1.08rem;
            font-weight: 700;
            color: var(--ink);
        }

        .ops-card-subtitle {
            color: var(--muted);
            line-height: 1.5;
            font-size: 0.92rem;
            max-width: 72ch;
        }

        .ops-badge {
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            padding: 0.34rem 0.72rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            white-space: nowrap;
        }

        .ops-badge--neutral {
            background: var(--accent-soft);
            color: var(--accent);
        }

        .ops-badge--quiet {
            background: var(--panel-bg-soft);
            border: 1px solid var(--panel-border);
            color: var(--muted);
        }

        .ops-status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.15rem 0 0.85rem 0;
        }

        .ops-status-pill {
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            border: 1px solid transparent;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .ops-status-pill--neutral {
            background: var(--panel-bg-soft);
            border-color: var(--panel-border);
            color: var(--muted);
        }

        .ops-status-pill--success {
            background: var(--success-soft);
            color: #295a3b;
        }

        .ops-status-pill--warning {
            background: var(--warning-soft);
            color: #8a5a12;
        }

        .ops-status-pill--danger {
            background: var(--danger-soft);
            color: #9b3a31;
        }

        .ops-note {
            background: var(--accent-soft);
            border: 1px solid rgba(31, 78, 109, 0.12);
            border-left: 4px solid var(--accent);
            border-radius: var(--radius-md);
            padding: 0.78rem 0.9rem;
            color: var(--ink);
            margin: 0.75rem 0;
            font-size: 0.92rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-card);
        }

        div[data-testid="stMetric"] {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            padding: 0.9rem 1rem;
            box-shadow: var(--shadow-card);
        }

        div[data-testid="stMetricLabel"] {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.74rem;
            font-weight: 700;
        }

        div[data-testid="stMetricValue"] {
            color: var(--ink);
            font-size: 1.55rem;
            font-weight: 700;
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            background: var(--panel-bg);
        }

        div[data-baseweb="select"] > div,
        div[data-testid="stTextInputRootElement"] > div,
        div[data-testid="stTextAreaRootElement"] > div,
        div[data-testid="stNumberInput"] > div {
            border-radius: 12px;
            border-color: var(--panel-border);
            background: var(--panel-bg);
            box-shadow: none;
        }

        div[data-testid="stMultiSelect"] label,
        div[data-testid="stRadio"] label,
        div[data-testid="stSlider"] label,
        div[data-testid="stCheckbox"] label {
            font-size: 0.84rem;
            font-weight: 600;
            color: var(--muted);
        }

        div[role="radiogroup"] {
            gap: 0.55rem;
        }

        div[role="radiogroup"] > label {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 999px;
            padding: 0.3rem 0.72rem;
        }

        details {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
        }

        summary {
            padding-top: 0.15rem;
            padding-bottom: 0.15rem;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 12px;
            min-height: 2.85rem;
            border: 1px solid var(--panel-border-strong);
            background: var(--panel-bg);
            color: var(--ink);
            font-weight: 600;
            box-shadow: none;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--accent);
            color: var(--accent);
        }

        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
            color: #ffffff;
        }

        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover {
            background: #173f57;
            border-color: #173f57;
            color: #ffffff;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-top: 0.8rem;
            }

            .ops-page-title {
                font-size: 1.45rem;
            }

            .ops-topbar-title {
                font-size: 1.18rem;
            }
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
          <div class="ops-page-eyebrow">Engineering Operations</div>
          <div class="ops-page-title">IBC Reporting Platform</div>
          <p class="ops-page-subtitle">
            Daily site reporting, consultant review, photo tracking, and final report export in one operational workspace.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
