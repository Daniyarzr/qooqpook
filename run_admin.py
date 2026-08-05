"""Entry point: Admin panel."""

import uvicorn

from src.admin.app import create_admin_app

app = create_admin_app()

if __name__ == "__main__":
    uvicorn.run("run_admin:app", host="0.0.0.0", port=8001, reload=True)
