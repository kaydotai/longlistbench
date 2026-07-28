import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "scripts" / "run_bonsai_demo.sh"


def test_single_demo_script_owns_setup_and_runtime() -> None:
    script = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "PrismML-Eng/llama.cpp" in script
    assert 'LLAMA_CPP_REVISION="7529fdaaf99ffdc5ca71ace9c7409a56b27ad92f"' in script
    assert 'MODEL_REPO="prism-ml/Ternary-Bonsai-27B-gguf"' in script
    assert 'MODEL_FILE="Ternary-Bonsai-27B-Q2_0.gguf"' in script
    assert "python3 -m venv" in script
    assert 'cd "$ROOT"' in script
    assert "huggingface_hub" in script
    assert "-DGGML_METAL=ON" in script
    assert "--slot-save-path" in script
    assert "-m demo.bonsai_extract.app" in script


def test_demo_runtime_preflight_requires_every_pdf_ingestion_tool() -> None:
    """The launcher must reject missing tools needed for uploaded PDF previews."""

    script = RUN_SCRIPT.read_text(encoding="utf-8")
    require_loop = re.search(
        (
            r"for\s+command\s+in\s+(?P<commands>[^;]+);\s*do\s+"
            r'require_command\s+"\$command"\s+done'
        ),
        script,
    )

    assert require_loop is not None
    required_commands = set(require_loop.group("commands").split())
    assert {"pdftotext", "pdftocairo"} <= required_commands


def test_single_demo_script_stays_demo_only() -> None:
    script = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "pi-coding-agent" not in script
    assert "npm install" not in script
    assert "benchmarks/requirements.txt" not in script
    assert "uv " not in script
    assert not (ROOT / "scripts" / "setup_bonsai_runtime.sh").exists()
    assert not (ROOT / "scripts" / "start_bonsai_server.sh").exists()
    assert not (ROOT / "scripts" / "start_bonsai_demo.sh").exists()


def test_single_demo_script_uses_cold_prefill_configuration() -> None:
    script = RUN_SCRIPT.read_text(encoding="utf-8")

    required = [
        "--alias",
        "prism-ml/Ternary-Bonsai-27B-mlx-2bit",
        "-ngl 999",
        "-fa on",
        "-c 262144",
        "--temp 0.7",
        "--top-p 0.95",
        "--top-k 20",
        "--reasoning-budget 8192",
        "-np 1",
    ]
    for fragment in required:
        assert fragment in script


def test_readme_documents_one_command_demo() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Local Bonsai extraction demo" in readme
    assert "./scripts/run_bonsai_demo.sh" in readme
    assert "M4 Pro with 48 GB" in readme
    assert "about 6.7 GB" in readme
    assert "brew install python cmake poppler" in readme
    assert "Press Ctrl-C" in readme
    assert "demo/bonsai_extract/assets/driver_mvr_record_001.pdf" in readme
