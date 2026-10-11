"""Even direct pytest invocation must not drive a retargeted physical device."""
import pytest
from tools import ha_lab


@pytest.fixture(scope="session", autouse=True)
def require_virtual_target():
    ha_lab.ensure_virtual_target()
