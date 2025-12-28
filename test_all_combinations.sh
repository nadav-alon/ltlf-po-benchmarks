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
for mode in direct belief mso; do
    echo ""
    echo "Testing: Lucas + $mode mode"
    output_file="test_lucas_${mode}.csv"
    
    if python3 runTests.py \
        --solver=lucas \
        --mode=$mode \
        --test-dir=$TEST_DIR \
        --path=$LUCAS_PATH \
        --timeout=$TIMEOUT \
        --output=$output_file \
        2>&1 | tail -20; then
        echo "✓ Lucas + $mode: SUCCESS"
    else
        echo "✗ Lucas + $mode: FAILED"
    fi
done

echo ""
echo "--- Testing Christian Solver ---"
for mode in direct belief mso; do
    echo ""
    echo "Testing: Christian + $mode mode"
    output_file="test_christian_${mode}.csv"
    
    if python3 runTests.py \
        --solver=christian \
        --mode=$mode \
        --test-dir=$TEST_DIR \
        --path=$CHRISTIAN_PATH \
        --timeout=$TIMEOUT \
        --output=$output_file \
        2>&1 | tail -20; then
        echo "✓ Christian + $mode: SUCCESS"
    else
        echo "✗ Christian + $mode: FAILED"
    fi
done

echo ""
echo "========================================="
echo "All tests completed!"
echo "========================================="
echo ""
echo "Generated output files:"
ls -lh test_*.csv 2>/dev/null || echo "No output files generated"
