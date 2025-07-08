from summary_utils import generate_hf_summary
from unittest.mock import patch


class DummyRequests:
    class RequestException(Exception):
        pass


def test_generate_hf_summary_request_exception():
    with patch('summary_utils.requests') as mock_requests:
        mock_requests.post.side_effect = DummyRequests.RequestException("boom")
        mock_requests.RequestException = DummyRequests.RequestException
        result = generate_hf_summary("text", "token")
    assert result.startswith("Summary not available")
