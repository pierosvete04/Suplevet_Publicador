"""Revisa que la carpeta app/ armada tenga todos los módulos propios que importa el código (si falta uno, el
programa no arranca después de actualizar). Uso: python instalador/revisar_app.py dist/PublicadorSuplevet/app"""
import ast
import sys
from pathlib import Path

app = Path(sys.argv[1])
propios = {p.stem for p in app.glob("*.py")} | {p.name for p in app.iterdir() if p.is_dir()}
fuente = Path(__file__).resolve().parent.parent
del_repo = {p.stem for p in fuente.glob("*.py")} | {p.name for p in fuente.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
faltan = set()
for f in app.rglob("*.py"):
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        nombres = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.module and not n.level else []
        for m in nombres:
            raiz = m.split(".")[0]
            if raiz in del_repo and raiz not in propios:
                faltan.add(raiz)
if faltan:
    print("Faltan en app/:", ", ".join(sorted(faltan)))
    sys.exit(1)
print(f"app/ completa: {len(propios)} módulos")
