from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "rainfall_ca.api:app",
        host=os.getenv("RAINFALL_HOST", "127.0.0.1"),
        port=int(os.getenv("RAINFALL_PORT", "8000")),
        reload=False,
        app_dir="src",
    )
