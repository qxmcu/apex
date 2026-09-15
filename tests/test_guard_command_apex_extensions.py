"""
Unit tests for HOL Guard Command Extension for ApexCompress.
Verifies correct classification of apex / apexcompress commands into REVIEW vs ALLOW.
"""

import sys
from pathlib import Path
import unittest

# Ensure src/ is importable
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from codex_plugin_scanner.guard.runtime.command_apex_extensions import (
    classify_apex_command,
    is_apex_command,
    DecisionLevel,
)


class TestGuardCommandApexExtensions(unittest.TestCase):

    def test_non_apex_commands(self):
        self.assertFalse(is_apex_command(["git", "status"]))
        self.assertIsNone(classify_apex_command("git status"))
        self.assertIsNone(classify_apex_command("tar -czf test.tar.gz folder"))
        self.assertIsNone(classify_apex_command(""))

    def test_binary_recognition(self):
        self.assertTrue(is_apex_command(["apex"]))
        self.assertTrue(is_apex_command(["/usr/local/bin/apex"]))
        self.assertTrue(is_apex_command(["apexcompress"]))
        self.assertTrue(is_apex_command(["C:\\bin\\apex.exe"]))

    def test_review_commands(self):
        # Mutating operations must return REVIEW
        review_cases = [
            "apex compress my_dir -o out.apx",
            "apex c file.txt",
            "apex decompress archive.apx -d ./dest",
            "apex extract archive.apx",
            "apex x archive.apx -i '*.json'",
            "apex repair damaged.apx",
            "apex fix damaged.apx",
            "apex heal damaged.apx",
            "/usr/local/bin/apexcompress compress data -m ultra",
            "apexcompress extract vault.apx -p secret",
        ]
        for cmd in review_cases:
            decision = classify_apex_command(cmd)
            self.assertIsNotNone(decision, f"Failed to classify: {cmd}")
            self.assertEqual(decision.level, DecisionLevel.REVIEW, f"Expected REVIEW for: {cmd}")
            self.assertTrue(decision.requires_review)
            self.assertFalse(decision.is_safe)

    def test_safe_commands(self):
        # Read-only inspection operations must return ALLOW
        safe_cases = [
            "apex list archive.apx",
            "apex l archive.apx",
            "apex test archive.apx",
            "apex t archive.apx",
            "apex diff old.apx new.apx",
            "apex d old.apx new.apx --json",
            "apex info file.bin",
            "apex i sample.json",
            "apex completions bash",
            "apex completions zsh",
            "apex benchmark sample.bin",
            "apex b dataset.csv",
            "apex --help",
            "apex -h",
            "apex --version",
            "apex -V",
            "apex",
            "apexcompress list archive.apx",
            "apexcompress test archive.apx",
            "apexcompress diff a.apx b.apx",
        ]
        for cmd in safe_cases:
            decision = classify_apex_command(cmd)
            self.assertIsNotNone(decision, f"Failed to classify: {cmd}")
            self.assertEqual(decision.level, DecisionLevel.ALLOW, f"Expected ALLOW for: {cmd}")
            self.assertTrue(decision.is_safe)
            self.assertFalse(decision.requires_review)

    def test_argv_list_input(self):
        # Can accept list of tokens as well as string
        decision = classify_apex_command(["apex", "compress", "data"])
        self.assertEqual(decision.level, DecisionLevel.REVIEW)

        decision_safe = classify_apex_command(["apex", "diff", "a.apx", "b.apx"])
        self.assertEqual(decision_safe.level, DecisionLevel.ALLOW)


if __name__ == "__main__":
    unittest.main()
