"""
python tools/check_assets.py

Windows ignores capital letters in file names, a Linux server does not.  This lists every file the PDF needs
(read from the PDF templates and pdf_generator.py) and checks that it exists with EXACTLY that spelling.
It prints what to rename if something differs.  Run it from the project folder (where manage.py is) before you deploy.
"""
import pathlib
import re
import sys


def required_files(root):
    design = pathlib.Path(root) / "quotations" / "pdf_design"
    names = set()
    for template in (design / "templates").glob("*.html"):
        names |= set(re.findall(r"\{\{\s*assets\s*\}\}([\w./ -]+?)[\"')\s]", template.read_text(encoding="utf-8")))
    generator = pathlib.Path(root) / "quotations" / "pdf_generator.py"
    names |= set(re.findall(r'ASSETS_DIR\s*/\s*"([^"]+)"', generator.read_text(encoding="utf-8")))
    return sorted(names)


def find_problems(root):
    """-> list of (wanted name, what is really there or None)."""
    assets = pathlib.Path(root) / "quotations" / "pdf_design" / "assets"
    problems = []
    for wanted in required_files(root):
        folder, _, name = (assets / wanted).as_posix().rpartition("/")
        present = {p.name for p in pathlib.Path(folder).iterdir()} if pathlib.Path(folder).is_dir() else set()
        if name in present:
            continue
        lookalike = [p for p in present if p.lower() == name.lower()]
        problems.append((wanted, lookalike[0] if lookalike else None))
    return problems


def main():
    root = pathlib.Path.cwd()
    needed = required_files(root)
    problems = find_problems(root)
    print("The PDF needs %d files:" % len(needed))
    for name in needed:
        print("   ", name)
    if not problems:
        print("\nOK: every file exists with exactly this spelling.")
        return 0
    print("\nPROBLEM - these would break the PDF on a Linux server:")
    for wanted, actual in problems:
        print("   wanted '%s'  ->  %s" % (wanted, "found as '%s': rename it" % actual if actual else "NOT FOUND"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
