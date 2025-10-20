"""Hero section utilities for the WorkWatch Streamlit app."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import streamlit as st


def _resolve_image(image_path: str) -> Optional[str]:
    """Return a base64 data URI for the provided image path if it exists."""
    candidate_paths = [Path(image_path)]
    # Support relative lookups from this file's directory as well.
    candidate_paths.append(Path(__file__).parent / image_path)

    for path in candidate_paths:
        if path.exists() and path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode()
            # Heuristic for mime type; jpg is the provided asset.
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
) -> None:
    """Render the blue FormAssembly-style hero at the top of the page."""

    st.markdown(
        """
        <style>
        /* ---- Global refinements ---- */
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }

        /* ---- Hero wrapper ---- */
        .hero-wrap {
            width: 100%;
            margin: 0 auto 28px auto;
            border-radius: 16px;
            overflow: hidden;
            background: linear-gradient(135deg, #0a66c2 0%, #1b86f9 100%);
            padding: 48px 28px;
            box-shadow: 0 12px 30px rgba(20, 86, 160, 0.25);
        }

        /* ---- Hero grid ---- */
        .hero-grid {
            display: grid;
            grid-template-columns: 1.1fr 1fr;
            gap: 28px;
            align-items: center;
        }

        /* ---- Left text ---- */
        .hero-title {
            color: #ffffff;
            font-weight: 800;
            letter-spacing: -0.3px;
            line-height: 1.15;
            font-size: clamp(28px, 3.2vw, 44px);
            margin: 0 0 10px 0;
        }
        .hero-subtitle {
            color: rgba(255,255,255,0.92);
            font-size: clamp(14px, 1.3vw, 18px);
            line-height: 1.6;
            margin: 0 0 22px 0;
        }

        /* ---- CTA row ---- */
        .hero-cta {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }
        .btn-primary {
            background: #ffffff; color: #0a66c2;
            border: 0; border-radius: 10px; padding: 12px 18px;
            font-weight: 700; cursor: pointer;
            box-shadow: 0 6px 14px rgba(0,0,0,0.08);
            transition: transform .06s ease, box-shadow .2s ease;
        }
        .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 10px 20px rgba(0,0,0,0.12); }

        .btn-outline {
            background: transparent; color: #ffffff;
            border: 2px solid rgba(255,255,255,0.9);
            border-radius: 10px; padding: 10px 16px;
            font-weight: 700; cursor: pointer;
            transition: background .15s ease, transform .06s ease;
        }
        .btn-outline:hover { background: rgba(255,255,255,0.12); transform: translateY(-1px); }

        /* ---- Right image tablet ---- */
        .hero-media {
            background: #ffffff;
            border-radius: 18px;
            padding: 10px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.18);
        }
        .hero-media img {
            display: block;
            width: 100%;
            height: auto;
            border-radius: 12px;
        }

        /* ---- Responsive ---- */
        @media (max-width: 900px) {
            .hero-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    img_src = _resolve_image(image_path) or image_path

    st.markdown(
        f"""
        <div class="hero-wrap">
          <div class="hero-grid">
            <div>
              <h1 class="hero-title">{title}</h1>
              <p class="hero-subtitle">{subtitle}</p>
              <div class="hero-cta">
                <button class="btn-primary" data-action="generate">{cta_primary}</button>
                <button class="btn-outline" data-action="upload">{cta_secondary}</button>
              </div>
            </div>
            <div class="hero-media">
              <img src="{img_src}" alt="Preview">
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
            const actionMap = {
                generate: 'reports-section',
                upload: 'upload-section'
            };
            const bind = () => {
                document.querySelectorAll('.hero-cta [data-action]').forEach((btn) => {
                    if (btn.dataset.heroBound === 'true') return;
                    btn.dataset.heroBound = 'true';
                    btn.addEventListener('click', () => {
                        const targetId = actionMap[btn.dataset.action];
                        if (!targetId) return;
                        const el = document.getElementById(targetId);
                        if (el && typeof el.scrollIntoView === 'function') {
                            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                    });
                });
            };
            if (document.readyState === 'complete') {
                bind();
            } else {
                window.addEventListener('load', bind);
                document.addEventListener('DOMContentLoaded', bind);
            }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    # Ensure the rest of the page retains a neutral white background.
    st.markdown(
        """
        <style>
          body, .stApp { background: #ffffff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
