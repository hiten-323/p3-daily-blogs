"""
Purity Beans — Autonomous AI Marketing → Lead → Sales → Revenue Engine.
Minimal __init__ — no side effects on import.
Logging and environment loading are the caller's responsibility.
Call configure() explicitly if you want the built-in defaults.

Quick start:
    from content_generator import generate_daily_content, save_content, configure
    configure(load_env=True, setup_logging=True)
    content = generate_daily_content()
    save_content(content)

Autonomous mode (runs research + generation + editorial + nurture):
    from content_generator import run_daily_pipeline
    run_daily_pipeline()

Feed performance data back so the engine learns:
    from content_generator import record_metrics
    record_metrics("reel_1", views=54000, retention=68, shares=810, saves=1100,
                   hook_archetype="EXPOSE", emotion="REBELLION")

Capture and manage leads (Sales Engine):
    from content_generator import record_lead, advance_stage, close_deal

    lead_id = record_lead(
        segment="distributor",
        contact="+919876543210",
        name="Rajesh Sharma",
        source_content="reel_1_day42",
        source_platform="instagram",
        engagement_type="direct_dm",
    )
    advance_stage(lead_id, notes="Sample sent to Nagpur warehouse")
    close_deal(lead_id, revenue=900_000, notes="6-month agreement signed")
"""


__all__ = [
    # Core pipeline
    "generate_daily_content",
    "save_content",
    "configure",
    # Autonomous runner
    "run_daily_pipeline",
    # Performance feedback
    "record_metrics",
    "record_conversion",
    "generate_tracking_url",
    # Sales Engine — lead lifecycle
    "record_lead",
    "advance_stage",
    "close_deal",
]


def configure(load_env: bool = True, setup_logging: bool = False) -> None:
    """
    Optional initialisation helper for script/CLI use.
    Libraries should NOT call this — let the application control logging.

    Args:
        load_env:      Load .env file for local development.
        setup_logging: Configure a basic console logger (disable if the
                       calling app already configures logging).
    """
    if load_env:
        _load_env()
    if setup_logging:
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def _load_env() -> None:
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(here, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# run_daily_pipeline is resolved lazily (PEP 562). Importing it eagerly put
# content_generator.scheduler.daily into sys.modules before runpy executed it,
# so `python -m content_generator.scheduler.daily` — the workflow's only entry
# point — ran the module twice under two names ("...daily" and "__main__"),
# each with its own copy of every module-level object. That is what the
# RuntimeWarning in the run logs was reporting. The public name is unchanged.
def __getattr__(name):
    if name in ("generate_daily_content", "save_content"):
        from content_generator.pipeline import generator
        return getattr(generator, name)
    if name == "record_metrics":
        from content_generator.analytics.metrics_store import record_metrics
        return record_metrics
    if name in ("record_conversion", "generate_tracking_url"):
        from content_generator.analytics import attribution
        return getattr(attribution, name)
    if name == "record_lead":
        from content_generator.leads.lead_capture import record_lead
        return record_lead
    if name in ("advance_stage", "close_deal"):
        from content_generator.crm import pipeline_tracker
        return getattr(pipeline_tracker, name)
    if name == "run_daily_pipeline":
        from content_generator.scheduler.daily import run_now
        return run_now
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
