"""Shared test setup: an isolated, offline app.

Imported before anything else in each test module. It makes the tests
independent of your machine:
  - LaunchDarkly and LLM settings are blanked, so the SDK runs offline and
    every flag serves its fallback value (no network, no real project);
  - .env is never read, so your real keys don't leak into tests.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

for name in ("LD_SDK_KEY", "LD_CLIENT_SIDE_ID", "LD_API_TOKEN", "LD_TRIGGER_URL", "LLM_API_KEY"):
    os.environ[name] = ""

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False  # never read the real .env

import logging  # noqa: E402

logging.disable(logging.CRITICAL)  # keep test output readable (incl. the intentional v2 errors)

import app  # noqa: E402,F401  (initializes the offline LaunchDarkly client once)
