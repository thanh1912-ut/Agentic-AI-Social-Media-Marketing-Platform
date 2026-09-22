"""Run the API with ``python -m services.api``."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8000, reload=False)

