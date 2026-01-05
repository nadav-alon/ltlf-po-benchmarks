#!/bin/bash

# Script to test all combinations of solvers and modes
# This helps verify that runTests.py works correctly with all configurations

set -e  # Exit on error

TIMEOUT=60
TEST_DIR="lucas"
LUCAS_PATH="~/lucas/Syft/build/bin/Syft"
CHRISTIAN_PATH="~/christian/ltlf-synth-unrel-input-aaai2025/Syft/build/bin/Syft"

echo "========================================="
echo "Testing all solver and mode combinations"
echo "========================================="
echo ""

# Test Lucas solver with different modes
echo "--- Testing Lucas Solver ---"
for mode in "lucas:belief-states" "lucas:projection-based" "lucas:mso"; do
    echo ""
    echo "Testing: $mode"
    safe_mode=$(echo $mode | tr ':' '_')
    output_file="test_${safe_mode}.csv"
    
    if python3 runTests.py \
        --mode=$mode \
        --test-dir=$TEST_DIR \
        --path=$LUCAS_PATH \
        --timeout=$TIMEOUT \
        --output=$output_file \
        2>&1 | tail -20; then
        echo "✓ $mode: SUCCESS"
    else
        echo "✗ $mode: FAILED"
    fi
done

echo ""
echo "--- Testing Christian Solver ---"
for mode in "christian:direct" "christian:belief" "christian:mso"; do
    echo ""
    echo "Testing: $mode"
    safe_mode=$(echo $mode | tr ':' '_')
    output_file="test_${safe_mode}.csv"
    
    if python3 runTests.py \
        --mode=$mode \
        --test-dir=$TEST_DIR \
        --path=$CHRISTIAN_PATH \
        --timeout=$TIMEOUT \
        --output=$output_file \
        2>&1 | tail -20; then
        echo "✓ $mode: SUCCESS"
    else
        echo "✗ $mode: FAILED"
    fi
done

echo ""
echo "========================================="
echo "All tests completed!"
echo "========================================="
echo ""
echo "Generated output files:"
ls -lh test_*.csv 2>/dev/null || echo "No output files generated"
