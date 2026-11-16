import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="HTTP wrapper for the IDML renderer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    uvicorn.run(
        "render_api.app:create_app",
        factory=True,
        host=arguments.host,
        port=arguments.port,
        workers=1,
        limit_concurrency=32,
        timeout_graceful_shutdown=15,
        log_level=os.getenv("IDML_API_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
