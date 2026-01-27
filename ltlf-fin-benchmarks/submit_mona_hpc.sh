#!/bin/bash
#SBATCH --job-name=mona_gen
#SBATCH --output=logs/mona_%A_%a.out
#SBATCH --error=logs/mona_%A_%a.err
#SBATCH --array=0-19
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --exclude=cn[31-44],gpu[1-4],gpu[6-8]

# This script should be run from the ltlf-fin-benchmarks directory on HPC

mkdir -p logs

python3 run_mona_hpc.py \
    --tasks mona_tasks.json \
    --shard-id $SLURM_ARRAY_TASK_ID \
    --num-shards 20 \
    --workers 8

# After all shards finish, you can combine them:
# head -n 1 mona_results_0.csv > mona_results_combined.csv
# for i in {0..19}; do if [ -f mona_results_$i.csv ]; then tail -n +2 mona_results_$i.csv >> mona_results_combined.csv; fi; done
