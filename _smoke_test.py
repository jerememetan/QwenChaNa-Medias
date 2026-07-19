"""Quick smoke test for Task 5 wiring."""
import sys
sys.path.insert(0, ".")

from backend.main import create_production_app

app = create_production_app()

# Check routes exist
routes = [r.path for r in app.routes if hasattr(r, 'path')]
assert "/generate" in routes, f"/generate not in {routes}"
assert "/status/{job_id}" in routes or "/status/{job_id}" in [r.path for r in app.routes if hasattr(r, 'path')]

# App creation above verifies production dependency wiring without exposing internals.
print("App created successfully with Video and Voice agents wired in.")
print("Routes:", [r.path for r in app.routes if hasattr(r, 'path')])
