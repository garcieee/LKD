"""Write a result file that can be traced: the numbers plus the commit, time and library versions they came from."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn

RESULTS = Path(__file__).resolve().parents[1] / "results"


def _clean(value):
    """Plain JSON: numpy numbers become Python numbers, NaN and infinity become null."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent)
        return out.stdout.strip() or None
    except OSError:
        return None


def write_result(name: str, payload: dict, folder: Path | None = None) -> Path:
    """results/<name>.json with a meta block. Returns the path."""
    folder = folder or RESULTS
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"git_commit": _commit(), "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "numpy": np.__version__, "scipy": scipy.__version__, "scikit_learn": sklearn.__version__}
    path = folder / f"{name}.json"
    path.write_text(json.dumps(_clean({"meta": meta, **payload}), indent=2, sort_keys=True) + "\n")
    return path


def md_table(rows: list[dict], columns: list[str], digits: int = 3) -> str:
    """A markdown table from dict rows. Floats are rounded, missing cells are blank."""
    fmt = lambda v: "" if v is None else (f"{v:.{digits}f}" if isinstance(v, float) else str(v))
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    lines += ["| " + " | ".join(fmt(row.get(c)) for c in columns) + " |" for row in rows]
    return "\n".join(lines)
