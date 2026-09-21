import ast
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ALLOWED_IMPORTS = {
    "contracts": frozenset(),
    "email_classification": frozenset({"contracts"}),
    "document_extraction": frozenset({"contracts"}),
    "verification": frozenset({"contracts"}),
    "pipeline": frozenset({"contracts"}),
    "frontend": frozenset(
        {"contracts", "document_extraction", "email_classification", "verification"}
    ),
}


def imported_roots(source_file):
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class ModuleBoundaryTests(unittest.TestCase):
    def test_every_source_package_is_declared(self):
        packages = {
            path.name
            for path in SRC.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        self.assertEqual(
            packages,
            set(ALLOWED_IMPORTS),
            "A new src package must declare its allowed dependencies here",
        )

    def test_modules_only_depend_on_the_shared_contract(self):
        for package, allowed in sorted(ALLOWED_IMPORTS.items()):
            for source_file in sorted((SRC / package).rglob("*.py")):
                with self.subTest(module=str(source_file.relative_to(SRC))):
                    siblings = imported_roots(source_file) & set(ALLOWED_IMPORTS)
                    siblings.discard(package)
                    forbidden = sorted(siblings - allowed)
                    self.assertEqual(
                        forbidden,
                        [],
                        f"{source_file.relative_to(SRC)} may not import {forbidden}",
                    )

    def test_contracts_package_is_standalone(self):
        for source_file in sorted((SRC / "contracts").rglob("*.py")):
            with self.subTest(module=source_file.name):
                self.assertEqual(
                    imported_roots(source_file) & set(ALLOWED_IMPORTS),
                    set(),
                    "contracts must not depend on any pipeline module",
                )


if __name__ == "__main__":
    unittest.main()
