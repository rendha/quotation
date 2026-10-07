"""
python tools/check_decimal_fields.py

Postgres is strict where SQLite is relaxed.  A DecimalField(max_digits=12, decimal_places=12) can only hold values BELOW 1; SQLite accepts
bigger numbers anyway, Postgres stops with "numeric field overflow".  This lists every DecimalField of quotations/models.py and of the
migrations, and marks the ones that cannot hold what they should.  It only READS your files.
"""
import ast
import pathlib
import sys
from decimal import Decimal, InvalidOperation


def _const(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _default_number(node):
    """The default as a number, when it is one (default=85, default=Decimal("0.85"), default=0.85)."""
    if node is None:
        return None
    if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "Decimal" and node.args:
        text = _const(node.args[0])
    else:
        text = _const(node)
    try:
        return Decimal(str(text)) if text is not None and not isinstance(text, bool) else None
    except InvalidOperation:
        return None


def _is_decimal_field(call):
    return isinstance(call, ast.Call) and getattr(call.func, "attr", getattr(call.func, "id", "")) == "DecimalField"


def _names(tree):
    """id(DecimalField call) -> 'Model.field' / 'field', read from the usual shapes of models.py and of migrations."""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):                                                     # class Quotation: margin_factor = DecimalField(...)
            for item in node.body:
                if isinstance(item, ast.Assign) and _is_decimal_field(item.value) and isinstance(item.targets[0], ast.Name):
                    names[id(item.value)] = "%s.%s" % (node.name, item.targets[0].id)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("AddField", "AlterField"):          # migrations.AlterField(name=..., field=...)
            kw = {k.arg: k.value for k in node.keywords}
            if "field" in kw and _is_decimal_field(kw["field"]):
                names[id(kw["field"])] = "%s.%s  (%s)" % (_const(kw.get("model_name")) or "?", _const(kw.get("name")) or "?", node.func.attr)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "CreateModel":                       # migrations.CreateModel(fields=[("x", DecimalField)])
            kw = {k.arg: k.value for k in node.keywords}
            model = _const(kw.get("name")) or "?"
            fields = kw.get("fields")
            if isinstance(fields, ast.List):
                for element in fields.elts:
                    if isinstance(element, ast.Tuple) and len(element.elts) == 2 and _is_decimal_field(element.elts[1]):
                        names[id(element.elts[1])] = "%s.%s  (CreateModel)" % (model, _const(element.elts[0]) or "?")
    return names


def scan(root):
    """-> list of dicts: file, line, field, max_digits, decimal_places, default, problem ('' when fine)."""
    root = pathlib.Path(root)
    files = [root / "quotations" / "models.py"] + sorted((root / "quotations" / "migrations").glob("0*.py"))
    found = []
    for path in files:
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        names = _names(tree)
        for node in ast.walk(tree):
            if not _is_decimal_field(node):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            digits, places = _const(kw.get("max_digits")), _const(kw.get("decimal_places"))
            default = _default_number(kw.get("default"))
            problem = ""
            if isinstance(digits, int) and isinstance(places, int):
                if places >= digits:
                    problem = "ONLY VALUES BELOW 1 FIT (Postgres refuses 83.5, 19 ...)"
                elif default is not None and abs(default) >= Decimal(10) ** (digits - places):
                    problem = "THE DEFAULT %s DOES NOT FIT" % default
            found.append({"file": str(path.relative_to(root)).replace("\\", "/"), "line": node.lineno, "field": names.get(id(node), "?"),
                          "max_digits": digits, "decimal_places": places, "default": ast.unparse(kw["default"]) if "default" in kw else "", "problem": problem})
    return found


def main():
    root = pathlib.Path.cwd()
    rows = scan(root)
    if not rows:
        print("No DecimalField found. Run this from the folder that contains manage.py.")
        return 1
    bad = [r for r in rows if r["problem"]]
    print("%d decimal fields checked (models and migrations).\n" % len(rows))
    if bad:
        print("PROBLEMS (these stop Postgres):")
        for r in bad:
            print("  %s line %d   %s   max_digits=%s decimal_places=%s default=%s\n      -> %s" % (
                r["file"], r["line"], r["field"], r["max_digits"], r["decimal_places"], r["default"] or "-", r["problem"]))
    else:
        print("No problem found in the decimal fields.")
    print("\nALL decimal fields:")
    for r in rows:
        print("  %-52s line %-4d %-34s (%s,%s)  default=%s" % (r["file"], r["line"], r["field"], r["max_digits"], r["decimal_places"], r["default"] or "-"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
