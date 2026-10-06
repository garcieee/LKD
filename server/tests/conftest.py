"""The tests never touch the real db/: importing app.main builds an app there, so point it at a temp folder first."""
import os
import tempfile

os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="lakad-tests-"))
