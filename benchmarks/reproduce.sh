#!/bin/bash

# ==============================================================================
# APEX COMPRESSION LAB - REPRODUCIBLE BENCHMARK SUITE
# ==============================================================================
# This script downloads a standard corpus and runs the same benchmarks
# displayed on our README against your local hardware.
#
# Dependencies required on PATH:
# - curl
# - tar
# - gzip
# - bzip2
# - xz
# - zstd
# - brotli
# - apex
# ==============================================================================

set -e

CORPUS_URL="http://corpus.canterbury.ac.nz/resources/cantrbry.tar.gz"
WORK_DIR="/tmp/apex_benchmarks"
CORPUS_DIR="$WORK_DIR/canterbury"
TAR_FILE="$WORK_DIR/cantrbry.tar.gz"

echo "============================================================"
echo "⚡ ApexCompress - Automated Benchmark Suite"
echo "============================================================"
echo "Hardware Specs:"
if [ "$(uname)" == "Darwin" ]; then
    sysctl -n machdep.cpu.brand_string
    sysctl -n hw.memsize | awk '{print $1/1073741824" GB RAM"}'
else
    lscpu | grep "Model name" | sed -e 's/^[[:space:]]*//'
    free -h | grep Mem | awk '{print $2" RAM"}'
fi
echo "============================================================"

# Setup
mkdir -p "$WORK_DIR"
mkdir -p "$CORPUS_DIR"

if [ ! -f "$TAR_FILE" ]; then
    echo "[+] Downloading Canterbury Corpus..."
    curl -sS -o "$TAR_FILE" "$CORPUS_URL"
fi

echo "[+] Extracting corpus..."
tar -xzf "$TAR_FILE" -C "$CORPUS_DIR"

# Create 282MB version (100x concatenation)
echo "[+] Generating 282MB scaled corpus for parallel execution testing..."
SCALED_FILE="$WORK_DIR/canterbury_scaled.bin"
if [ ! -f "$SCALED_FILE" ]; then
    # Create single file from all cantrbry files
    cat "$CORPUS_DIR"/* > "$WORK_DIR/single_corpus.bin"
    # Duplicate 100 times
    for i in {1..100}; do cat "$WORK_DIR/single_corpus.bin" >> "$SCALED_FILE"; done
fi

# Run Apex Benchmark
echo ""
echo "[+] Starting Live Tournament (Apex vs The World)..."
echo "------------------------------------------------------------"
if command -v apex &> /dev/null; then
    apex benchmark "$SCALED_FILE"
else
    echo "ERROR: 'apex' command not found in PATH."
    echo "Please build apex or run 'python3 -m pip install -e .' first."
    exit 1
fi

echo ""
echo "[+] Benchmark Complete."
echo "You can manually compare these results against standard archivers:"
echo "  gzip -9   < canterbury_scaled.bin > canterbury_scaled.bin.gz"
echo "  bzip2 -9  < canterbury_scaled.bin > canterbury_scaled.bin.bz2"
echo "  xz -9     < canterbury_scaled.bin > canterbury_scaled.bin.xz"
echo "  zstd -19  < canterbury_scaled.bin > canterbury_scaled.bin.zst"
echo "  brotli -q 11 < canterbury_scaled.bin > canterbury_scaled.bin.br"
echo "============================================================"
