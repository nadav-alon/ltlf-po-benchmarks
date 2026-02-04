#!/bin/bash

# Configuration
TEST_DIR="ltlf-fin-benchmarks"
TOOLS=("lucas:mso" "lucas:belief-states" "spot:ltlf")

echo "======================================================"
echo "Rerunning ltlf-fin FU (Full Unobservability) benchmarks"
echo "Fix applied: Resolved on-the-fly part file generation bug"
echo "Tools: ${TOOLS[*]}"
echo "======================================================"

# FU (Full Unobservability)
# Using level "all" which maps to po-part-all
./submit_samples.sh "${TOOLS[@]}" --num-samples 1 --level "all" --test-dir "$TEST_DIR"

echo ""
echo "Jobs submitted. Monitor with 'squeue -u $USER'."
echo "Once finished, remember to run the consolidation script."
