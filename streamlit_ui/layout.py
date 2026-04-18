from __future__ import annotations

from typing import Iterable

from streamlit_ui.helpers import safe_markdown


def render_section_header(title: str, subtitle: str = "") -> None:
    """Render a professional section header."""
    safe_markdown(f'<div class="ops-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        safe_markdown(
            f'<div class="ops-section-subtitle">{subtitle}</div>',
            unsafe_allow_html=True,
        )


def render_subsection(title: str, subtitle: str = "") -> None:
    """Render a subsection shell title."""
    safe_markdown(
        f"""
        <div class="ops-subsection">
          <h4>{title}</h4>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_note(text: str) -> None:
    """Render a muted operational note."""
    if not text:
        return
    safe_markdown(f'<div class="ops-note">{text}</div>', unsafe_allow_html=True)


def render_kpi_strip(items: Iterable[tuple[str, object]]) -> None:
    """Render a simple KPI strip for diagnostics or workflow counts."""
    cards = []
    for label, value in items:
        cards.append(
            f"""
            <div class="ops-kpi">
              <div class="ops-kpi-label">{label}</div>
              <div class="ops-kpi-value">{value}</div>
            </div>
            """
        )
    if cards:
        safe_markdown(f'<div class="ops-kpi-strip">{"".join(cards)}</div>', unsafe_allow_html=True)

