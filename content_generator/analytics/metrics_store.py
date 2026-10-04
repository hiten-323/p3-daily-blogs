"""
SQLite-backed metrics store.

Tables:
  content_metrics     — per-post engagement data
  hook_performance    — rolling averages per hook archetype
  trend_cache         — daily trend snapshots from intelligence layer
  revenue_attribution — revenue / orders per content piece (ROAS engine)
  audience_performance — engagement + revenue breakdown by audience segment
  cta_performance     — CTA click-through and conversion tracking
  posting_time_log    — actual vs optimal posting times per platform

No side effects on import. DB is initialised on first write/read call.
"""
from content_generator.core.ist_dates import today_ist
import os
import sqlite3
import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_DB_PATH    = os.getenv("METRICS_DB_PATH", os.path.join("output", "metrics.db"))
_initialized = False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS content_metrics (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id     TEXT    NOT NULL,
                date           TEXT    NOT NULL,
                views          INTEGER DEFAULT 0,
                retention      REAL    DEFAULT 0,
                shares         INTEGER DEFAULT 0,
                saves          INTEGER DEFAULT 0,
                comments       INTEGER DEFAULT 0,
                viral_score    REAL    DEFAULT 0,
                hook_archetype TEXT    DEFAULT '',
                emotion        TEXT    DEFAULT '',
                objective      TEXT    DEFAULT '',
                platform       TEXT    DEFAULT 'instagram',
                created_at     TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS hook_performance (
                archetype        TEXT PRIMARY KEY,
                avg_views        REAL    DEFAULT 0,
                avg_retention    REAL    DEFAULT 0,
                avg_shares       REAL    DEFAULT 0,
                avg_saves        REAL    DEFAULT 0,
                avg_viral_score  REAL    DEFAULT 0,
                sample_count     INTEGER DEFAULT 0,
                last_updated     TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS trend_cache (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                trend      TEXT NOT NULL,
                velocity   REAL DEFAULT 0,
                source     TEXT DEFAULT '',
                fetched_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS revenue_attribution (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id  TEXT NOT NULL,
                platform    TEXT DEFAULT 'instagram',
                event_type  TEXT DEFAULT 'purchase',
                revenue     REAL DEFAULT 0,
                orders      INTEGER DEFAULT 0,
                audience    TEXT DEFAULT 'consumer',
                spend       REAL DEFAULT 0,
                date        TEXT DEFAULT (date('now')),
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS audience_performance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id  TEXT NOT NULL,
                audience    TEXT NOT NULL,
                views       INTEGER DEFAULT 0,
                engagements INTEGER DEFAULT 0,
                leads       INTEGER DEFAULT 0,
                revenue     REAL DEFAULT 0,
                business_value REAL DEFAULT 0,
                date        TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS cta_performance (
                cta_text    TEXT PRIMARY KEY,
                objective   TEXT DEFAULT '',
                audience    TEXT DEFAULT '',
                clicks      INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                revenue     REAL DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS posting_time_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL,
                hour        INTEGER NOT NULL,
                audience    TEXT DEFAULT 'consumer',
                viral_score REAL DEFAULT 0,
                engagement  INTEGER DEFAULT 0,
                date        TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS leads (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id         TEXT NOT NULL UNIQUE,
                name            TEXT DEFAULT '',
                contact         TEXT DEFAULT '',
                segment         TEXT NOT NULL,
                stage           TEXT NOT NULL DEFAULT 'inquiry',
                source_content  TEXT DEFAULT '',
                source_platform TEXT DEFAULT '',
                score           REAL DEFAULT 0,
                estimated_ltv   REAL DEFAULT 0,
                notes           TEXT DEFAULT '',
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS pipeline_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id     TEXT NOT NULL,
                from_stage  TEXT DEFAULT '',
                to_stage    TEXT NOT NULL,
                notes       TEXT DEFAULT '',
                revenue     REAL DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS nurture_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id     TEXT NOT NULL,
                channel     TEXT DEFAULT 'whatsapp',
                template    TEXT DEFAULT '',
                status      TEXT DEFAULT 'sent',
                message_ref TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS publish_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT NOT NULL,
                day        INTEGER DEFAULT 0,
                platform   TEXT NOT NULL,
                success    INTEGER DEFAULT 0,
                post_id    TEXT DEFAULT '',
                url        TEXT DEFAULT '',
                error      TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_publish_date     ON publish_log(date);
            CREATE INDEX IF NOT EXISTS idx_publish_platform ON publish_log(platform);
            CREATE INDEX IF NOT EXISTS idx_metrics_date    ON content_metrics(date);
            CREATE INDEX IF NOT EXISTS idx_metrics_hook    ON content_metrics(hook_archetype);
            CREATE INDEX IF NOT EXISTS idx_revenue_content ON revenue_attribution(content_id);
            CREATE INDEX IF NOT EXISTS idx_audience_date   ON audience_performance(date);
            CREATE INDEX IF NOT EXISTS idx_leads_segment   ON leads(segment);
            CREATE INDEX IF NOT EXISTS idx_leads_stage     ON leads(stage);
            CREATE INDEX IF NOT EXISTS idx_leads_content   ON leads(source_content);
            CREATE INDEX IF NOT EXISTS idx_pipeline_lead   ON pipeline_events(lead_id);
        """)
    _initialized = True


@contextmanager
def _conn():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Public API ────────────────────────────────────────────────────────────────

def record_metrics(
    content_id: str,
    views: int          = 0,
    retention: float    = 0.0,
    shares: int         = 0,
    saves: int          = 0,
    comments: int       = 0,
    hook_archetype: str = "",
    emotion: str        = "",
    objective: str      = "",
    platform: str       = "instagram",
) -> float:
    """
    Record performance for one content piece.
    Returns the computed viral score.

    Call this the day after posting once you have real metrics:
        from content_generator.analytics.metrics_store import record_metrics
        record_metrics("reel_1", views=54000, retention=68, shares=810, saves=1100)
    """
    _ensure_init()
    from content_generator.analytics.viral_scorer import compute_viral_score
    score = compute_viral_score(views, retention, shares, saves, comments)
    date  = today_ist().isoformat()

    with _conn() as con:
        con.execute("""
            INSERT INTO content_metrics
                (content_id, date, views, retention, shares, saves, comments,
                 viral_score, hook_archetype, emotion, objective, platform)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (content_id, date, views, retention, shares, saves, comments,
              score, hook_archetype, emotion, objective, platform))

    _update_hook_stats(hook_archetype, views, retention, shares, saves, score)
    # score is None until the account has enough history to normalize against;
    # it is stored as NULL rather than 0 so "unscored" stays distinct from "bad".
    if score is None:
        logger.info("[metrics] %s → viral_score unavailable (no account baseline yet)",
                    content_id)
    else:
        logger.info("[metrics] %s → viral_score=%.1f", content_id, score)
    return score


def _update_hook_stats(
    archetype: str,
    views: int, retention: float,
    shares: int, saves: int,
    score: float | None,
) -> None:
    if not archetype:
        return
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM hook_performance WHERE archetype=?", (archetype,)
        ).fetchone()
        if row:
            n = row["sample_count"]
            def _avg(col, new_val):
                return ((row[col] or 0) * n + new_val) / (n + 1)
            # An unscored post (no account baseline yet) must not be folded into
            # the average as a zero — that would read as "this hook performs
            # badly" when the truth is "this hook has not been scored".
            prev = row["avg_viral_score"]
            if score is None:
                new_score = prev
            elif prev is None:
                new_score = score
            else:
                new_score = _avg("avg_viral_score", score)
            con.execute("""
                UPDATE hook_performance SET
                    avg_views=?, avg_retention=?, avg_shares=?, avg_saves=?,
                    avg_viral_score=?, sample_count=sample_count+1,
                    last_updated=datetime('now')
                WHERE archetype=?
            """, (_avg("avg_views", views), _avg("avg_retention", retention),
                  _avg("avg_shares", shares), _avg("avg_saves", saves),
                  new_score, archetype))
        else:
            con.execute("""
                INSERT INTO hook_performance
                    (archetype, avg_views, avg_retention, avg_shares,
                     avg_saves, avg_viral_score, sample_count)
                VALUES (?,?,?,?,?,?,1)
            """, (archetype, views, retention, shares, saves, score))


def get_hook_performance(min_samples: int = 3) -> list[dict]:
    """
    Return hook archetypes ranked by avg viral score.
    Only includes archetypes with at least min_samples data points.
    """
    _ensure_init()
    with _conn() as con:
        rows = con.execute("""
            SELECT archetype, avg_views, avg_viral_score, avg_shares, avg_saves, sample_count
            FROM hook_performance
            WHERE sample_count >= ?
            ORDER BY avg_viral_score DESC
        """, (min_samples,)).fetchall()
    return [dict(r) for r in rows]


def get_recent_metrics(days: int = 14) -> list[dict]:
    """Return all metrics from the last N days, sorted by viral score."""
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM content_metrics WHERE date >= ?
            ORDER BY viral_score DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def store_trends(trends: list[dict]) -> None:
    """Cache trend data from intelligence layer. Auto-expires after 7 days."""
    _ensure_init()
    with _conn() as con:
        con.execute("DELETE FROM trend_cache WHERE fetched_at < datetime('now', '-7 days')")
        for t in trends:
            con.execute(
                "INSERT INTO trend_cache (trend, velocity, source) VALUES (?,?,?)",
                (t.get("trend", ""), t.get("velocity", 0), t.get("source", "")),
            )


def get_cached_trends(max_age_hours: int = 24) -> list[dict]:
    """Return cached trends not older than max_age_hours."""
    _ensure_init()
    with _conn() as con:
        rows = con.execute("""
            SELECT trend, velocity, source, fetched_at FROM trend_cache
            WHERE fetched_at >= datetime('now', ?)
            ORDER BY velocity DESC LIMIT 10
        """, (f"-{max_age_hours} hours",)).fetchall()
    return [dict(r) for r in rows]


# ── Revenue attribution ───────────────────────────────────────────────────────

def record_revenue(
    content_id: str,
    revenue: float,
    orders: int     = 0,
    spend: float    = 0.0,
    platform: str   = "instagram",
    audience: str   = "consumer",
    event_type: str = "purchase",
) -> None:
    """Record revenue attributed to a content piece."""
    _ensure_init()
    with _conn() as con:
        con.execute("""
            INSERT INTO revenue_attribution
                (content_id, platform, event_type, revenue, orders, audience, spend)
            VALUES (?,?,?,?,?,?,?)
        """, (content_id, platform, event_type, revenue, orders, audience, spend))
    logger.info("[metrics] Revenue recorded: %s → Rs %.0f (%d orders)", content_id, revenue, orders)


def get_revenue_by_content(content_id: str) -> dict:
    """Return aggregated revenue stats for one content piece."""
    _ensure_init()
    with _conn() as con:
        row = con.execute("""
            SELECT
                content_id,
                SUM(revenue) AS total_revenue,
                SUM(orders)  AS total_orders,
                SUM(spend)   AS total_spend
            FROM revenue_attribution WHERE content_id=?
        """, (content_id,)).fetchone()
    if not row or row["total_revenue"] is None:
        return {"content_id": content_id, "total_revenue": 0, "total_orders": 0, "roas": 0.0}
    r = dict(row)
    r["roas"] = round(r["total_revenue"] / max(r["total_spend"], 1), 2)
    return r


def get_revenue_leaders(days: int = 30, limit: int = 10) -> list[dict]:
    """Return top revenue-generating content pieces."""
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT
                content_id,
                SUM(revenue) AS total_revenue,
                SUM(orders)  AS total_orders,
                SUM(spend)   AS total_spend,
                platform, audience
            FROM revenue_attribution
            WHERE date >= ?
            GROUP BY content_id
            ORDER BY total_revenue DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["roas"] = round(d["total_revenue"] / max(d["total_spend"], 1), 2)
        result.append(d)
    return result


def get_total_revenue(days: int = 30) -> dict:
    """Return total revenue stats for the last N days."""
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        row = con.execute("""
            SELECT SUM(revenue) AS total_revenue, SUM(orders) AS total_orders,
                   SUM(spend) AS total_spend, COUNT(*) AS conversion_events
            FROM revenue_attribution WHERE date >= ?
        """, (cutoff,)).fetchone()
    if not row or row["total_revenue"] is None:
        return {"total_revenue": 0, "total_orders": 0, "roas": 0.0, "conversion_events": 0}
    d = dict(row)
    d["roas"] = round(d["total_revenue"] / max(d["total_spend"], 1), 2)
    return d


# ── Audience performance ──────────────────────────────────────────────────────

def record_audience_performance(
    content_id: str,
    audience: str,
    views: int          = 0,
    engagements: int    = 0,
    leads: int          = 0,
    revenue: float      = 0.0,
    business_value: float = 0.0,
) -> None:
    """Record audience-segmented performance for a content piece."""
    _ensure_init()
    with _conn() as con:
        con.execute("""
            INSERT INTO audience_performance
                (content_id, audience, views, engagements, leads, revenue, business_value)
            VALUES (?,?,?,?,?,?,?)
        """, (content_id, audience, views, engagements, leads, revenue, business_value))


def get_audience_performance(days: int = 30) -> list[dict]:
    """Return performance aggregated by audience segment."""
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT
                audience,
                COUNT(*)              AS pieces,
                SUM(views)            AS total_views,
                SUM(engagements)      AS total_engagements,
                SUM(leads)            AS total_leads,
                SUM(revenue)          AS total_revenue,
                SUM(business_value)   AS total_business_value,
                AVG(business_value)   AS avg_business_value
            FROM audience_performance
            WHERE date >= ?
            GROUP BY audience
            ORDER BY total_business_value DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


# ── CTA performance ───────────────────────────────────────────────────────────

def record_cta_click(
    cta_text: str,
    objective: str   = "",
    audience: str    = "",
    converted: bool  = False,
    revenue: float   = 0.0,
) -> None:
    """Record a CTA click (and optional conversion)."""
    _ensure_init()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM cta_performance WHERE cta_text=?", (cta_text,)
        ).fetchone()
        if row:
            con.execute("""
                UPDATE cta_performance SET
                    clicks=clicks+1,
                    conversions=conversions+?,
                    revenue=revenue+?,
                    sample_count=sample_count+1,
                    last_updated=datetime('now')
                WHERE cta_text=?
            """, (1 if converted else 0, revenue, cta_text))
        else:
            con.execute("""
                INSERT INTO cta_performance
                    (cta_text, objective, audience, clicks, conversions, revenue, sample_count)
                VALUES (?,?,?,1,?,?,1)
            """, (cta_text, objective, audience, 1 if converted else 0, revenue))


def get_cta_performance(min_clicks: int = 5) -> list[dict]:
    """Return CTAs ranked by conversion rate."""
    _ensure_init()
    with _conn() as con:
        rows = con.execute("""
            SELECT *, CAST(conversions AS REAL)/NULLIF(clicks,0) AS conv_rate
            FROM cta_performance
            WHERE clicks >= ?
            ORDER BY conv_rate DESC
        """, (min_clicks,)).fetchall()
    return [dict(r) for r in rows]


# ── Posting time ──────────────────────────────────────────────────────────────

def record_posting_time(
    platform: str,
    hour: int,
    viral_score: float  = 0.0,
    engagement: int     = 0,
    audience: str       = "consumer",
) -> None:
    """Log actual posting hour alongside performance for time optimisation."""
    _ensure_init()
    with _conn() as con:
        con.execute("""
            INSERT INTO posting_time_log (platform, hour, audience, viral_score, engagement)
            VALUES (?,?,?,?,?)
        """, (platform, hour, audience, viral_score, engagement))


def get_best_posting_hours(platform: str = "instagram", days: int = 90) -> list[dict]:
    """Return posting hours ranked by avg viral score."""
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT hour, AVG(viral_score) AS avg_score, COUNT(*) AS samples
            FROM posting_time_log
            WHERE platform=? AND date >= ?
            GROUP BY hour HAVING samples >= 2
            ORDER BY avg_score DESC
        """, (platform, cutoff)).fetchall()
    return [dict(r) for r in rows]


# ── Lead management ───────────────────────────────────────────────────────────

def upsert_lead(
    lead_id: str,
    segment: str,
    stage: str           = "inquiry",
    name: str            = "",
    contact: str         = "",
    source_content: str  = "",
    source_platform: str = "",
    score: float         = 0.0,
    estimated_ltv: float = 0.0,
    notes: str           = "",
) -> None:
    """Insert or update a lead record."""
    _ensure_init()
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM leads WHERE lead_id=?", (lead_id,)
        ).fetchone()
        if existing:
            con.execute("""
                UPDATE leads SET stage=?, score=?, estimated_ltv=?,
                    notes=?, updated_at=datetime('now')
                WHERE lead_id=?
            """, (stage, score, estimated_ltv, notes, lead_id))
        else:
            con.execute("""
                INSERT INTO leads
                    (lead_id, name, contact, segment, stage,
                     source_content, source_platform, score, estimated_ltv, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (lead_id, name, contact, segment, stage,
                  source_content, source_platform, score, estimated_ltv, notes))


def record_pipeline_event(
    lead_id: str,
    to_stage: str,
    from_stage: str = "",
    notes: str      = "",
    revenue: float  = 0.0,
) -> None:
    """Record a stage transition in the pipeline."""
    _ensure_init()
    with _conn() as con:
        con.execute("""
            INSERT INTO pipeline_events (lead_id, from_stage, to_stage, notes, revenue)
            VALUES (?,?,?,?,?)
        """, (lead_id, from_stage, to_stage, notes, revenue))
        con.execute("""
            UPDATE leads SET stage=?, updated_at=datetime('now') WHERE lead_id=?
        """, (to_stage, lead_id))


def get_leads(
    segment: str = None,
    stage: str   = None,
    days: int    = None,
) -> list[dict]:
    """Return leads optionally filtered by segment, stage, or recency."""
    _ensure_init()
    clauses, params = [], []
    if segment:
        clauses.append("segment=?"); params.append(segment)
    if stage:
        clauses.append("stage=?"); params.append(stage)
    if days:
        cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
        clauses.append("created_at >= ?"); params.append(cutoff)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM leads {where} ORDER BY created_at DESC", params
        ).fetchall()
    return [dict(r) for r in rows]


def get_pipeline_summary() -> dict:
    """Return stage-level counts and LTV for every segment."""
    _ensure_init()
    with _conn() as con:
        rows = con.execute("""
            SELECT segment, stage, COUNT(*) AS count,
                   SUM(estimated_ltv) AS pipeline_value
            FROM leads
            GROUP BY segment, stage
            ORDER BY segment, stage
        """).fetchall()
    summary: dict[str, dict] = {}
    for r in rows:
        seg = r["segment"]
        if seg not in summary:
            summary[seg] = {}
        summary[seg][r["stage"]] = {
            "count":          r["count"],
            "pipeline_value": round(r["pipeline_value"] or 0, 2),
        }
    return summary


def record_nurture_sent(
    lead_id: str,
    channel: str   = "whatsapp",
    template: str  = "",
    status: str    = "sent",
    message_ref: str = "",
) -> None:
    """Log a nurture message sent to a lead."""
    _ensure_init()
    with _conn() as con:
        con.execute("""
            INSERT INTO nurture_log (lead_id, channel, template, status, message_ref)
            VALUES (?,?,?,?,?)
        """, (lead_id, channel, template, status, message_ref))


def record_publish_event(
    platform: str,
    day: int      = 0,
    success: bool = False,
    post_id: str  = "",
    url: str      = "",
    error: str    = None,
) -> None:
    """Log a publish attempt to any social platform."""
    _ensure_init()
    today = today_ist().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO publish_log (date, day, platform, success, post_id, url, error)
            VALUES (?,?,?,?,?,?,?)
        """, (today, day, platform, int(success), post_id or "", url or "", error or ""))


def get_publish_stats(days: int = 30) -> dict:
    """
    Return publishing success rates per platform for the last N days.

    Returns:
        {
            "linkedin":  {"total": 30, "success": 28, "rate": 0.93, "last_url": "..."},
            "instagram": {"total": 30, "success": 25, "rate": 0.83, "last_url": "..."},
            ...
        }
    """
    _ensure_init()
    since = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT platform,
                   COUNT(*)                        AS total,
                   SUM(success)                    AS successes,
                   MAX(CASE WHEN success=1 THEN url ELSE '' END) AS last_url
            FROM   publish_log
            WHERE  date >= ?
            GROUP BY platform
        """, (since,)).fetchall()

    result = {}
    for row in rows:
        total   = row["total"] or 1
        success = row["successes"] or 0
        result[row["platform"]] = {
            "total":    total,
            "success":  success,
            "rate":     round(success / total, 2),
            "last_url": row["last_url"] or "",
        }
    return result
