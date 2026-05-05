"""Pytest config — add src/ to path before any test module imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
