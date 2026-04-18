from __future__ import annotations

import html
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET

import streamlit as st

from streamlit_ui.helpers import (
    safe_columns,
    safe_container,
    safe_markdown,
    safe_toggle,
)

DEFAULT_LIVE_UPDATE_TOPICS = ("infrastructure", "energy", "engineering", "weather", "safety")
LIVE_UPDATES_TOGGLE_KEY = "reporting_show_live_updates"
LIVE_UPDATES_CACHE_KEY = "_reporting_live_updates_cache"


def _streamlit_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default) or "").strip()
    except Exception:
        return str(default or "").strip()


def _env_or_secret(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return _streamlit_secret(name, default)


def _bool_setting(name: str, default: bool = False) -> bool:
    value = _env_or_secret(name, "")
    if not value:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_setting(name: str, default: float) -> float:
    value = _env_or_secret(name, "")
    if not value:
        return float(default)
    try:
        return max(0.5, float(value))
    except ValueError:
        return float(default)


def _int_setting(name: str, default: int) -> int:
    value = _env_or_secret(name, "")
    if not value:
        return int(default)
    try:
        return max(1, int(value))
    except ValueError:
        return int(default)


def parse_updates_items(value: object) -> list[dict[str, str]]:
    """Normalize static update configuration into title/context dictionaries."""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                return parse_updates_items(json.loads(raw))
            except json.JSONDecodeError:
                pass
        pieces = [segment.strip() for segment in raw.replace("|", "\n").splitlines()]
        return [{"title": item, "context": ""} for item in pieces if item]

    normalized: list[dict[str, str]] = []
    if not isinstance(value, list):
        return normalized

    for item in value:
        if isinstance(item, str):
            title = item.strip()
            if title:
                normalized.append({"title": title, "context": ""})
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        context = str(item.get("context", "") or item.get("source", "") or item.get("topic", "") or "").strip()
        normalized.append({"title": title, "context": context})
    return normalized


def load_live_updates_config() -> dict[str, object]:
    """Read optional live-updates configuration from env or Streamlit secrets."""
    static_items = parse_updates_items(_env_or_secret("REPORTING_LIVE_UPDATES_ITEMS", ""))
    topics_raw = _env_or_secret("REPORTING_LIVE_UPDATES_TOPICS", "")
    if topics_raw:
        topics = tuple(topic.strip().lower() for topic in topics_raw.split(",") if topic.strip())
    else:
        topics = DEFAULT_LIVE_UPDATE_TOPICS

    return {
        "label": _env_or_secret("REPORTING_LIVE_UPDATES_LABEL", "Live updates") or "Live updates",
        "feed_url": _env_or_secret("REPORTING_LIVE_UPDATES_FEED_URL", ""),
        "topics": tuple(topics),
        "timeout_seconds": _float_setting("REPORTING_LIVE_UPDATES_TIMEOUT_SECONDS", 2.0),
        "cache_ttl_seconds": _int_setting("REPORTING_LIVE_UPDATES_CACHE_TTL_SECONDS", 300),
        "max_items": _int_setting("REPORTING_LIVE_UPDATES_MAX_ITEMS", 5),
        "enabled_by_default": _bool_setting("REPORTING_LIVE_UPDATES_ENABLED_BY_DEFAULT", False),
        "static_items": static_items,
    }


def _local_name(tag: object) -> str:
    value = str(tag or "")
    return value.rsplit("}", 1)[-1].lower()


def _first_child_text(node: ET.Element, allowed_names: tuple[str, ...]) -> str:
    for child in list(node):
        if _local_name(child.tag) not in allowed_names:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return " ".join(text.split())
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in list(node):
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "") or "").strip()
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _entry_categories(node: ET.Element) -> list[str]:
    categories: list[str] = []
    for child in list(node):
        if _local_name(child.tag) != "category":
            continue
        term = str(child.attrib.get("term", "") or "").strip()
        if term:
            categories.append(term)
            continue
        text = "".join(child.itertext()).strip()
        if text:
            categories.append(text)
    return categories


def _entry_matches_topics(title: str, summary: str, categories: list[str], topics: tuple[str, ...]) -> bool:
    if not topics:
        return True
    searchable = " ".join([title, summary, " ".join(categories)]).lower()
    return any(topic in searchable for topic in topics)


def fetch_feed_updates(feed_url: str, *, topics: tuple[str, ...], timeout_seconds: float, max_items: int) -> list[dict[str, str]]:
    """Fetch a small set of RSS or Atom items and filter them to sector-relevant topics."""
    request = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "IBCReportingPlatform/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()

    root = ET.fromstring(payload)
    items: list[dict[str, str]] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"item", "entry"}:
            continue
        title = _first_child_text(node, ("title",))
        summary = _first_child_text(node, ("description", "summary", "content"))
        categories = _entry_categories(node)
        if not title or not _entry_matches_topics(title, summary, categories, topics):
            continue
        context = categories[0] if categories else ""
        items.append(
            {
                "title": title,
                "context": context,
                "link": _entry_link(node),
            }
        )
        if len(items) >= max_items:
            break
    return items


def load_live_updates_items(config: dict[str, object]) -> list[dict[str, str]]:
    """Return live updates from static config or an optional feed."""
    static_items = parse_updates_items(config.get("static_items", []))
    if static_items:
        return static_items[: int(config.get("max_items", 5) or 5)]

    feed_url = str(config.get("feed_url", "") or "").strip()
    if not feed_url:
        return []

    cache_key = "|".join(
        [
            feed_url,
            ",".join(tuple(config.get("topics", DEFAULT_LIVE_UPDATE_TOPICS))),
            str(int(config.get("max_items", 5) or 5)),
        ]
    )
    cache = st.session_state.setdefault(LIVE_UPDATES_CACHE_KEY, {})
    if isinstance(cache, dict):
        cached = cache.get(cache_key, {})
        loaded_at = float(cached.get("loaded_at", 0) or 0) if isinstance(cached, dict) else 0
        cached_items = cached.get("items", []) if isinstance(cached, dict) else []
        if (
            isinstance(cached_items, list)
            and cached_items
            and (time.time() - loaded_at) < int(config.get("cache_ttl_seconds", 300) or 300)
        ):
            return cached_items

    try:
        items = fetch_feed_updates(
            feed_url,
            topics=tuple(config.get("topics", DEFAULT_LIVE_UPDATE_TOPICS)),
            timeout_seconds=float(config.get("timeout_seconds", 2.0) or 2.0),
            max_items=int(config.get("max_items", 5) or 5),
        )
    except Exception:
        return []
    if isinstance(cache, dict):
        cache[cache_key] = {"loaded_at": time.time(), "items": items}
        st.session_state[LIVE_UPDATES_CACHE_KEY] = cache
    return items


def render_live_updates_shell() -> None:
    """Render an optional, visually secondary live-updates companion bar."""
    config = load_live_updates_config()
    toggle_default = bool(st.session_state.get(LIVE_UPDATES_TOGGLE_KEY, config.get("enabled_by_default", False)))
    with safe_container(border=False):
        info_column, toggle_column = safe_columns((1.6, 0.7), gap="small")
        with info_column:
            safe_markdown(
                """
                <div class="ops-live-shell">
                  <div class="ops-live-shell-label">Sector updates</div>
                  <div class="ops-live-shell-text">
                    Optional companion updates for infrastructure, energy, engineering, weather, and safety.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with toggle_column:
            show_updates = safe_toggle(
                "Show live updates",
                value=toggle_default,
                key=LIVE_UPDATES_TOGGLE_KEY,
                help="Display a lightweight sector-focused updates strip without affecting reporting workflows.",
            )

    if not show_updates:
        return

    label = html.escape(str(config.get("label", "Live updates") or "Live updates"))
    items = load_live_updates_items(config)
    if not items:
        safe_markdown(
            f"""
            <div class="ops-live-bar ops-live-bar--quiet">
              <span class="ops-live-bar-label">{label}</span>
              <span class="ops-live-bar-empty">News unavailable</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    item_markup: list[str] = []
    for item in items:
        title = html.escape(str(item.get("title", "") or "").strip())
        if not title:
            continue
        context = html.escape(str(item.get("context", "") or "").strip())
        context_markup = f'<span class="ops-live-bar-context">{context}</span>' if context else ""
        item_markup.append(
            f"""
            <span class="ops-live-bar-item">
              <span class="ops-live-bar-title">{title}</span>
              {context_markup}
            </span>
            """
        )

    if not item_markup:
        safe_markdown(
            f"""
            <div class="ops-live-bar ops-live-bar--quiet">
              <span class="ops-live-bar-label">{label}</span>
              <span class="ops-live-bar-empty">News unavailable</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    safe_markdown(
        f"""
        <div class="ops-live-bar">
          <span class="ops-live-bar-label">{label}</span>
          <div class="ops-live-bar-track">{"".join(item_markup)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
