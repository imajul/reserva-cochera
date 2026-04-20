"""
Mock playwright before reservar_cochera is imported so unit tests
can run without the browser binaries installed.
"""

import sys
from unittest.mock import MagicMock

if "playwright" not in sys.modules:
    sys.modules["playwright"] = MagicMock()
    sys.modules["playwright.sync_api"] = MagicMock()
