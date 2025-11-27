import json
from types import SimpleNamespace

import pytest

from auditor_inference.inference import audit_document, call_remote_llm


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_call_remote_llm(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=60):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse({"llm_findings": [{"code": "X"}], "raw_model_output": "raw"})

    import auditor_inference.inference as inf

    monkeypatch.setattr(inf, "requests", SimpleNamespace(post=fake_post))

    resp = call_remote_llm("http://example.com/llm", {"doc": 1}, [{"id": "c1"}], timeout=5)
    assert resp["llm_findings"][0]["code"] == "X"
    assert captured["url"] == "http://example.com/llm"
    assert captured["timeout"] == 5
    assert captured["json"]["doc"] == {"doc": 1}


def test_audit_document_skip_llm(monkeypatch, tmp_path):
    # Provide a small chunk index file
    chunk_file = tmp_path / "chunks.jsonl"
    chunk_file.write_text('{"id":"c1","text":"IRS guidance"}\n', encoding="utf-8")

    doc = {"doc_id": "d1", "doc_type": "W2", "tax_year": 2024, "amounts": {"wages": 1000}}
    result = audit_document(
        doc,
        chunk_index_path=str(chunk_file),
        base_model="dummy",
        adapter_dir="dummy",
        skip_llm=True,
    )
    assert result["llm_findings"] == []
    assert result["audit_trail"]["llm_skipped"] is True
    assert result["audit_trail"]["llm_mode"] == "SKIPPED"
    assert result["audit_trail"]["retrieval_sources"]


def test_audit_document_remote_llm(monkeypatch, tmp_path):
    # Provide a small chunk index file
    chunk_file = tmp_path / "chunks.jsonl"
    chunk_file.write_text('{"id":"c1","text":"IRS guidance"}\n', encoding="utf-8")

    doc = {"doc_id": "d1", "doc_type": "W2", "tax_year": 2024, "amounts": {"wages": 1000}}

    def fake_post(url, json=None, timeout=60):
        return FakeResponse(
            {
                "llm_findings": [
                    {
                        "code": "REMOTE",
                        "category": "TEST",
                        "severity": "LOW",
                        "summary": "s",
                        "details": "d",
                        "suggested_action": "a",
                        "citation_hint": "c",
                        "tags": [],
                    }
                ],
                "raw_model_output": "raw",
            }
        )

    import auditor_inference.inference as inf

    monkeypatch.setattr(inf, "requests", SimpleNamespace(post=fake_post))

    result = audit_document(
        doc,
        chunk_index_path=str(chunk_file),
        base_model="dummy",
        adapter_dir="dummy",
        skip_llm=False,
        llm_endpoint="http://example.com/llm",
        http_timeout=5,
    )
    codes = {f["code"] for f in result["llm_findings"]}
    assert "REMOTE" in codes
    assert result["audit_trail"]["llm_skipped"] is False
    assert result["audit_trail"]["llm_mode"] == "REMOTE"
    assert result["audit_trail"]["retrieval_sources"]
