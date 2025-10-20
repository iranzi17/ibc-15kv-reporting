"""Hero section utilities for the WorkWatch Streamlit app."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

import streamlit as st

FiltersResult = Optional[Tuple[str, Iterable[str], Iterable[str]]]


def _resolve_image(image_path: str) -> Optional[str]:
    """Return a base64 data URI for the provided image path if it exists."""
    candidate_paths = [Path(image_path)]
    # Support relative lookups from this file's directory as well.
    candidate_paths.append(Path(__file__).parent / image_path)

    for path in candidate_paths:
        if path.exists() and path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode()
            suffix = path.suffix.lower()
            if suffix in {".jpg", ".jpeg"}:
                mime = "image/jpeg"
            elif suffix == ".png":
                mime = "image/png"
            elif suffix == ".webp":
                mime = "image/webp"
            else:
                mime = "image/jpeg"
            return f"data:{mime};base64,{encoded}"
    return None


def render_hero(
    title: str = "Smart Field Reporting for Electrical & Civil Works",
    subtitle: str = "A modern reporting system for engineers, supervisors and consultants.",
    cta_primary: str = "Generate Reports",
    cta_secondary: str = "Upload Site Data",
    image_path: str = "bg.jpg",
    filters_renderer: Optional[Callable[[], FiltersResult]] = None,
) -> FiltersResult:
    """Render the blue FormAssembly-style hero at the top of the page.

    Parameters
    ----------
    title, subtitle, cta_primary, cta_secondary, image_path
        Text and imagery shown in the left/right hero columns.
    filters_renderer
        Optional callback executed inside a tinted panel beneath the hero copy
        where Streamlit widgets (discipline/sites/dates) can live. The callback
        should return a tuple of values which will be surfaced back to the
        caller so the rest of the app can use the selections.
    """

    img_src = _resolve_image(image_path) or image_path

    st.markdown(
        """
        <style>
        /* ---- Global refinements ---- */
        .block-container { padding-top: 1.1rem; padding-bottom: 2.4rem; }

        /* ---- Hero container ---- */
        .hero-block {
            position: relative;
            width: 100%;
            margin: 0 auto 1.6rem auto;
            background: linear-gradient(135deg, #0a66c2 0%, #1b86f9 100%);
            border-radius: 24px;
            padding: clamp(28px, 4vw, 52px) clamp(22px, 6vw, 48px);
            box-shadow: 0 16px 42px rgba(11, 81, 156, 0.28);
            overflow: hidden;
        }

        .hero-block .stColumn {
            align-self: center;
        }

        .hero-copy h1 {
            color: #ffffff;
            font-weight: 800;
            letter-spacing: -0.3px;
            line-height: 1.1;
            font-size: clamp(32px, 3.1vw, 46px);
            margin-bottom: 0.65rem;
        }

        .hero-copy p {
            color: rgba(255,255,255,0.92);
            font-size: clamp(15px, 1.3vw, 18px);
            line-height: 1.6;
            margin-bottom: 1.4rem;
        }

        .hero-cta {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }
        .hero-cta button {
            border-radius: 12px;
            font-weight: 700;
            padding: 12px 20px;
            cursor: pointer;
            border: none;
            transition: transform .08s ease, box-shadow .18s ease, background .18s ease;
        }
        .hero-cta .btn-primary {
            background: #ffffff;
            color: #0a66c2;
            box-shadow: 0 8px 22px rgba(0,0,0,0.18);
        }
        .hero-cta .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 28px rgba(0,0,0,0.2);
        }
        .hero-cta .btn-outline {
            background: rgba(10, 102, 194, 0.15);
            color: #ffffff;
            border: 2px solid rgba(255,255,255,0.86);
            box-shadow: 0 8px 22px rgba(0,0,0,0.12);
        }
        .hero-cta .btn-outline:hover {
            background: rgba(255,255,255,0.18);
            transform: translateY(-1px);
        }

        .hero-media-wrapper {
            width: 100%;
            background: rgba(255,255,255,0.96);
            border-radius: 22px;
            padding: 12px;
            box-shadow: 0 20px 44px rgba(0,0,0,0.26);
        }
        .hero-media-wrapper img {
            width: 100%;
            height: auto;
            border-radius: 16px;
            display: block;
        }

        .hero-filters {
            margin-top: clamp(18px, 3vw, 28px);
            background: rgba(255,255,255,0.14);
            border-radius: 18px;
            padding: clamp(18px, 3vw, 28px);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.24);
        }

        .hero-filters .hero-field-label {
            color: rgba(255,255,255,0.92);
            font-size: 0.92rem;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }

        .hero-filters [data-testid="stRadio"] > div[role="radiogroup"] > label {
            background: rgba(255,255,255,0.12);
            color: #ffffff;
            border-radius: 10px;
            padding: 10px 14px;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .hero-filters [data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
            background: rgba(255,255,255,0.22);
        }

        .hero-filters [data-testid="stRadio"] svg {
            fill: rgba(255,255,255,0.8);
        }

        .hero-filters div[data-baseweb="select"] {
            background: rgba(255,255,255,0.92);
            border-radius: 12px !important;
            box-shadow: 0 6px 18px rgba(15, 70, 135, 0.2);
        }
        .hero-filters div[data-baseweb="select"] input {
            color: #0a356c !important;
        }
        .hero-filters div[data-baseweb="select"] div[aria-selected="true"] {
            background: #0a66c2;
            color: #ffffff;
        }

        .hero-filters .stMultiSelect {
            color: #0a356c;
        }

        .hero-filters .stMultiSelect span[data-baseweb="tag"] {
            background: #f44336;
            color: #ffffff;
            border-radius: 8px;
        }

        .hero-filters .stMultiSelect span[data-baseweb="tag"] svg {
            fill: #ffffff;
        }

        .hero-filters .stVerticalBlock {
            gap: 0.4rem;
        }

        .hero-filters .stColumn {
            padding-bottom: 0 !important;
        }

        .hero-filters .stSelectbox > label,
        .hero-filters .stMultiSelect > label,
        .hero-filters [data-testid="stRadio"] > label {
            display: none;
        }

        @media (max-width: 1100px) {
            .hero-cta { justify-content: flex-start; }
        }

        @media (max-width: 900px) {
            .hero-block {
                padding: clamp(24px, 6vw, 42px) clamp(18px, 6vw, 32px);
            }
            .hero-filters .stColumns {
                flex-direction: column;
            }
        }

        body, .stApp { background: #ffffff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    filters_values: FiltersResult = None
    hero_container = st.container()
    with hero_container:
        st.markdown('<div class="hero-marker"></div>', unsafe_allow_html=True)
        left, right = st.columns((1.08, 1), gap="large")
        with left:
            st.markdown(
                f"""
                <div class="hero-copy">
                  <h1>{title}</h1>
                  <p>{subtitle}</p>
                  <div class="hero-cta">
                    <button class="btn-primary" data-action="generate">{cta_primary}</button>
                    <button class="btn-outline" data-action="upload">{cta_secondary}</button>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right:
            st.markdown(
                f"""
                <div class="hero-media-wrapper">
                  <img src="{img_src}" alt="Preview" />
                </div>
                """,
                unsafe_allow_html=True,
            )

        if filters_renderer is not None:
            filters_container = st.container()
            with filters_container:
                st.markdown('<div class="hero-filters-marker"></div>', unsafe_allow_html=True)
                filters_values = filters_renderer()

    st.markdown(
        """
        <script>
        (function attachHeroEnhancements(){
            const doc = (window.parent && window.parent !== window)
                ? window.parent.document
                : window.document;
            const ensureBound = () => {
                const actionMap = { generate: 'reports-section', upload: 'upload-section' };
                doc.querySelectorAll('.hero-cta [data-action]').forEach((btn) => {
                    if (btn.dataset.heroBound === 'true') return;
                    btn.dataset.heroBound = 'true';
                    btn.addEventListener('click', () => {
                        const targetId = actionMap[btn.dataset.action];
                        if (!targetId) return;
                        const el = doc.getElementById(targetId);
                        if (el && typeof el.scrollIntoView === 'function') {
                            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                    });
                });

                doc.querySelectorAll('.hero-marker').forEach((marker) => {
                    const block = marker.closest('[data-testid="stVerticalBlock"]');
                    if (block && !block.classList.contains('hero-block')) {
                        block.classList.add('hero-block');
                    }
                    marker.remove();
                });

                doc.querySelectorAll('.hero-filters-marker').forEach((marker) => {
                    const block = marker.closest('[data-testid="stVerticalBlock"]');
                    if (block && !block.classList.contains('hero-filters')) {
                        block.classList.add('hero-filters');
                    }
                    marker.remove();
                });
            };

            if (doc.readyState === 'complete') {
                ensureBound();
            } else {
                doc.addEventListener('DOMContentLoaded', ensureBound, { once: true });
                window.addEventListener('load', ensureBound, { once: true });
            }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    return filters_values
