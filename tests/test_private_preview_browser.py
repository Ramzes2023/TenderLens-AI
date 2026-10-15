"""Offline browser startup failures must stay nonzero and identify dependencies."""
import builtins
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

from ops.private_preview.browser_smoke import run


class BrowserStartupTests(unittest.TestCase):
    def test_missing_playwright_fails_before_any_journey(self):
        original_import = builtins.__import__

        def missing(name, *args, **kwargs):
            if name == "playwright.sync_api":
                raise ModuleNotFoundError("sensitive exception text", name="playwright")
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("os.environ", {}, clear=True), \
                patch("builtins.__import__", side_effect=missing), \
                contextlib.redirect_stdout(output):
            self.assertEqual(run(directory), 1)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 7)
        self.assertIn("PRIVATE_GUEST=FAIL browser dependency missing: playwright", lines[0])
        self.assertIn("requirements.browser.txt", lines[0])
        self.assertTrue(all("=NOT_VERIFIED journey not reached" in line for line in lines[1:]))
        self.assertNotIn("sensitive exception text", output.getvalue())
