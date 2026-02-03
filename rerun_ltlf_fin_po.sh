#!/bin/bash

# Configuration
TEST_DIR="ltlf-fin-benchmarks"
NUM_SAMPLES=10
TOOLS=("lucas:mso" "lucas:belief-states" "spot:ltlf")
LEVELS=("1-2" "1-4" "3-4")
DRY_RUN=""

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "[DRY RUN ENABLED]"
fi

echo "======================================================"
echo "Rerunning ltlf-fin benchmarks with corrected PO logic"
echo "Tools: ${TOOLS[*]}"
echo "Samples: 1-$NUM_SAMPLES"
echo "======================================================"

# 1. Run for PO levels with 10 samples each
for LEVEL in "${LEVELS[@]}"; do
    echo ""
    echo ">>> Submitting Level: $LEVEL ($NUM_SAMPLES samples)"
    ./submit_samples.sh "${TOOLS[@]}" --num-samples "$NUM_SAMPLES" --level "$LEVEL" --test-dir "$TEST_DIR" $DRY_RUN
done

# 2. Run for 'all' level (only 1 sample needed)
echo ""
echo ">>> Submitting Level: all (1 sample)"
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "all" --test-dir "$TEST_DIR" $DRY_RUN

echo ""
echo "All jobs submitted. Monitor with 'squeue -u $USER'."
echo "Results will be saved in the cluster results directory."
