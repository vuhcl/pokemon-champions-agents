"""Find setup-module globals not imported from role_compendium."""
import ast
import re
from pathlib import Path

import recommender.role_compendium as rc

setup_path = Path(__file__).resolve().parents[1] / "recommender" / "role_compendium_setup.py"
text = setup_path.read_text()
mod = ast.parse(text)

# names imported from role_compendium in setup module
imported = set()
for node in mod.body:
    if isinstance(node, ast.ImportFrom) and node.module == "recommender.role_compendium":
        for alias in node.names:
            imported.add(alias.name)

defined = set()
for node in mod.body:
    if isinstance(node, ast.FunctionDef):
        defined.add(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                defined.add(t.id)

rc_names = {n for n in dir(rc) if not n.startswith("__")}

# uppercase / _CONST style used in setup body (after imports)
body = text.split("from recommender.role_compendium import", 1)[1]
body = body.split(")", 1)[1]
tokens = set(re.findall(r"\b([A-Z_][A-Z0-9_]*)\b", body))
tokens |= set(re.findall(r"\b(_[a-z][a-z0-9_]*)\b", body))

missing = sorted(
    t
    for t in tokens
    if t not in defined
    and t not in imported
    and t in rc_names
    and t not in {"true", "false", "none"}
)
for n in missing:
    print(n)
