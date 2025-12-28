#!/bin/bash

# Script to submit all test combinations to SLURM on the same node

echo "========================================="
echo "Submitting SLURM Job Array"
echo "========================================="
echo ""

# Create necessary directories
mkdir -p logs results

# Submit the job array
JOB_ID=$(sbatch --parsable test_all_combinations_slurm.sh)

if [ $? -eq 0 ]; then
    echo "✓ Job array submitted successfully!"
    echo "  Job ID: $JOB_ID"
    echo "  Array tasks: 0-5 (6 combinations total)"
    echo ""
    echo "Combinations:"
    echo "  Task 0: lucas + direct"
    echo "  Task 1: lucas + belief"
    echo "  Task 2: lucas + mso"
    echo "  Task 3: christian + direct"
    echo "  Task 4: christian + belief"
    echo "  Task 5: christian + mso"
    echo ""
    echo "Monitor jobs with:"
    echo "  squeue -j $JOB_ID"
    echo "  squeue -u \$USER"
    echo ""
    echo "Check logs in:"
    echo "  logs/test_all_${JOB_ID}_*.out"
    echo "  logs/test_all_${JOB_ID}_*.err"
    echo ""
    echo "Results will be in:"
    echo "  results/test_*_*.csv"
    echo ""
    echo "Cancel all tasks with:"
    echo "  scancel $JOB_ID"
else
    echo "✗ Failed to submit job"
    exit 1
fi
