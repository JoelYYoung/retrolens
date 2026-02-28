"""
Listener - Data Capture Layer

Responsible for intercepting and storing communication data between Agent and API.

Modules:
- adapter.py  : FastAPI proxy server, intercepts requests/responses
- storage.py  : Session data persistence storage
"""

from .storage import SessionStorage, get_storage, get_or_create_session, reset_session

__all__ = [
    "SessionStorage",
    "get_storage",
    "get_or_create_session",
    "reset_session",
]
