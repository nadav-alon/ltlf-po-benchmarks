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
    echo "  Array tasks: 0-95 (6 combinations x 16 shards)"
    echo ""
    echo "Combinations (16 shards each):"
    echo "  Tasks 0-15:  lucas + direct"
    echo "  Tasks 16-31: lucas + belief"
    echo "  Tasks 32-47: lucas + mso"
    echo "  Tasks 48-63: christian + direct"
    echo "  Tasks 64-79: christian + belief"
    echo "  Tasks 80-95: christian + mso"
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
