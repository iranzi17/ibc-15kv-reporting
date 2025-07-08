import logging

try:  # pragma: no cover - requests may not be installed in some environments
    import requests
except Exception:  # noqa: BLE001 - any import failure should fallback gracefully
    requests = None


logger = logging.getLogger(__name__)


def generate_hf_summary(text: str, hf_token: str) -> str:
    """Summarize text using Hugging Face's inference API.

    If the request fails or the API returns a non-200 status code, a fallback
    message is returned and the error is logged.
    """
    API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {"Authorization": f"Bearer {hf_token}"}
    prompt = (
        "You are an experienced electrical engineering consultant. Summarize the "
        "following daily site reports into a natural, professional, and human-sounding weekly progress summary:\n\n" + text
    )
    payload = {"inputs": prompt}

    if requests is None:
        logger.warning("requests library is not available")
        return "Summary not available. Please check your Hugging Face token or try again later."

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
    except requests.RequestException as exc:
        logger.warning("HF API request failed: %s", exc)
        return "Summary not available. Please check your Hugging Face token or try again later."

    if response.status_code != 200:
        logger.warning("HF API returned status %s: %s", response.status_code, response.text)
        return "Summary not available. Please check your Hugging Face token or try again later."

    try:
        return response.json()[0]["summary_text"]
    except Exception as exc:  # noqa: BLE001  # allow broad except for robustness
        logger.warning("Failed to parse HF API response: %s", exc)
        return "Summary not available. Please check your Hugging Face token or try again later."
