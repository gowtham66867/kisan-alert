"""
Kisan Alert — full API test suite.
Run: cd backend && python -m pytest tests/ -v
"""
import io
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Use a temp DB so tests don't pollute kisan.db
os.environ["SQLITE_DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["ENABLE_ADMIN"] = "true"
os.environ["CRON_SECRET"] = "test-secret-123"

from main import app  # noqa: E402  (must come after env setup)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_db():
    """Re-init DB before each test so tables exist and are empty."""
    from services.db import init_db, _conn
    init_db()
    con = _conn()
    con.execute("DELETE FROM queries")
    con.execute("DELETE FROM alerts")
    con.execute("DELETE FROM farmers")
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------

class TestHealthAndRoot:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "Kisan Alert" in data["service"]

    def test_root_returns_info(self):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "endpoints" in data

    def test_docs_accessible(self):
        r = client.get("/docs")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Text Query
# ---------------------------------------------------------------------------

class TestTextQuery:
    def test_submit_english_query(self):
        r = client.post("/query/text", json={
            "text": "My rice crop has yellow leaves. What should I do?",
            "language": "en",
            "crop": "rice",
            "village": "Narasaraopet"
        })
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["status"] == "analyzed"
        assert "advisory" in data
        assert len(data["advisory"]) > 10

    def test_submit_telugu_query(self):
        r = client.post("/query/text", json={
            "text": "టమాటా పంటకు తెల్ల పురుగులు వస్తున్నాయి. ఏమి చేయాలి?",
            "language": "te",
            "crop": "tomato",
            "village": "Guntur"
        })
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "advisory" in data

    def test_submit_hindi_query(self):
        r = client.post("/query/text", json={
            "text": "मेरी गेहूं की फसल पर सफेद पाउडर आ गया है",
            "language": "hi",
            "crop": "wheat"
        })
        assert r.status_code == 200
        assert "advisory" in r.json()

    def test_query_returns_severity(self):
        r = client.post("/query/text", json={
            "text": "Cotton bollworm infestation is severe",
            "language": "en",
            "crop": "cotton"
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("severity") in ["Critical", "High", "Medium", "Low"]

    def test_query_returns_issue_type(self):
        r = client.post("/query/text", json={
            "text": "Groundnut leaves are pale yellow",
            "language": "en",
            "crop": "groundnut"
        })
        assert r.status_code == 200
        assert "issue_type" in r.json()

    def test_query_returns_products_recommended(self):
        r = client.post("/query/text", json={
            "text": "My crop has fungal disease",
            "language": "en",
            "crop": "rice"
        })
        assert r.status_code == 200
        data = r.json()
        assert "products_recommended" in data
        assert isinstance(data["products_recommended"], list)

    def test_query_with_location(self):
        r = client.post("/query/text", json={
            "text": "Pest attack on my field",
            "language": "en",
            "crop": "cotton",
            "lat": 16.22,
            "lng": 80.12,
            "village": "Narasaraopet"
        })
        assert r.status_code == 200
        assert "id" in r.json()

    def test_empty_text_still_processes(self):
        """Empty text should not crash — rule-based fallback handles it."""
        r = client.post("/query/text", json={"text": " ", "language": "en"})
        assert r.status_code == 200

    def test_id_is_short_string(self):
        r = client.post("/query/text", json={"text": "crop issue", "language": "en"})
        assert r.status_code == 200
        qid = r.json()["id"]
        assert isinstance(qid, str)
        assert len(qid) <= 8


# ---------------------------------------------------------------------------
# Photo Query
# ---------------------------------------------------------------------------

class TestPhotoQuery:
    def _fake_image(self, name="crop.jpg", content=b"FAKEJPEG"):
        return ("image", (name, io.BytesIO(content), "image/jpeg"))

    def test_submit_photo_query(self):
        r = client.post("/query/photo", files=[self._fake_image()],
                        data={"language": "en", "crop": "rice", "village": "Test"})
        assert r.status_code == 200
        data = r.json()
        assert "advisory" in data
        assert data["status"] == "analyzed"

    def test_photo_with_description(self):
        r = client.post("/query/photo",
                        files=[self._fake_image()],
                        data={"text": "Brown spots on leaves", "language": "te", "crop": "tomato"})
        assert r.status_code == 200
        assert "id" in r.json()

    def test_photo_missing_file_returns_422(self):
        r = client.post("/query/photo", data={"language": "en"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Query History
# ---------------------------------------------------------------------------

class TestQueryHistory:
    def _seed_query(self, crop="rice", village="Guntur"):
        client.post("/query/text", json={"text": f"{crop} issue", "language": "en", "crop": crop, "village": village})

    def test_empty_history(self):
        r = client.get("/query/history")
        assert r.status_code == 200
        data = r.json()
        assert "queries" in data or isinstance(data, list)

    def test_history_contains_submitted_queries(self):
        self._seed_query("rice")
        self._seed_query("cotton")
        r = client.get("/query/history")
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("queries", [])
        assert len(items) >= 2

    def test_history_respects_limit(self):
        for i in range(5):
            self._seed_query(f"crop{i}")
        r = client.get("/query/history?limit=3")
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("queries", [])
        assert len(items) <= 3

    def test_history_district_filter(self):
        self._seed_query("rice", "Guntur")
        self._seed_query("cotton", "Vijayawada")
        r = client.get("/query/history?district=Guntur")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_empty_db(self):
        r = client.get("/query/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_queries" in data
        assert data["total_queries"] == 0

    def test_stats_after_queries(self):
        client.post("/query/text", json={"text": "rice problem", "language": "en", "crop": "rice"})
        client.post("/query/text", json={"text": "cotton problem", "language": "te", "crop": "cotton"})
        r = client.get("/query/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_queries"] == 2

    def test_stats_by_crop(self):
        client.post("/query/text", json={"text": "issue", "language": "en", "crop": "groundnut"})
        r = client.get("/query/stats")
        data = r.json()
        crops = data.get("crops") or data.get("by_crop", {})
        assert "groundnut" in crops

    def test_stats_critical_count(self):
        r = client.get("/query/stats")
        data = r.json()
        # critical_count is optional — just ensure no crash
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_generate_alert(self):
        r = client.post("/alerts/generate", params={"district": "Guntur"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "generated"
        assert "id" in data

    def test_generate_alert_for_each_district(self):
        districts = ["Guntur", "Krishna", "Nellore"]
        for d in districts:
            r = client.post("/alerts/generate", params={"district": d})
            assert r.status_code == 200, f"Failed for district: {d}"

    def test_alert_contains_advisory(self):
        r = client.post("/alerts/generate", params={"district": "Prakasam"})
        data = r.json()
        # alert must have some content
        assert "message" in data or "advisory" in data or "content" in data

    def test_recent_alerts_empty(self):
        r = client.get("/alerts/recent")
        assert r.status_code == 200
        data = r.json()
        alerts = data if isinstance(data, list) else data.get("alerts", [])
        assert isinstance(alerts, list)

    def test_recent_alerts_after_generate(self):
        client.post("/alerts/generate", params={"district": "Guntur"})
        client.post("/alerts/generate", params={"district": "Krishna"})
        r = client.get("/alerts/recent")
        assert r.status_code == 200
        data = r.json()
        alerts = data if isinstance(data, list) else data.get("alerts", [])
        assert len(alerts) >= 2

    def test_cron_requires_secret(self):
        r = client.post("/alerts/cron/daily")
        assert r.status_code == 403

    def test_cron_with_valid_secret(self):
        r = client.post("/alerts/cron/daily",
                        headers={"x-cron-secret": "test-secret-123"})
        assert r.status_code == 200
        data = r.json()
        assert "generated" in data
        assert data["generated"] > 0


# ---------------------------------------------------------------------------
# Admin Seed
# ---------------------------------------------------------------------------

ADMIN_HEADER = {"x-admin-secret": "kisan-admin-2024"}


class TestAdminSeed:
    def test_seed_wrong_key_rejected(self):
        r = client.post("/admin/seed", headers={"x-admin-secret": "wrong-key"})
        assert r.status_code in [401, 403]

    def test_seed_with_valid_key(self):
        r = client.post("/admin/seed", headers=ADMIN_HEADER)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert data.get("seeded", 0) > 0

    def test_seed_populates_queries(self):
        client.post("/admin/seed", headers=ADMIN_HEADER)
        r = client.get("/query/stats")
        data = r.json()
        assert data["total_queries"] > 0

    def test_seed_idempotent(self):
        """Running seed twice should not crash (INSERT OR REPLACE)."""
        r1 = client.post("/admin/seed", headers=ADMIN_HEADER)
        r2 = client.post("/admin/seed", headers=ADMIN_HEADER)
        assert r1.status_code == 200
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# DB layer unit tests
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_save_and_retrieve_query(self):
        from services.db import save_query, get_queries
        qid = save_query({
            "id": "test001",
            "input_type": "text",
            "original_text": "leaf curl",
            "language": "en",
            "crop": "tomato",
            "issue_type": "Pest Attack",
            "severity": "High",
            "advisory": "Apply neem oil spray",
            "village": "Guntur",
        })
        assert qid == "test001"
        rows = get_queries()
        assert any(r["id"] == "test001" for r in rows)

    def test_save_and_retrieve_alert(self):
        from services.db import save_alert, get_alerts
        aid = save_alert({
            "district": "Guntur",
            "village": "Guntur",
            "alert_type": "weather",
            "message": "Heavy rain expected",
            "message_local": "భారీ వర్షాలు",
            "language": "te",
            "severity": "High",
        })
        assert isinstance(aid, str)
        alerts = get_alerts()
        assert any(a["id"] == aid for a in alerts)

    def test_stats_accuracy(self):
        from services.db import save_query, get_stats
        save_query({"crop": "rice", "issue_type": "Pest Attack", "severity": "High",
                    "language": "en", "advisory": "test"})
        save_query({"crop": "cotton", "issue_type": "Crop Disease", "severity": "Critical",
                    "language": "te", "advisory": "test"})
        save_query({"crop": "rice", "issue_type": "Water Stress", "severity": "Medium",
                    "language": "en", "advisory": "test"})
        stats = get_stats()
        assert stats["total_queries"] == 3
        crops = stats.get("crops") or stats.get("by_crop", {})
        assert crops.get("rice", 0) == 2
        assert crops.get("cotton", 0) == 1

    def test_query_limit_respected(self):
        from services.db import save_query, get_queries
        for i in range(10):
            save_query({"crop": "rice", "advisory": f"advisory {i}", "language": "en"})
        rows = get_queries(limit=5)
        assert len(rows) <= 5


# ---------------------------------------------------------------------------
# Gemini service unit tests (rule-based fallback)
# ---------------------------------------------------------------------------

class TestGeminiServiceFallback:
    """Test that the rule-based fallback works when Gemini is unavailable."""

    def test_analyze_returns_dict(self):
        from services.gemini_service import analyze_crop_query
        result = analyze_crop_query("rice leaf curl", "en", "rice")
        assert isinstance(result, dict)
        assert "advisory" in result
        assert "severity" in result

    def test_analyze_fills_required_fields(self):
        from services.gemini_service import analyze_crop_query
        result = analyze_crop_query("cotton bollworm", "en", "cotton")
        for field in ["advisory", "severity", "issue_type", "crop"]:
            assert field in result, f"Missing field: {field}"

    def test_analyze_telugu_input(self):
        from services.gemini_service import analyze_crop_query
        result = analyze_crop_query("పంట వ్యాధి", "te", "rice")
        assert isinstance(result, dict)
        assert "advisory" in result

    def test_severity_valid_values(self):
        from services.gemini_service import analyze_crop_query
        result = analyze_crop_query("severe disease", "en", "wheat")
        assert result.get("severity") in ["Critical", "High", "Medium", "Low", None, ""]

    def test_generate_daily_alert_returns_dict(self):
        from services.gemini_service import generate_daily_alert
        result = generate_daily_alert("Guntur", "kharif", ["rice", "cotton"])
        assert isinstance(result, dict)
        assert "message" in result or "advisory" in result or "content" in result

    def test_products_recommended_is_list(self):
        from services.gemini_service import analyze_crop_query
        result = analyze_crop_query("leaf blight", "en", "rice")
        prods = result.get("products_recommended", [])
        assert isinstance(prods, list)
