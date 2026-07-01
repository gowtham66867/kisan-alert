"""SQLite persistence for Kisan Alert."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("SQLITE_DB_PATH", "kisan.db")


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = _conn()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS farmers (
        id TEXT PRIMARY KEY,
        name TEXT,
        phone TEXT UNIQUE,
        village TEXT,
        district TEXT,
        state TEXT DEFAULT 'Andhra Pradesh',
        language TEXT DEFAULT 'te',
        crops TEXT DEFAULT '[]',
        lat REAL,
        lng REAL,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS queries (
        id TEXT PRIMARY KEY,
        farmer_id TEXT,
        phone TEXT,
        input_type TEXT,
        original_text TEXT,
        translated_text TEXT,
        language TEXT,
        crop TEXT,
        issue_type TEXT,
        severity TEXT,
        advisory TEXT,
        image_url TEXT,
        lat REAL,
        lng REAL,
        village TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        village TEXT,
        district TEXT,
        alert_type TEXT,
        message TEXT,
        message_local TEXT,
        language TEXT,
        severity TEXT,
        sent_at TEXT
    );
    """)
    con.commit()
    con.close()


def save_query(q: dict) -> str:
    qid = q.get("id") or str(uuid.uuid4())[:8]
    q["id"] = qid
    q["created_at"] = datetime.now(timezone.utc).isoformat()
    con = _conn()
    con.execute("""
        INSERT OR REPLACE INTO queries
        (id, farmer_id, phone, input_type, original_text, translated_text,
         language, crop, issue_type, severity, advisory, image_url,
         lat, lng, village, created_at)
        VALUES (:id, :farmer_id, :phone, :input_type, :original_text, :translated_text,
                :language, :crop, :issue_type, :severity, :advisory, :image_url,
                :lat, :lng, :village, :created_at)
    """, {**{"farmer_id": "", "phone": "", "input_type": "text", "original_text": "",
             "translated_text": "", "language": "en", "crop": "", "issue_type": "",
             "severity": "Medium", "advisory": "", "image_url": "", "lat": 0.0,
             "lng": 0.0, "village": ""}, **q})
    con.commit()
    con.close()
    return qid


def get_queries(district: str = "", limit: int = 200) -> list[dict]:
    con = _conn()
    if district:
        rows = con.execute(
            "SELECT * FROM queries WHERE village LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{district}%", limit)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM queries ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    con = _conn()
    total = con.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    crops = con.execute(
        "SELECT crop, COUNT(*) as c FROM queries WHERE crop != '' GROUP BY crop ORDER BY c DESC"
    ).fetchall()
    issues = con.execute(
        "SELECT issue_type, COUNT(*) as c FROM queries WHERE issue_type != '' GROUP BY issue_type ORDER BY c DESC"
    ).fetchall()
    severity = con.execute(
        "SELECT severity, COUNT(*) as c FROM queries GROUP BY severity"
    ).fetchall()
    con.close()
    return {
        "total_queries": total,
        "crops": {r[0]: r[1] for r in crops},
        "issue_types": {r[0]: r[1] for r in issues},
        "severity": {r[0]: r[1] for r in severity},
    }


def save_alert(a: dict) -> str:
    aid = str(uuid.uuid4())[:8]
    a["id"] = aid
    a["sent_at"] = datetime.now(timezone.utc).isoformat()
    con = _conn()
    con.execute("""
        INSERT INTO alerts (id, village, district, alert_type, message, message_local, language, severity, sent_at)
        VALUES (:id, :village, :district, :alert_type, :message, :message_local, :language, :severity, :sent_at)
    """, {**{"village": "", "district": "", "alert_type": "", "message": "",
             "message_local": "", "language": "en", "severity": "Medium"}, **a})
    con.commit()
    con.close()
    return aid


def get_alerts(limit: int = 50) -> list[dict]:
    con = _conn()
    rows = con.execute("SELECT * FROM alerts ORDER BY sent_at DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
