"""Entry point: FastAPI API server."""

import uvicorn

from src.api.app import create_api_app

app = create_api_app()

if __name__ == "__main__":
    uvicorn.run("run_api:app", host="0.0.0.0", port=8000, reload=True)
