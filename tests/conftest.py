"""Shared pytest configuration for the Sirius Rangehood tests.

Home Assistant's test harness (``pytest-homeassistant-custom-component``)
provides the ``hass`` fixture and the ``enable_custom_integrations`` fixture.
Repo root is added to ``sys.path`` via ``pythonpath = .`` in ``pytest.ini`` so
``custom_components`` is importable from any checkout.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the custom integration in every test that needs it."""
    yield
