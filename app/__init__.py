"""Face API — a portable, production-ready Face Detection & Recognition REST API.

Package layout:
    app.config      configuration + plan/limit definitions
    app.engine      OpenCV YuNet (detection) + SFace (recognition) wrapper
    app.storage     SQLite persistence: API keys, usage events, face collections
    app.security    API-key authentication + rate limiting dependencies
    app.routes.*    HTTP endpoints
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
