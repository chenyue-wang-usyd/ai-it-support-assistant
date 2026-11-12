import json

import httpx
from openai import OpenAI
from pydantic import SecretStr

from tests.test_ai import valid_analysis


def test_real_sdk_parses_mock_transport_response(client, issue, monkeypatch):
    """Check serialization and parsing in the real SDK; MockTransport cannot reach a network."""
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "id": "resp_unit_test",
                "object": "response",
                "created_at": 0,
                "model": "gpt-4o-mini",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(valid_analysis()),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    def local_client(**kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    client.app.state.settings.openai_api_key = SecretStr("transport-only-test-key")
    monkeypatch.setattr("backend.services.diagnosis.OpenAI", local_client)
    response = client.post("/diagnose", json=issue)
    assert response.status_code == 200
    assert response.json()["mode"] == "AI-Powered Analysis"
    assert len(captured) == 1
    schema = captured[0]["text"]["format"]
    assert schema["type"] == "json_schema"
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
