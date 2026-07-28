from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_ci_installs_playwright_chromium_before_running_tests() -> None:
    """Browser-backed demo tests need a Chromium executable on clean runners."""

    workflow = TEST_WORKFLOW.read_text(encoding="utf-8")
    dependency_install = "pip install pytest"
    browser_install = "python -m playwright install --with-deps chromium"
    test_run = "python -m pytest -q"

    assert browser_install in workflow
    assert workflow.index(dependency_install) < workflow.index(browser_install)
    assert workflow.index(browser_install) < workflow.index(test_run)
