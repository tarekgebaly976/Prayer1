"""Regression guard: the request DB session must commit BEFORE the response is sent (read-your-writes).
A plain Depends(get_db) ends after the response, letting a client or another worker observe uncommitted state
(found by load testing: first request after login returned 401)."""

import pathlib
import re


def test_every_get_db_dependency_is_function_scoped():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in root.rglob("*.py"):
        for m in re.finditer(r"Depends\(get_db[^)]*\)", f.read_text()):
            if 'scope="function"' not in m.group(0):
                offenders.append(f"{f.relative_to(root)}: {m.group(0)}")
    assert not offenders, offenders
