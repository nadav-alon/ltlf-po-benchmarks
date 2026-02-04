#!/bin/bash

# Configuration
modes=('lucas:mso' 'lucas:belief-states' 'spot:ltlf')
tests=('lucas/ltlf/coins_3.ltlf' 'lucas/ltlf/coins_4.ltlf' 'lucas/ltlf/seek_3.ltlf' )
expected=(0 1 1)
LUCAS_PATH="../lucas/Syft/build/bin/Syft"

failures=()

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
