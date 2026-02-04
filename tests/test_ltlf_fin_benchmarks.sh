#!/bin/bash

# Configuration
modes=('lucas:mso' 'lucas:belief-states' 'spot:ltlf')
tests=('ltlf-fin-benchmarks/ltlf/counter_pb_01_pe_.ltlf')
expected_fo=(1)
expected_fu=(0)
LUCAS_PATH="../lucas/Syft/build/bin/Syft"

failures=()

test_part() {
    part_dir=$1
    expected=$2

    for mode in "${modes[@]}"; do
        for i in "${!tests[@]}"; do 
            test_path="${tests[$i]}"
            expect="${expected[$i]}"
            
            echo "Testing $mode on $test_path (Expected: $expect)..."
            rm -f output.csv

            python3 runTests.py \
                --mode="$mode" \
                --test-dir="$test_path" \
                --path="$LUCAS_PATH" \
                --part-dir="$part_dir" \
                --output output.csv 

            if [ -f output.csv ]; then
                # Filter out comments and match the test path precisely
                line=$(grep -v '^#' output.csv | grep "$test_path")
                
                if [ -n "$line" ]; then
                    # Ensure we only have one line (take the last one if multiple)
                    line=$(echo "$line" | tail -n 1)
                    status=$(echo "$line" | cut -d',' -f5)
                    
                    if [ "$status" == "$expect" ]; then
                        echo "✓ Success (Outcome: $status)"
                    else
                        echo "✗ Failed (Expected: $expect, Got: $status)"
                        failures+=("$mode on $test_path (Expected $expect, Got $status)")
                    fi
                else
                    echo "✗ Failed (not found in output CSV data rows)"
                    failures+=("$mode on $test_path (missing in csv)")
                fi
            else
                echo "✗ Failed (output.csv not generated)"
                failures+=("$mode on $test_path (no output file)")
            fi
            echo "----------------------------------------"
        done
    done
}

# FO
test_part 'part' $expected_fo
test_part 'po-part-all' $expected_fu

rm -f output.csv

if [ ${#failures[@]} -ne 0 ]; then
    echo "========================================"
    echo "FAILS:"
    for fail in "${failures[@]}"; do
        echo "  - $fail"
    done
    exit 1
else
    echo "========================================"
    echo "All tests passed!"
    exit 0
fi

