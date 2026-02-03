#!/bin/bash

# Configuration
TEST_DIR="ltlf-fin-benchmarks"
TOOLS=("lucas:mso" "lucas:belief-states" "spot:ltlf")
DRY_RUN=""

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "[DRY RUN ENABLED]"
fi

echo "======================================================"
echo "Rerunning ltlf-fin FO and FU benchmarks"
echo "Tools: ${TOOLS[*]}"
echo "Note: Spot will run both On-The-Fly and Restricted"
echo "======================================================"

# 1. FO (Full Observability)
echo ""
echo ">>> Submitting Level: FO (using part directory)"
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "part" --test-dir "$TEST_DIR" $DRY_RUN

# 2. FU (Full Unobservability)
echo ""
echo ">>> Submitting Level: FU (using level all)"
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "all" --test-dir "$TEST_DIR" $DRY_RUN

echo ""
echo "Jobs submitted. Monitor with 'squeue -u $USER'."
echo "Results will be in results/<JOB_ID>/part/ and results/<JOB_ID>/po-part-all/"
