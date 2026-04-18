from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st


def set_background(image_path: str, overlay_opacity: float = 0.0):
    """Legacy no-op background helper kept for compatibility."""
    candidate = Path(__file__).parent / image_path
    if candidate.exists():
        st.markdown(
            """
            <style>
            [data-testid="stAppViewContainer"], .stApp {
                background: #f4f6f8;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def render_workwatch_header(
    author: str = "IRANZI",
    brand: str = "IBC Reporting",
    subtitle: str = "Operational Reporting",
    logo_path: Optional[str] = "ibc_logo.png",
    tagline: Optional[str] = "Daily site supervision, contractor conversion, and report generation",
):
    """Render a restrained legacy header for compatibility with older entry points."""
    logo_html = ""
    if logo_path:
        candidate = Path(__file__).parent / logo_path
        if candidate.exists():
            logo_html = f'<img src="{candidate.as_posix()}" alt="logo" style="height:34px;width:auto;" />'

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;padding:0.8rem 0 0.4rem 0;">
          {logo_html}
          <div>
            <div style="font-size:1.35rem;font-weight:700;color:#17212b;">{brand}</div>
            <div style="font-size:0.9rem;color:#5d6b79;">{subtitle} | {author}</div>
            {f'<div style="font-size:0.86rem;color:#6c7884;">{tagline}</div>' if tagline else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

