from __future__ import annotations

import streamlit as st


def render_hero(
    title: str = "IBC Reporting Platform",
    subtitle: str = "Operational reporting workspace for engineers, supervisors, consultants, and controls staff.",
    cta_primary: str = "",
    cta_secondary: str = "",
    image_path: str = "",
) -> None:
    """Legacy placeholder kept for compatibility with older imports."""
    st.markdown(
        f"""
        <div style="background:#ffffff;border:1px solid #d7dde5;border-radius:12px;padding:1rem 1.2rem;margin-bottom:1rem;">
          <div style="font-size:1.6rem;font-weight:700;color:#17212b;">{title}</div>
          <div style="font-size:0.95rem;color:#5d6b79;line-height:1.5;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

