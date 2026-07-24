"""Make the repo root importable during tests.

The test modules do `import config`, `import notion_bridge`, `import stt`, etc.
pytest's default (prepend) import mode only puts the `tests/` directory on
sys.path, not the repo root — so `pytest tests/` (the bare console script, as CI
runs it) fails at collection with ModuleNotFoundError on whichever test file is
imported first. A root conftest.py is loaded before any test module is collected,
so inserting the repo root here fixes every invocation (`pytest`, `pytest tests/`,
a single file, or `python -m pytest`) without relying on per-file sys.path hacks.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
