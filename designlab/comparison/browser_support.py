"""Use an explicit browser, the existing ARM install, or Playwright's default."""
from pathlib import Path
import os


def launch_chromium(playwright):
    executable = os.environ.get("PW_CHROMIUM")
    if not executable:
        cached = sorted((Path.home() / ".cache/ms-playwright").glob(
            "chromium-*/chrome-linux/chrome"))
        executable = str(cached[-1]) if cached else None
    return playwright.chromium.launch(headless=True, executable_path=executable)
