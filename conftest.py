# Ensures the repo root is importable so `import collector` works under pytest.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
