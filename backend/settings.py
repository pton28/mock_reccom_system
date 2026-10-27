import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def data_dir():
    path = Path(os.getenv("NUTEE_DATA_DIR", str(ROOT / "data" / "product-demo-v1"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def layer(name, origin=None):
    if origin not in {None, "synthetic", "real"}:
        raise ValueError("origin must be synthetic or real")
    path = data_dir() / origin / name if origin else data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def pipeline_config():
    import json
    return json.loads((ROOT / "configs/pipeline.json").read_text())
