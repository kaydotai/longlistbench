#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"
RUNTIME_DIR="$ROOT/.runtime/bonsai-demo"
VENV_DIR="$RUNTIME_DIR/venv"
LLAMA_DIR="$RUNTIME_DIR/llama.cpp"
MODEL_DIR="$RUNTIME_DIR/models"
SLOT_SAVE_DIR="$RUNTIME_DIR/slot-cache"
LOG_DIR="$RUNTIME_DIR/logs"
PYTHON="$VENV_DIR/bin/python"
SERVER="$LLAMA_DIR/build/bin/llama-server"
MODEL_FILE="Ternary-Bonsai-27B-Q2_0.gguf"
MODEL="$MODEL_DIR/$MODEL_FILE"
MODEL_REPO="prism-ml/Ternary-Bonsai-27B-gguf"
MODEL_ID="prism-ml/Ternary-Bonsai-27B-mlx-2bit"
LLAMA_CPP_REVISION="7529fdaaf99ffdc5ca71ace9c7409a56b27ad92f"
MODEL_LOG="$LOG_DIR/llama-server.log"
DEMO_LOG="$LOG_DIR/demo.log"
DEMO_PORT=${BONSAI_DEMO_PORT:-8765}
MODEL_PID=""
DEMO_PID=""

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

cleanup() {
    if [ -n "$DEMO_PID" ] && kill -0 "$DEMO_PID" 2>/dev/null; then
        kill "$DEMO_PID"
        wait "$DEMO_PID" 2>/dev/null || true
    fi
    if [ -n "$MODEL_PID" ] && kill -0 "$MODEL_PID" 2>/dev/null; then
        kill "$MODEL_PID"
        wait "$MODEL_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap 'exit 130' INT TERM

for command in python3 git cmake curl pdftotext pdftocairo open; do
    require_command "$command"
done

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
    echo "This demo currently supports Apple Silicon Macs." >&2
    exit 1
fi

mkdir -p "$RUNTIME_DIR" "$MODEL_DIR" "$SLOT_SAVE_DIR" "$LOG_DIR"

if [ ! -x "$PYTHON" ]; then
    echo "Creating the demo environment..."
    python3 -m venv "$VENV_DIR"
fi

if ! "$PYTHON" -c "import openai, huggingface_hub" >/dev/null 2>&1; then
    echo "Installing the two Python runtime dependencies..."
    "$PYTHON" -m pip install --quiet --disable-pip-version-check \
        "openai>=1,<3" \
        "huggingface_hub>=0.24,<2"
fi

if [ ! -d "$LLAMA_DIR/.git" ]; then
    echo "Cloning the pinned Bonsai llama.cpp runtime..."
    git clone https://github.com/PrismML-Eng/llama.cpp.git "$LLAMA_DIR"
fi

if ! git -C "$LLAMA_DIR" cat-file -e \
    "$LLAMA_CPP_REVISION^{commit}" 2>/dev/null; then
    git -C "$LLAMA_DIR" fetch origin "$LLAMA_CPP_REVISION"
fi
git -C "$LLAMA_DIR" checkout --quiet --detach "$LLAMA_CPP_REVISION"

if [ ! -x "$SERVER" ]; then
    echo "Building llama-server with Metal..."
    cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
        -DGGML_METAL=ON \
        -DGGML_METAL_EMBED_LIBRARY=ON \
        -DCMAKE_BUILD_TYPE=Release
    cmake --build "$LLAMA_DIR/build" \
        --target llama-server \
        --config Release \
        -j 8
fi

if [ ! -f "$MODEL" ]; then
    echo "Downloading Ternary Bonsai 27B (about 6.7 GB)..."
    "$VENV_DIR/bin/hf" download "$MODEL_REPO" "$MODEL_FILE" \
        --local-dir "$MODEL_DIR"
fi

if curl -fsS --max-time 1 http://127.0.0.1:8080/health >/dev/null 2>&1; then
    echo "Port 8080 already has a model server. Stop it, then rerun this script." >&2
    exit 1
fi

echo "Starting Ternary Bonsai 27B..."
"$SERVER" \
    -m "$MODEL" \
    --alias "$MODEL_ID" \
    --host 127.0.0.1 \
    --port 8080 \
    -ngl 999 \
    -fa on \
    -c 262144 \
    --temp 0.7 \
    --top-p 0.95 \
    --top-k 20 \
    --min-p 0 \
    --jinja \
    --reasoning-budget 8192 \
    --slot-save-path "$SLOT_SAVE_DIR" \
    -np 1 \
    >"$MODEL_LOG" 2>&1 &
MODEL_PID=$!

attempts=0
until curl -fsS --max-time 1 http://127.0.0.1:8080/health >/dev/null 2>&1; do
    if ! kill -0 "$MODEL_PID" 2>/dev/null; then
        echo "llama-server exited during startup. See $MODEL_LOG" >&2
        exit 1
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 180 ]; then
        echo "Timed out waiting for llama-server. See $MODEL_LOG" >&2
        exit 1
    fi
    sleep 1
done

echo "Starting the extraction app..."
"$PYTHON" -m demo.bonsai_extract.app \
    --host 127.0.0.1 \
    --port "$DEMO_PORT" \
    >"$DEMO_LOG" 2>&1 &
DEMO_PID=$!

attempts=0
until curl -fsS --max-time 1 \
    "http://127.0.0.1:$DEMO_PORT/api/health" >/dev/null 2>&1; do
    if ! kill -0 "$DEMO_PID" 2>/dev/null; then
        echo "The demo exited during startup. See $DEMO_LOG" >&2
        exit 1
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
        echo "Timed out waiting for the demo. See $DEMO_LOG" >&2
        exit 1
    fi
    sleep 1
done

DEMO_URL="http://127.0.0.1:$DEMO_PORT/"
echo "Demo ready: $DEMO_URL"
echo "Drop demo/bonsai_extract/assets/driver_mvr_record_001.pdf into the page."
echo "Press Ctrl-C to stop both local processes."
open "$DEMO_URL"

wait "$DEMO_PID"
