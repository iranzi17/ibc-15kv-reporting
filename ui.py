import base64
from pathlib import Path
from typing import Optional

import streamlit as st


def set_background(image_path: str, overlay_opacity: float = 0.55):
    """Set a background image with optional white overlay for readability."""
    overlay_opacity = max(0.0, min(1.0, overlay_opacity))
    path = Path(__file__).parent / image_path
    if not path.exists():
        return
    encoded = base64.b64encode(path.read_bytes()).decode()
    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(255,255,255,{overlay_opacity}),
                                rgba(255,255,255,{overlay_opacity})),
                url("data:image/jpg;base64,{encoded}");
            background-size: cover;
            background-position: center center;
            background-attachment: fixed;
        }}
        [data-testid="stHeader"] {{
            background: rgba(0,0,0,0);
        }}
        .block-container {{
            background: rgba(255,255,255,0.85);
            border-radius: 14px;
            padding: 1.2rem 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            backdrop-filter: blur(2px);
        }}
        [data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,0.75);
            border-radius: 12px;
            margin: 0.5rem;
            padding: 0.5rem;
            backdrop-filter: blur(2px);
        }}
        .stButton>button {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        }}
        @media (max-width: 768px) {{
          .block-container {{ background: rgba(255,255,255,0.92); }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_workwatch_header(
    author: str = "IRANZI",
    brand: str = "WorkWatch",
    subtitle: str = "Site Intelligence",
    logo_path: Optional[str] = "ibc_logo.png",
    tagline: Optional[str] = "Field reports & weekly summaries",
):
    """Render the branded header used throughout the app."""
    logo_html = ""
    if logo_path:
        p = Path(__file__).parent / logo_path
        if p.exists():
            encoded = base64.b64encode(p.read_bytes()).decode()
            logo_html = f'<img class="ww-logo" src="data:image/png;base64,{encoded}" alt="logo"/>'

    discipline = st.session_state.get("discipline_radio")
    suffix = f' <span class="ww-suffix">— {discipline}</span>' if discipline else ""

    st.markdown(
        f"""
        <style>
        .ww-wrap {{
          display:flex; align-items:center; gap:14px; margin: .25rem 0 1rem 0;
        }}
        .ww-logo {{
          height: 46px; width:auto; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.12);
        }}
        .ww-title {{
          font-size: clamp(28px, 4vw, 44px);
          line-height: 1.05;
          font-weight: 800;
          margin: 0;
        }}
        .ww-brand {{
          background: linear-gradient(90deg,#111,#5a5a5a 60%,#111);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }}
        .ww-sub {{ opacity:.85; font-weight:700; }}
        .ww-dot {{ opacity:.6; font-weight:600; padding:0 .2rem; }}
        .ww-author {{ font-weight:500; opacity:.8; }}
        .ww-suffix {{ font-weight:500; opacity:.65; }}
        .ww-tagline {{ margin-top:.25rem; opacity:.75; font-size:0.95rem; }}
        </style>

        <div class="ww-wrap">
          {logo_html}
          <div>
            <div class="ww-title">
              ⚡ <span class="ww-brand">{brand}</span> — <span class="ww-sub">{subtitle}</span>
              <span class="ww-dot">·</span><span class="ww-author">{author}</span>{suffix}
            </div>
            {f'<div class="ww-tagline">{tagline}</div>' if tagline else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
