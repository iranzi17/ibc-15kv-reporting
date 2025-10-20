import base64
from pathlib import Path

import streamlit as st


def _resolve_image(image_path: str) -> str:
    """Return a usable image reference for the hero preview."""

    candidate = Path(image_path)
    if not candidate.exists():
        candidate = Path(__file__).parent / image_path

    if candidate.exists() and candidate.is_file():
        encoded = base64.b64encode(candidate.read_bytes()).decode()
        suffix = candidate.suffix.lower()
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
    """Render the FormAssembly-style hero section at the top of the page."""

    st.markdown(
        """
        <style>
        /* ---- Global refinements ---- */
        /* Reduce default Streamlit padding a bit */
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }

        /* ---- Hero wrapper ---- */
        .hero-outer {
            width: 100%;
            margin-bottom: 28px;
        }
        .hero-wrap {
            width: min(1120px, 100%);
            margin: 0 auto;
            border-radius: 16px;
            overflow: hidden;
            background: linear-gradient(135deg, #0a66c2 0%, #1b86f9 100%);
            padding: clamp(32px, 5vw, 48px) clamp(20px, 4vw, 36px);
            box-shadow: 0 12px 30px rgba(20, 86, 160, 0.25);
        }

        /* ---- Hero grid ---- */
        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
            gap: clamp(20px, 4vw, 32px);
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

    img_src = _resolve_image(image_path)

    st.markdown(
        f"""
        <div class="hero-outer">
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
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <script>
        // Optional: Codex can bind these to existing widgets/sections.
        // document.querySelector('[data-action="generate"]')?.addEventListener('click', () => {/* attach */});
        // document.querySelector('[data-action="upload"]')?.addEventListener('click', () => {/* attach */});
        </script>
        """,
        unsafe_allow_html=True,
    )
