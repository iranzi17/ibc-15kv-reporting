"""Hero section utilities for the WorkWatch Streamlit app."""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


def _resolve_image(image_path: str) -> str:
    """Return a usable image source for the hero media preview."""

    candidate_paths = [Path(image_path), Path(__file__).parent / image_path]
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
    return image_path


def render_hero(
    title: str = "Smart Field Reporting for Electrical & Civil Works",
    subtitle: str = "A modern reporting system for engineers, supervisors and consultants.",
    cta_primary: str = "Generate Reports",
    cta_secondary: str = "Upload Site Data",
    image_path: str = "bg.jpg",
) -> None:
    """Render the FormAssembly-style hero banner used on the landing page."""

    img_src = _resolve_image(image_path)

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.15rem; padding-bottom: 2.25rem; }

        .hero-wrap {
            width: 100%;
            margin: 0 auto 1.75rem auto;
            background: linear-gradient(135deg, #0a66c2 0%, #1b86f9 100%);
            border-radius: 22px;
            padding: clamp(32px, 5vw, 52px) clamp(24px, 6vw, 48px);
            box-shadow: 0 16px 42px rgba(11, 81, 156, 0.28);
            overflow: hidden;
        }

        .hero-grid {
            display: grid;
            grid-template-columns: 1.05fr 0.95fr;
            gap: clamp(18px, 3vw, 32px);
            align-items: center;
        }

        .hero-title {
            color: #ffffff;
            font-weight: 800;
            letter-spacing: -0.3px;
            line-height: 1.1;
            font-size: clamp(30px, 3.2vw, 46px);
            margin: 0 0 0.6rem 0;
        }

        .hero-subtitle {
            color: rgba(255,255,255,0.92);
            font-size: clamp(15px, 1.25vw, 18px);
            line-height: 1.6;
            margin: 0 0 1.4rem 0;
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
            transition: transform .08s ease, box-shadow .2s ease, background .18s ease;
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
            background: rgba(10, 102, 194, 0.18);
            color: #ffffff;
            border: 2px solid rgba(255,255,255,0.88);
            box-shadow: 0 8px 22px rgba(0,0,0,0.12);
        }
        .hero-cta .btn-outline:hover {
            background: rgba(255,255,255,0.2);
            transform: translateY(-1px);
        }

        .hero-media {
            display: flex;
            justify-content: center;
        }

        .hero-tablet {
            width: 100%;
            background: rgba(255,255,255,0.96);
            border-radius: 22px;
            padding: 12px;
            box-shadow: 0 20px 44px rgba(0,0,0,0.26);
        }

        .hero-tablet img {
            width: 100%;
            height: auto;
            border-radius: 16px;
            display: block;
        }

        @media (max-width: 900px) {
            .hero-grid {
                grid-template-columns: 1fr;
            }
            .hero-media { order: -1; }
        }

        body, .stApp { background: #ffffff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    hero_container = st.container()
    with hero_container:
        st.markdown(
            f"""
            <div class="hero-wrap">
              <div class="hero-grid">
                <div class="hero-copy">
                  <h1 class="hero-title">{title}</h1>
                  <p class="hero-subtitle">{subtitle}</p>
                  <div class="hero-cta">
                    <button class="btn-primary" data-action="generate">{cta_primary}</button>
                    <button class="btn-outline" data-action="upload">{cta_secondary}</button>
                  </div>
                </div>
                <div class="hero-media">
                  <div class="hero-tablet">
                    <img src="{img_src}" alt="Preview" />
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <script>
        (function attachHeroCTAs(){
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
