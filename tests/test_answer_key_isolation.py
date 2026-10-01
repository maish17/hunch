"""The detector must never see the answer key or the generator's world truth. REAL test.

Without this guarantee our headline metric (warning lead time) means nothing: a
detector that peeks at ground_truth.json or generator.json would score perfectly.

Static check over the source of every "ground-system" package. They may not:
  - import p4maint.generator or p4maint.scoring
  - call load_generator_params / load_config("generator")
  - contain a string mentioning answer_key, ground_truth or generator.json
Docstrings and comments are ignored, so explaining the rule in prose is fine.
Only p4maint/generator (writes it) and p4maint/scoring (reads it) are exempt;
p4maint/pipeline.py wires both sides together and is reviewed by hand.
"""

import ast
import unittest

from p4maint.paths import REPO_ROOT

GROUND_SIDE = ["health", "detect", "predict", "diagnose", "workorders", "fleet",
               "dashboard_export", "eventlog", "ingest"]
FORBIDDEN_MODULES = ("p4maint.generator", "p4maint.scoring")
FORBIDDEN_NAMES = {"load_generator_params"}
FORBIDDEN_TEXT = ("answer_key", "ground_truth", "generator.json")


def docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the string nodes that are docstrings (allowed to mention anything)."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def problems_in(path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    allowed_strings = docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_MODULES):
                    found.append(f"line {node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_MODULES) or (module == "p4maint" and any(a.name in ("generator", "scoring") for a in node.names)):
                found.append(f"line {node.lineno}: imports from {module}")
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    found.append(f"line {node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append(f"line {node.lineno}: uses {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.append(f"line {node.lineno}: uses {node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in allowed_strings:
            text = node.value.lower()
            if text == "generator" or any(bad in text for bad in FORBIDDEN_TEXT):
                found.append(f"line {node.lineno}: string {node.value!r}")
    return found


class TestAnswerKeyIsolation(unittest.TestCase):
    def test_ground_side_packages_cannot_reach_the_answer_key(self):
        checked = 0
        for package in GROUND_SIDE:
            for path in sorted((REPO_ROOT / "p4maint" / package).rglob("*.py")):
                checked += 1
                with self.subTest(file=str(path.relative_to(REPO_ROOT))):
                    self.assertEqual(problems_in(path), [])
        self.assertGreater(checked, 10, "expected to find the ground-side modules")

    def test_the_checker_catches_a_violation(self):
        """Guard against the checker silently passing everything."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            cheat = Path(tmp) / "cheat.py"
            cheat.write_text(
                '"""Docstring may say ground_truth."""\n'
                "from p4maint.generator.ground_truth import answer_key_path\n"
                "KEY = 'runs/x/answer_key/ground_truth.json'\n"
            )
            self.assertEqual(len(problems_in(cheat)), 2)


if __name__ == "__main__":
    unittest.main()
