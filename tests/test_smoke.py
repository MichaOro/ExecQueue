"""
Minimal smoke test to validate test infrastructure.
No external services, no production code required.
"""
import pytest


def test_smoke_infrastructure():
    """Verify that pytest is working correctly."""
    assert True


@pytest.mark.asyncio
async def test_async_support():
    """Verify that pytest-asyncio is configured correctly."""
    assert True


def test_fastapi_import():
    """Verify that FastAPI can be imported (optional dependency)."""
    try:
        from fastapi import FastAPI
        assert FastAPI is not None
    except ImportError:
        pytest.skip("FastAPI not installed")


def test_httpx_import():
    """Verify that httpx can be imported (optional dependency)."""
    try:
        import httpx
        assert httpx is not None
    except ImportError:
        pytest.skip("httpx not installed")
