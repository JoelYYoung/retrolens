"""
Import smoke tests — verify all public modules import cleanly.
"""

import pytest


def test_import_main_package():
    """Main package exposes __version__."""
    import retrolens
    # Version should be a valid semantic version string
    assert hasattr(retrolens, "__version__")
    assert isinstance(retrolens.__version__, str)
    # Format: X.Y.Z
    parts = retrolens.__version__.split(".")
    assert len(parts) == 3, f"Version should be X.Y.Z format, got: {retrolens.__version__}"
    assert all(p.isdigit() for p in parts), f"Version parts should be numbers: {parts}"


def test_import_models():
    """Core Pydantic models are importable."""
    from retrolens.models import (
        SessionInfo,
        SessionOverview,
        TurnSummary,
        TurnDetail,
        ToolCallDetail,
        DiffResult,
    )
    assert SessionInfo is not None
    assert DiffResult is not None


def test_import_cli():
    """CLI entry point is importable."""
    from retrolens.cli import main
    assert main is not None


def test_import_readers():
    """Reader infrastructure is importable."""
    from retrolens.readers import (
        BaseReader,
        ReaderRegistry,
        create_default_registry,
    )
    assert BaseReader is not None
    assert ReaderRegistry is not None


def test_import_vscode_reader():
    """VS Code Copilot reader is importable."""
    from retrolens.readers.vscode_copilot import VSCodeCopilotReader
    assert VSCodeCopilotReader is not None


def test_import_formatters():
    """Formatter functions are importable."""
    from retrolens import formatters
    assert formatters is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
