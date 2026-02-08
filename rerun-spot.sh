#!/bin/bash

# Configuration
TOOLS=("spot:ltlf")
DRY_RUN=""

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "[DRY RUN ENABLED]"
fi

echo "======================================================"
echo "Rerunning Lucas and LTLf-fin benchmarks with new Spot"
echo "Tools: ${TOOLS[*]}"
echo "======================================================"

# 1. LTLf-fin benchmarks (751 tests)
echo ""
echo ">>> Submitting LTLf-fin Benchmarks..."
LTLF_DIR="ltlf-fin-benchmarks"

# FO
echo "Submitting LTLf-fin FO (part)..."
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "part" --test-dir "$LTLF_DIR" $DRY_RUN

# PO (10 samples each)
echo "Submitting LTLf-fin PO (1-2, 1-4, 3-4)..."
for LEVEL in "1-2" "1-4" "3-4"; do
    ./submit_samples.sh "${TOOLS[@]}" --num-samples 10 --level "$LEVEL" --test-dir "$LTLF_DIR" $DRY_RUN
done

# FU
echo "Submitting LTLf-fin FU (all)..."
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "all" --test-dir "$LTLF_DIR" $DRY_RUN

echo ""
echo ">>> Submitting Lucas Benchmarks..."
LUCAS_DIR="lucas"

echo "Submitting Lucas PO (part)..."
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "part" --test-dir "$LUCAS_DIR" $DRY_RUN

echo ""
echo "======================================================"
echo "All jobs submitted. Monitor with 'squeue -u $USER'."
echo "Results will be saved in the results/ directory."
echo "======================================================"