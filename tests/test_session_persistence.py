"""
test_session_persistence.py — Tests for persisted session save/load.

Run with: pytest tests/test_session_persistence.py -v
"""

import json

import pytest

import web_app
from web_app import (
    _derive_label,
    _persist_session,
    _load_session_record,
    _list_session_records,
    _delete_session_record,
    _session_path,
    SESSION_SCHEMA_VERSION,
)


@pytest.fixture(autouse=True)
def isolated_sessions_dir(tmp_path, monkeypatch):
    """Point session storage at a temp dir so tests never touch the real cwd."""
    monkeypatch.setattr(web_app, "_get_app_dir", lambda: tmp_path)
    # Reset in-memory sessions between tests.
    web_app.sessions.clear()
    yield tmp_path


# =============================================================================
# Helpers
# =============================================================================

class TestDeriveLabel:
    @pytest.mark.unit
    def test_first_meaningful_line(self):
        assert _derive_label("  \n# Heading\nbody") == "Heading"

    @pytest.mark.unit
    def test_empty_notes(self):
        assert _derive_label("") == "Untitled session"
        assert _derive_label("   \n\n") == "Untitled session"

    @pytest.mark.unit
    def test_truncates_to_80(self):
        assert len(_derive_label("x" * 200)) == 80


class TestPersistAndLoad:
    @pytest.mark.unit
    def test_round_trip(self):
        sid = "11111111-1111-1111-1111-111111111111"
        _persist_session(
            sid,
            {"notes": "my notes", "images": [{"data": "abc", "type": "image/png"}]},
            {"thread_id": "t1", "current_tsg": "TSG body", "follow_up_round": 1},
        )
        record = _load_session_record(sid)
        assert record["schema_version"] == SESSION_SCHEMA_VERSION
        assert record["session_id"] == sid
        assert record["notes"] == "my notes"
        assert record["images"][0]["data"] == "abc"
        assert record["thread_id"] == "t1"
        assert record["current_tsg"] == "TSG body"
        assert record["follow_up_round"] == 1
        assert record["label"] == "my notes"

    @pytest.mark.unit
    def test_missing_record_returns_none(self):
        assert _load_session_record("22222222-2222-2222-2222-222222222222") is None

    @pytest.mark.unit
    def test_followup_preserves_images(self):
        """A follow-up save that sends no images keeps the originals."""
        sid = "33333333-3333-3333-3333-333333333333"
        _persist_session(
            sid,
            {"notes": "n", "images": [{"data": "img1", "type": "image/png"}]},
            {"thread_id": "t1"},
        )
        # Follow-up: no images sent
        _persist_session(sid, {"notes": "n", "images": []}, {"thread_id": "t1", "follow_up_round": 1})
        record = _load_session_record(sid)
        assert record["images"][0]["data"] == "img1"
        assert record["follow_up_round"] == 1

    @pytest.mark.unit
    def test_preserves_created_at_and_custom_label(self):
        sid = "44444444-4444-4444-4444-444444444444"
        _persist_session(sid, {"notes": "orig", "label": "Custom Name"}, {})
        first = _load_session_record(sid)
        created = first["created_at"]
        # Re-save without a label; custom label and created_at must survive.
        _persist_session(sid, {"notes": "orig edited"}, {})
        second = _load_session_record(sid)
        assert second["label"] == "Custom Name"
        assert second["created_at"] == created


class TestListAndDelete:
    @pytest.mark.unit
    def test_list_sorted_newest_first(self, isolated_sessions_dir):
        # Write two records with explicit updated_at.
        for sid, ts in [("a" * 8, "2026-01-01T00:00:00+00:00"), ("b" * 8, "2026-02-01T00:00:00+00:00")]:
            full = f"{sid}-0000-0000-0000-000000000000"
            (isolated_sessions_dir / ".sessions").mkdir(exist_ok=True)
            _session_path(full).write_text(
                json.dumps({"session_id": full, "label": sid, "updated_at": ts, "current_tsg": "x"}),
                encoding="utf-8",
            )
        listing = _list_session_records()
        assert [r["label"] for r in listing] == ["b" * 8, "a" * 8]
        assert listing[0]["has_tsg"] is True

    @pytest.mark.unit
    def test_corrupt_file_skipped(self, isolated_sessions_dir):
        sessions_dir = isolated_sessions_dir / ".sessions"
        sessions_dir.mkdir(exist_ok=True)
        (sessions_dir / "corrupt.json").write_text("{not json", encoding="utf-8")
        good = "55555555-5555-5555-5555-555555555555"
        _persist_session(good, {"notes": "ok"}, {})
        listing = _list_session_records()
        assert len(listing) == 1
        assert listing[0]["session_id"] == good

    @pytest.mark.unit
    def test_delete_idempotent(self):
        sid = "66666666-6666-6666-6666-666666666666"
        _persist_session(sid, {"notes": "x"}, {})
        _delete_session_record(sid)
        assert _load_session_record(sid) is None
        # Deleting again does not raise.
        _delete_session_record(sid)


# =============================================================================
# Endpoints
# =============================================================================

class TestSessionEndpoints:
    @pytest.mark.unit
    def test_save_creates_id_and_lists(self, client):
        resp = client.post("/api/sessions", json={"notes": "first line\nrest"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["label"] == "first line"
        sid = data["session_id"]

        listing = client.get("/api/sessions").get_json()["sessions"]
        assert any(s["session_id"] == sid for s in listing)

    @pytest.mark.unit
    def test_save_merges_in_memory_state(self, client):
        web_app.sessions["thread-abc"] = {
            "current_tsg": "generated tsg",
            "research_report": "research",
            "review_result": {"approved": True},
            "follow_up_round": 2,
        }
        resp = client.post("/api/sessions", json={"notes": "n", "thread_id": "thread-abc"})
        sid = resp.get_json()["session_id"]
        record = _load_session_record(sid)
        assert record["current_tsg"] == "generated tsg"
        assert record["follow_up_round"] == 2

    @pytest.mark.unit
    def test_load_restores_in_memory_session(self, client):
        sid = "77777777-7777-7777-7777-777777777777"
        _persist_session(
            sid,
            {"notes": "n"},
            {"thread_id": "thread-xyz", "current_tsg": "tsg", "research_report": "r", "follow_up_round": 3},
        )
        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.get_json()["current_tsg"] == "tsg"
        # In-memory session restored for iteration continuity.
        assert web_app.sessions["thread-xyz"]["follow_up_round"] == 3
        assert web_app.sessions["thread-xyz"]["research_report"] == "r"

    @pytest.mark.unit
    def test_load_missing_returns_404(self, client):
        resp = client.get("/api/sessions/88888888-8888-8888-8888-888888888888")
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_invalid_session_id_rejected(self, client):
        assert client.get("/api/sessions/not-a-uuid").status_code == 400
        assert client.delete("/api/sessions/not-a-uuid").status_code == 400

    @pytest.mark.unit
    def test_delete_endpoint(self, client):
        sid = "99999999-9999-9999-9999-999999999999"
        _persist_session(sid, {"notes": "x"}, {})
        assert client.delete(f"/api/sessions/{sid}").status_code == 200
        assert _load_session_record(sid) is None

    @pytest.mark.unit
    def test_rename_endpoint(self, client):
        sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        _persist_session(sid, {"notes": "x"}, {})
        resp = client.put(f"/api/sessions/{sid}/label", json={"label": "Renamed"})
        assert resp.status_code == 200
        assert _load_session_record(sid)["label"] == "Renamed"

    @pytest.mark.unit
    def test_rename_empty_label_rejected(self, client):
        sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        _persist_session(sid, {"notes": "x"}, {})
        assert client.put(f"/api/sessions/{sid}/label", json={"label": "  "}).status_code == 400
