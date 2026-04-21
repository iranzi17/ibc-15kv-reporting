from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import textwrap

import streamlit as st
from PIL import Image

from core.session_state import AI_IMAGE_CAPTIONS_KEY, utc_timestamp
from report_structuring import REPORT_HEADERS
from services.openai_client import (
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    TRANSCRIPTION_OPENAI_MODEL,
    TRANSCRIPTION_OPENROUTER_MODEL,
    TTS_OPENAI_MODEL,
    extract_chat_completion_text,
    extract_openai_output_text,
    make_ai_client,
    normalize_ai_provider,
)
from services.usage_logging import log_usage_event


def uploaded_file_name(uploaded_file: object) -> str:
    name = str(getattr(uploaded_file, "name", "") or "").strip()
    return name or "upload.bin"


def uploaded_file_mime_type(uploaded_file: object) -> str:
    explicit_type = str(getattr(uploaded_file, "type", "") or "").strip()
    if explicit_type:
        return explicit_type
    guessed_type, _ = mimetypes.guess_type(uploaded_file_name(uploaded_file))
    return guessed_type or "application/octet-stream"


def uploaded_file_bytes(uploaded_file: object) -> bytes:
    getvalue_fn = getattr(uploaded_file, "getvalue", None)
    if callable(getvalue_fn):
        data = getvalue_fn()
        return bytes(data or b"")

    read_fn = getattr(uploaded_file, "read", None)
    if not callable(read_fn):
        return b""

    tell_fn = getattr(uploaded_file, "tell", None)
    seek_fn = getattr(uploaded_file, "seek", None)
    position = None
    if callable(tell_fn):
        try:
            position = tell_fn()
        except Exception:
            position = None

    data = read_fn()
    if callable(seek_fn) and position is not None:
        try:
            seek_fn(position)
        except Exception:
            pass
    return bytes(data or b"")


def data_url_for_bytes(data: bytes, *, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def uploaded_file_to_response_part(uploaded_file: object) -> dict[str, str] | None:
    data = uploaded_file_bytes(uploaded_file)
    if not data:
        return None

    filename = uploaded_file_name(uploaded_file)
    mime_type = uploaded_file_mime_type(uploaded_file)
    data_url = data_url_for_bytes(data, mime_type=mime_type)
    if mime_type.startswith("image/"):
        return {
            "type": "input_image",
            "image_url": data_url,
        }
    return {
        "type": "input_file",
        "filename": filename,
        "file_data": data_url,
    }


def uploaded_files_signature(files: list[object]) -> str:
    digest = hashlib.sha256()
    for uploaded_file in files:
        filename = uploaded_file_name(uploaded_file)
        data = uploaded_file_bytes(uploaded_file)
        digest.update(filename.encode("utf-8"))
        digest.update(len(data).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def uploaded_file_names(files: list[object] | None) -> list[str]:
    return [uploaded_file_name(uploaded_file) for uploaded_file in files or [] if uploaded_file]


def uploaded_files_to_response_input(
    prompt_text: str,
    *,
    uploaded_files: list[object] | None = None,
) -> list[dict[str, object]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt_text.strip()}]
    for uploaded_file in uploaded_files or []:
        part = uploaded_file_to_response_part(uploaded_file)
        if part:
            content.append(part)
    return [{"role": "user", "content": content}]


def uploaded_file_to_chat_part(uploaded_file: object) -> dict[str, object] | None:
    """Convert one uploaded file into an OpenRouter/OpenAI Chat content part."""
    data = uploaded_file_bytes(uploaded_file)
    if not data:
        return None

    filename = uploaded_file_name(uploaded_file)
    mime_type = uploaded_file_mime_type(uploaded_file)
    data_url = data_url_for_bytes(data, mime_type=mime_type)
    if mime_type.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": data_url}}
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return {"type": "file", "file": {"filename": filename, "file_data": data_url}}
    if mime_type.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv", ".json", ".xml")):
        decoded = data.decode("utf-8", errors="replace").strip()
        if decoded:
            return {
                "type": "text",
                "text": f"Attached text file ({filename}):\n{decoded[:12000]}",
            }
    return {
        "type": "text",
        "text": f"Attached file available by name only: {filename} ({mime_type}).",
    }


def uploaded_files_to_chat_content(
    prompt_text: str,
    *,
    uploaded_files: list[object] | None = None,
) -> list[dict[str, object]]:
    """Convert prompt and attachments into Chat Completions multipart content."""
    content: list[dict[str, object]] = [{"type": "text", "text": prompt_text.strip()}]
    for uploaded_file in uploaded_files or []:
        part = uploaded_file_to_chat_part(uploaded_file)
        if part:
            content.append(part)
    return content


def has_pdf_files(files: list[object] | None) -> bool:
    """Return whether uploaded files contain at least one PDF."""
    for uploaded_file in files or []:
        filename = uploaded_file_name(uploaded_file).lower()
        mime_type = uploaded_file_mime_type(uploaded_file)
        if mime_type == "application/pdf" or filename.endswith(".pdf"):
            return True
    return False


def has_image_files(files: list[object] | None) -> bool:
    return any(uploaded_file_mime_type(uploaded_file).startswith("image/") for uploaded_file in files or [])


def image_bytes_signature(images: list[bytes], *, guidance: str = "") -> str:
    digest = hashlib.sha256()
    for image_bytes in images or []:
        payload = bytes(image_bytes or b"")
        digest.update(len(payload).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha256(payload).digest())
    digest.update(guidance.encode("utf-8"))
    return digest.hexdigest()


def image_mime_type_from_bytes(image_bytes: bytes) -> str:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").lower()
    except Exception:
        return "image/jpeg"
    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }.get(image_format, "image/jpeg")


def photo_caption_cache() -> dict[str, object]:
    return st.session_state.setdefault(AI_IMAGE_CAPTIONS_KEY, {})


def photo_caption_response_schema(expected_count: int) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "captions": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "string",
                    "description": "A short factual site-photo caption.",
                },
            }
        },
        "required": ["captions"],
        "additionalProperties": False,
    }


def report_row_context_text(row: list[str] | tuple[str, ...]) -> str:
    padded = list(row) + [""] * max(0, len(REPORT_HEADERS) - len(row))
    padded = padded[: len(REPORT_HEADERS)]
    mapping = {header: str(value or "").strip() for header, value in zip(REPORT_HEADERS, padded)}
    return textwrap.dedent(
        f"""
        Date: {mapping.get("Date", "")}
        Site: {mapping.get("Site_Name", "")}
        District: {mapping.get("District", "")}
        Work: {mapping.get("Work", "")}
        Work executed: {mapping.get("Work_Executed", "")}
        Comment on work: {mapping.get("Comment_on_work", "")}
        Comment on HSE: {mapping.get("Comment_on_HSE", "")}
        Challenges: {mapping.get("challenges", "")}
        """
    ).strip()


def request_image_captions_with_openai(
    images: list[bytes],
    *,
    api_key: str,
    model: str,
    discipline: str,
    report_row: list[str] | tuple[str, ...],
    persistent_guidance: str = "",
    provider: str | None = PROVIDER_OPENAI,
) -> list[str]:
    """Generate short site-photo captions using the configured AI vision provider."""

    if not images:
        return []
    normalized_provider = normalize_ai_provider(provider)

    instructions = textwrap.dedent(
        f"""
        You are writing short captions for {discipline.lower()} daily report photos.

        Rules:
        - Return JSON matching the schema exactly.
        - Write one caption per image, in the same order as the images were provided.
        - Keep captions factual, concise, and professional.
        - Do not invent locations, equipment, hazards, or quantities not visible in the image or present in the report context.
        - Prefer consultant-style phrasing and action-oriented wording.
        - Each caption should usually be one sentence and under 18 words.
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved caption and reporting preferences:\n{persistent_guidance}"

    prompt_text = (
        "Report context:\n"
        f"{report_row_context_text(report_row)}\n\n"
        "Generate captions for the attached site photos."
    )

    try:
        if normalized_provider == PROVIDER_OPENROUTER:
            content: list[dict[str, object]] = [{"type": "text", "text": prompt_text}]
            for image_bytes in images:
                payload = bytes(image_bytes or b"")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url_for_bytes(
                                payload,
                                mime_type=image_mime_type_from_bytes(payload),
                            )
                        },
                    }
                )
            response = make_ai_client(api_key=api_key, provider=normalized_provider).chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "site_photo_captions",
                        "strict": True,
                        "schema": photo_caption_response_schema(len(images)),
                    },
                }
            )
            payload_text = extract_chat_completion_text(response)
        else:
            content: list[dict[str, str]] = [{"type": "input_text", "text": prompt_text}]
            for image_bytes in images:
                payload = bytes(image_bytes or b"")
                content.append(
                    {
                        "type": "input_image",
                        "image_url": data_url_for_bytes(
                            payload,
                            mime_type=image_mime_type_from_bytes(payload),
                        ),
                    }
                )
            response = make_ai_client(api_key=api_key, provider=normalized_provider).responses.create(
                model=model,
                instructions=instructions,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "site_photo_captions",
                        "strict": True,
                        "schema": photo_caption_response_schema(len(images)),
                    }
                },
                store=False,
            )
            payload_text = extract_openai_output_text(response)
        if not payload_text:
            raise ValueError(f"{'OpenRouter' if normalized_provider == PROVIDER_OPENROUTER else 'OpenAI'} returned empty photo captions.")
        payload = json.loads(payload_text)
        captions = payload.get("captions", [])
        if not isinstance(captions, list):
            raise ValueError("The AI provider returned invalid photo captions.")
    except Exception as exc:
        log_usage_event(
            feature_name="image_captioning",
            model=model,
            has_files=True,
            has_images=True,
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="image_captioning",
        model=model,
        has_files=True,
        has_images=True,
        status="success",
    )
    return [str(caption or "").strip() for caption in captions]


def request_transcription_with_openai(
    audio_files: list[object],
    *,
    api_key: str,
    discipline: str,
    provider: str | None = PROVIDER_OPENAI,
) -> str:
    """Transcribe one or more uploaded voice notes into plain text."""

    if not audio_files:
        raise ValueError("Upload at least one voice note before requesting transcription.")
    normalized_provider = normalize_ai_provider(provider)
    model = TRANSCRIPTION_OPENROUTER_MODEL if normalized_provider == PROVIDER_OPENROUTER else TRANSCRIPTION_OPENAI_MODEL

    prompt = (
        f"This is a {discipline.lower()} construction site voice note for a daily report in Rwanda. "
        "Preserve site names, district names, acronyms, equipment names, cable sizes, 15kV notation, "
        "MV, LV, HSE, PPE, and quantities as accurately as possible."
    )
    transcripts: list[str] = []
    try:
        client = make_ai_client(api_key=api_key, provider=normalized_provider)
        for uploaded_file in audio_files:
            file_data = uploaded_file_bytes(uploaded_file)
            if not file_data:
                continue
            if normalized_provider == PROVIDER_OPENROUTER:
                filename = uploaded_file_name(uploaded_file)
                audio_format = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Transcribe this voice note as accurately as possible."},
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": base64.b64encode(file_data).decode("utf-8"),
                                        "format": audio_format,
                                    },
                                },
                            ],
                        },
                    ],
                )
                transcript_text = extract_chat_completion_text(response)
            else:
                audio_stream = io.BytesIO(file_data)
                audio_stream.name = uploaded_file_name(uploaded_file)
                try:
                    transcription = client.audio.transcriptions.create(
                        model=model,
                        file=audio_stream,
                        response_format="text",
                        prompt=prompt,
                    )
                finally:
                    audio_stream.close()

                transcript_text = transcription.strip() if isinstance(transcription, str) else str(getattr(transcription, "text", "") or "").strip()
            if transcript_text:
                transcripts.append(f"Voice note ({uploaded_file_name(uploaded_file)}):\n{transcript_text}")
        if not transcripts:
            raise ValueError("The AI provider did not return any transcription text.")
    except Exception as exc:
        log_usage_event(
            feature_name="transcription",
            model=model,
            has_files=True,
            has_images=False,
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="transcription",
        model=model,
        has_files=True,
        has_images=False,
        status="success",
    )
    return "\n\n".join(transcripts)


def request_text_to_speech_with_openai(
    text: str,
    *,
    api_key: str,
    voice: str = "coral",
    instructions: str = "Speak in a calm, professional consultant briefing tone.",
    provider: str | None = PROVIDER_OPENAI,
) -> bytes:
    """Convert assistant text into MP3 audio."""
    normalized_provider = normalize_ai_provider(provider)
    if normalized_provider == PROVIDER_OPENROUTER:
        raise ValueError("Text-to-speech is not enabled for OpenRouter mode in this app yet. Switch provider to OpenAI for readback audio.")

    speech_input = str(text or "").strip()
    if not speech_input:
        raise ValueError("Text is required before generating speech.")
    try:
        response = make_ai_client(api_key=api_key, provider=normalized_provider).audio.speech.create(
            model=TTS_OPENAI_MODEL,
            voice=voice,
            input=speech_input[:4000],
            instructions=instructions,
            response_format="mp3",
        )
        audio_bytes = response.read()
    except Exception as exc:
        log_usage_event(
            feature_name="text_to_speech",
            model=TTS_OPENAI_MODEL,
            has_files=False,
            has_images=False,
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="text_to_speech",
        model=TTS_OPENAI_MODEL,
        has_files=False,
        has_images=False,
        status="success",
    )
    return audio_bytes


def build_review_row_mapping(review_rows: list[list[str]]) -> dict[tuple[str, str], list[str]]:
    """Map site/date pairs to the edited review rows used for report generation."""
    mapping: dict[tuple[str, str], list[str]] = {}
    for row in review_rows:
        padded = (list(row) + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)]
        key = (str(padded[1] or "").strip(), str(padded[0] or "").strip())
        if all(key):
            mapping[key] = padded
    return mapping


def generate_ai_photo_captions_for_reports(
    review_rows: list[list[str]],
    image_mapping: dict[tuple[str, str], list[bytes]],
    *,
    api_key: str,
    model: str,
    discipline: str,
    persistent_guidance: str = "",
    provider: str | None = PROVIDER_OPENAI,
) -> dict[tuple[str, str], list[str]]:
    """Generate or reuse AI captions for uploaded report photos."""
    cache = photo_caption_cache()
    row_mapping = build_review_row_mapping(review_rows)
    caption_mapping: dict[tuple[str, str], list[str]] = {}

    for key, images in image_mapping.items():
        normalized_key = (str(key[0]).strip(), str(key[1]).strip())
        if normalized_key not in row_mapping or not images:
            continue

        signature = image_bytes_signature(images, guidance=persistent_guidance)
        cache_key = f"{normalized_key[0]}|{normalized_key[1]}"
        cached = cache.get(cache_key, {})
        if isinstance(cached, dict) and cached.get("signature") == signature:
            captions = cached.get("captions", [])
            if isinstance(captions, list):
                caption_mapping[normalized_key] = [str(item or "").strip() for item in captions]
                continue

        captions = request_image_captions_with_openai(
            images,
            api_key=api_key,
            model=model,
            discipline=discipline,
            report_row=row_mapping[normalized_key],
            persistent_guidance=persistent_guidance,
            provider=provider,
        )
        cache[cache_key] = {
            "signature": signature,
            "captions": captions,
            "created_at": utc_timestamp(),
        }
        caption_mapping[normalized_key] = captions

    st.session_state[AI_IMAGE_CAPTIONS_KEY] = cache
    return caption_mapping

