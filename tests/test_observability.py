from src.observability import scrub_event


def test_scrub_event_removes_request_secrets_and_body():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "X-Api-Key": "api-secret",
                "X-Request-ID": "safe",
            },
            "data": {"password": "secret"},
            "query_string": "token=secret&event=123",
        }
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed["request"]["headers"] == {"X-Request-ID": "safe"}
    assert scrubbed["request"]["data"] == "[Filtered]"
    assert scrubbed["request"]["query_string"] == "token=%5BFiltered%5D&event=123"


def test_scrub_event_removes_sensitive_query_values_from_url():
    event = {"request": {"url": "https://example.test/api?api_key=secret&mode=live"}}

    scrubbed = scrub_event(event, {})

    assert scrubbed["request"]["url"] == "https://example.test/api?api_key=%5BFiltered%5D&mode=live"
