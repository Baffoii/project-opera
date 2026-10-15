from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema

from app.adapters.vlm_clues import PROMPT_VERSION, SYSTEM_PROMPT, VlmClueAdapter, VlmClueError, downscale_for_vlm
from app.schemas import VlmClueOutput

from .conftest import make_settings


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.responses = FakeResponses(response, error)
        self.options: dict = {}

    def with_options(self, **kw):
        self.options = kw
        return self


def _response(parsed=None, *, status="completed", refusal=None, usage=(1000, 200)):
    content = [SimpleNamespace(type="refusal", refusal=refusal)] if refusal else []
    return SimpleNamespace(
        status=status,
        output=[SimpleNamespace(content=content)],
        output_parsed=parsed,
        usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
    )


def _clue(category="signage", text="Road sign in Portuguese", certainty="observed"):
    return {"category": category, "text": text, "certainty": certainty}


def _adapter(tmp_path, client, **kw):
    return VlmClueAdapter(make_settings(tmp_path, vlm_model="test-model", **kw), client=client, api_key="k")


@pytest.fixture
def img(jpeg_bytes):
    return jpeg_bytes(size=(2000, 1500))


def test_success_normalises_and_caps_output(tmp_path, img):
    parsed = VlmClueOutput.model_validate(
        {
            "abstain": False,
            "abstain_reason": None,
            "clues": [_clue(text="  x" * 200)] + [_clue()] * 30 + [_clue(text="   ")],
            "region_guesses": ["Portugal", "Spain", "France", "Italy", " "],
        }
    )
    client = FakeClient(_response(parsed))
    result = _adapter(tmp_path, client).extract(img, mime="image/jpeg")
    assert len(result.clues) == 20
    assert all(len(c["text"]) <= 300 for c in result.clues)
    assert result.region_guesses == ["Portugal", "Spain", "France"]
    assert (result.input_tokens, result.output_tokens) == (1000, 200)
    assert result.prompt_version == PROMPT_VERSION and result.model_name == "test-model"
    assert client.options["max_retries"] == 1 and client.options["timeout"] > 0


def test_request_shape_uses_structured_output_no_storage_and_downscaled_image(tmp_path, img):
    parsed = VlmClueOutput(abstain=False, abstain_reason=None, clues=[], region_guesses=[])
    client = FakeClient(_response(parsed))
    _adapter(tmp_path, client, vlm_max_edge_px=256).extract(img, mime="image/jpeg")
    call = client.responses.calls[0]
    assert call["store"] is False and call["text_format"] is VlmClueOutput and call["model"] == "test-model"
    user = call["input"][1]["content"]
    image_part = next(p for p in user if p["type"] == "input_image")
    assert image_part["image_url"].startswith("data:image/jpeg;base64,")
    assert call["input"][0]["content"] == SYSTEM_PROMPT


def test_downscale_limits_long_edge(img):
    from io import BytesIO

    from PIL import Image

    small = downscale_for_vlm(img, 256)
    with Image.open(BytesIO(small)) as out:
        assert max(out.size) <= 256 and out.getexif().get(274) is None


def test_model_abstain_is_reported(tmp_path, img):
    parsed = VlmClueOutput(abstain=True, abstain_reason="Indoor document", clues=[_clue()], region_guesses=["x"])
    result = _adapter(tmp_path, FakeClient(_response(parsed))).extract(img, mime="image/jpeg")
    assert result.abstain and result.abstain_reason == "Indoor document"
    assert result.clues == [] and result.region_guesses == []


def test_refusal_is_not_an_abstain(tmp_path, img):
    result = _adapter(tmp_path, FakeClient(_response(None, refusal="I can't help"))).extract(img, mime="image/jpeg")
    assert not result.abstain and result.clues == []
    assert any("declined" in n for n in result.notices)


@pytest.mark.parametrize(
    "response,error",
    [
        (_response(None), None),  # unparsable output
        (_response(VlmClueOutput(abstain=False, abstain_reason=None, clues=[], region_guesses=[]), status="incomplete"), None),
        (None, TimeoutError("slow")),
        (None, httpx.ReadTimeout("slow")),
        (None, RuntimeError("429 rate limited")),
    ],
)
def test_failures_become_clue_error_without_leaking_detail(tmp_path, img, response, error):
    adapter = _adapter(tmp_path, FakeClient(response, error))
    with pytest.raises(VlmClueError) as info:
        adapter.extract(img, mime="image/jpeg")
    assert "k" != str(info.value) and "rate limited" not in str(info.value)


def test_unavailable_without_key_or_model(tmp_path):
    no_key = VlmClueAdapter(make_settings(tmp_path, vlm_model="m"), api_key="")
    assert no_key.availability() == (False, "no key")
    no_model = VlmClueAdapter(make_settings(tmp_path, vlm_model=""), client=FakeClient(), api_key="k")
    assert no_model.availability() == (False, "OPERA_VLM_MODEL is not set")
    off = VlmClueAdapter(make_settings(tmp_path, vlm_model="m", vlm_enabled=False), api_key="k")
    assert off.availability()[0] is False
    with pytest.raises(VlmClueError):
        no_key.extract(b"x", mime="image/jpeg")


def _schema_keywords(node, found=None):
    """Collect schema keywords, skipping the *names* of properties."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key == "properties":
                for sub in value.values():
                    _schema_keywords(sub, found)
            else:
                _schema_keywords(value, found)
    elif isinstance(node, list):
        for item in node:
            _schema_keywords(item, found)
    return found


def test_strict_schema_has_no_unsupported_keywords():
    schema = to_strict_json_schema(VlmClueOutput)
    banned = {"maxLength", "minLength", "maxItems", "minItems", "default", "minimum", "maximum", "pattern"}
    assert not banned & _schema_keywords(schema)
    for definition in [schema, *schema.get("$defs", {}).values()]:
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])


def test_prompt_forbids_identification():
    lowered = SYSTEM_PROMPT.lower()
    assert "ignore people" in lowered and "identity" in lowered and "license plates" in lowered


def test_real_sdk_wire_request(tmp_path, img):
    """Drive the real OpenAI SDK against a mocked HTTP endpoint and check what would go over the wire."""
    body = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "test-model",
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "annotations": [],
                        "text": json.dumps(
                            {
                                "abstain": False,
                                "abstain_reason": None,
                                "clues": [_clue()],
                                "region_guesses": ["Portugal"],
                            }
                        ),
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 80,
            "total_tokens": 1280,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    # MockTransport guarantees no real network call: the only way out is this handler.
    sdk = OpenAI(
        api_key="sk-test-not-real",
        base_url="https://openai.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = VlmClueAdapter(make_settings(tmp_path, vlm_model="test-model"), client=sdk).extract(img, mime="image/jpeg")

    assert result.clues[0]["text"] == "Road sign in Portuguese" and result.region_guesses == ["Portugal"]
    assert (result.input_tokens, result.output_tokens) == (1200, 80)
    assert len(seen) == 1 and str(seen[0].url) == "https://openai.invalid/v1/responses"
    raw = seen[0].content.decode()
    sent = json.loads(raw)
    assert sent["model"] == "test-model" and sent["store"] is False
    fmt = sent["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    parts = sent["input"][1]["content"]
    assert next(p for p in parts if p["type"] == "input_image")["image_url"].startswith("data:image/jpeg;base64,")
    assert "filename" not in raw
    assert seen[0].headers["authorization"] == "Bearer sk-test-not-real"
