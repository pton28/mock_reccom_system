"""Structured stage logs. Explicit allowlist prevents raw PII/credentials leaking."""
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from backend.settings import layer

FIELDS = set("event_id event_name user_id product_id session_id request_id run_id origin environment source stage status count inserted duplicates rejected path reason duration_ms cutoff rows page checkpoint attempt status_code scenario seed metrics".split())


def audit(stage, **fields):
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "stage": stage,
              **{k: v for k, v in fields.items() if k in FIELDS}}
    logger = logging.getLogger("nutee.audit")
    target = str(layer("logs") / "audit.jsonl")
    if not logger.handlers or getattr(logger, "target", None) != target:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        stream = logging.StreamHandler()
        file = RotatingFileHandler(target, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
        for handler in [stream, file]:
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.target = target
    logger.info(json.dumps(record, default=str, ensure_ascii=False))
