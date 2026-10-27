import os
import uvicorn
from backend.db import init_db, records
from backend.settings import layer
from data_generator.seed import seed

if __name__ == "__main__":
    init_db()
    if os.getenv('APP_ENV', 'dev') == 'dev':
        if not records("products") or not records("users"):
            seed()
        if not (layer("gold", "synthetic") / "manifest.json").exists():
            from pipeline.run_pipeline import run_pipeline
            run_pipeline()
        # Startup seeds catalog only; history generation is explicit.
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
