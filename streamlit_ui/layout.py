from __future__ import annotations

from typing import Iterable

from streamlit_ui.helpers import (
    safe_caption,
    safe_columns,
    safe_container,
    safe_markdown,
    safe_metric,
)


def render_section_header(title: str, subtitle: str = "") -> None:
    """Render a professional section header."""
    safe_markdown(f'<div class="ops-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        safe_markdown(
            f'<div class="ops-section-subtitle">{subtitle}</div>',
            unsafe_allow_html=True,
        )


def render_workspace_topbar(
    title: str,
    subtitle: str = "",
    *,
    badge: str = "",
    meta: Iterable[str] | None = None,
) -> None:
    """Render a restrained operational top bar for key workspaces."""
    meta_items = [
        f'<span class="ops-topbar-meta-item">{item}</span>'
        for item in (str(value).strip() for value in (meta or []))
        if item
    ]
    badge_markup = f'<span class="ops-badge ops-badge--neutral">{badge}</span>' if badge else ""
    safe_markdown(
        f"""
        <div class="ops-workspace-topbar">
          <div class="ops-topbar-row">
            <div class="ops-topbar-copy">
              {badge_markup}
              <div class="ops-topbar-title">{title}</div>
              <div class="ops-topbar-subtitle">{subtitle}</div>
            </div>
            <div class="ops-topbar-meta">{"".join(meta_items)}</div>
          </div>
        </div>
        """,
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


def render_card_header(step: str, title: str, subtitle: str = "", *, badge: str = "") -> None:
    """Render a compact workflow-card header."""
    badge_markup = f'<span class="ops-badge ops-badge--quiet">{badge}</span>' if badge else ""
    safe_markdown(
        f"""
        <div class="ops-card-header">
          <div class="ops-card-header-row">
            <div class="ops-card-copy">
              <div class="ops-card-step">{step}</div>
              <div class="ops-card-title">{title}</div>
              <div class="ops-card-subtitle">{subtitle}</div>
            </div>
            {badge_markup}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badges(items: Iterable[str | tuple[str, str]]) -> None:
    """Render small status pills for workflow and readiness states."""
    badges: list[str] = []
    for item in items:
        if isinstance(item, tuple):
            text = str(item[0] or "").strip()
            tone = str(item[1] or "neutral").strip().lower()
        else:
            text = str(item or "").strip()
            tone = "neutral"
        if not text:
            continue
        if tone not in {"neutral", "success", "warning", "danger"}:
            tone = "neutral"
        badges.append(f'<span class="ops-status-pill ops-status-pill--{tone}">{text}</span>')
    if badges:
        safe_markdown(f'<div class="ops-status-row">{"".join(badges)}</div>', unsafe_allow_html=True)


def render_note(text: str) -> None:
    """Render a muted operational note."""
    if not text:
        return
    safe_markdown(f'<div class="ops-note">{text}</div>', unsafe_allow_html=True)


def render_kpi_strip(items: Iterable[tuple[str, object] | tuple[str, object, str]]) -> None:
    """Render KPI cards using native Streamlit metrics."""
    normalized_items: list[tuple[str, object, str]] = []
    for item in items:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        label = str(item[0] or "").strip()
        if not label:
            continue
        value = item[1]
        caption = str(item[2] or "").strip() if len(item) > 2 else ""
        normalized_items.append((label, value, caption))

    if not normalized_items:
        return

    columns = safe_columns(len(normalized_items), gap="small")
    for column, (label, value, caption) in zip(columns, normalized_items):
        with column:
            with safe_container(border=True):
                safe_metric(label, value)
                if caption:
                    safe_caption(caption)
