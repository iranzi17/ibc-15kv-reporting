from __future__ import annotations

from contextlib import nullcontext

import pandas as pd
import streamlit as st


def safe_columns(*args, **kwargs):
    """Call st.columns falling back to positional-only call for stubs."""
    columns_fn = getattr(st, "columns", None)
    if not callable(columns_fn):
        return (nullcontext(), nullcontext())

    requested_count = None
    if args:
        first_arg = args[0]
        if isinstance(first_arg, int):
            requested_count = first_arg
        elif isinstance(first_arg, (list, tuple)):
            requested_count = len(first_arg)

    try:
        columns = columns_fn(*args, **kwargs)
    except TypeError:
        columns = columns_fn(*args)

    if requested_count is None:
        return columns

    columns_list = list(columns)
    while len(columns_list) < requested_count:
        columns_list.append(nullcontext())
    return tuple(columns_list)


def safe_markdown(markdown: str, **kwargs) -> None:
    markdown_fn = getattr(st, "markdown", None)
    if callable(markdown_fn):
        markdown_fn(markdown, **kwargs)


def safe_checkbox(label: str, *, value=False, key=None):
    checkbox_fn = getattr(st, "checkbox", None)
    if callable(checkbox_fn):
        return checkbox_fn(label, value=value, key=key)
    return value


def safe_caption(text: str) -> None:
    caption_fn = getattr(st, "caption", None)
    if callable(caption_fn):
        caption_fn(text)


def safe_data_editor(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    editor_fn = getattr(st, "data_editor", None)
    if not callable(editor_fn):
        return df
    try:
        edited = editor_fn(df, **kwargs)
    except TypeError:
        edited = editor_fn(df)
    if isinstance(edited, pd.DataFrame):
        return edited
    return df


def safe_image(images, **kwargs) -> None:
    image_fn = getattr(st, "image", None)
    if callable(image_fn):
        image_fn(images, **kwargs)


def safe_text_input(label: str, value: str = "", **kwargs) -> str:
    text_input_fn = getattr(st, "text_input", None)
    if callable(text_input_fn):
        try:
            return text_input_fn(label, value=value, **kwargs)
        except TypeError:
            return text_input_fn(label, value)
    return value


def safe_text_area(label: str, value: str = "", **kwargs) -> str:
    text_area_fn = getattr(st, "text_area", None)
    if callable(text_area_fn):
        try:
            return text_area_fn(label, value=value, **kwargs)
        except TypeError:
            return text_area_fn(label, value)
    return value


def safe_selectbox(label: str, options: list[str], index: int = 0, **kwargs):
    selectbox_fn = getattr(st, "selectbox", None)
    if callable(selectbox_fn):
        try:
            return selectbox_fn(label, options, index=index, **kwargs)
        except TypeError:
            return selectbox_fn(label, options, index)
    if not options:
        return None
    safe_index = max(0, min(index, len(options) - 1))
    return options[safe_index]


def safe_file_uploader(label: str, **kwargs):
    uploader_fn = getattr(st, "file_uploader", None)
    if callable(uploader_fn):
        return uploader_fn(label, **kwargs)
    if kwargs.get("accept_multiple_files"):
        return []
    return None


def safe_write(value: object) -> None:
    write_fn = getattr(st, "write", None)
    if callable(write_fn):
        write_fn(value)


def safe_expander(label: str, *, expanded: bool = False):
    expander_fn = getattr(st, "expander", None)
    if callable(expander_fn):
        try:
            return expander_fn(label, expanded=expanded)
        except TypeError:
            return expander_fn(label)
    return nullcontext()


def safe_chat_message(role: str):
    chat_message_fn = getattr(st, "chat_message", None)
    if callable(chat_message_fn):
        return chat_message_fn(role)
    return nullcontext()


def safe_chat_input(prompt: str, **kwargs) -> str | None:
    chat_input_fn = getattr(st, "chat_input", None)
    if callable(chat_input_fn):
        try:
            return chat_input_fn(prompt, **kwargs)
        except TypeError:
            return chat_input_fn(prompt)
    return None


def safe_spinner(text: str):
    spinner_fn = getattr(st, "spinner", None)
    if callable(spinner_fn):
        return spinner_fn(text)
    return nullcontext()


def safe_audio(data, **kwargs) -> None:
    audio_fn = getattr(st, "audio", None)
    if callable(audio_fn):
        audio_fn(data, **kwargs)


def safe_audio_input(label: str, **kwargs):
    audio_input_fn = getattr(st, "audio_input", None)
    if callable(audio_input_fn):
        try:
            return audio_input_fn(label, **kwargs)
        except TypeError:
            return audio_input_fn(label)
    return None


def safe_rerun() -> None:
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()

