"""
Shared test fixtures and configuration.

Bootstraps v0_src module path so v0/ imports work in tests.
"""

# Importing src.config bootstraps the v0_src package in sys.modules
import src.config  # noqa: F401
