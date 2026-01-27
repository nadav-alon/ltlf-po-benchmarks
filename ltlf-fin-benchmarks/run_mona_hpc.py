import json
import subprocess
import time
import os
import argparse
import csv
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

def run_mona_task(task):
    mona_file = task['mona_file']
    dfa_file = task['dfa_file']
    
    # Paths are relative to the directory where mona_tasks.json is
    # We assume the script is run from ltlf-fin-benchmarks directory
    
    mona_path = Path(mona_file)
    dfa_path = Path(dfa_file)
    
    if not mona_path.exists():
        return {
            "mona_file": mona_file,
            "status": "MISSING_INPUT",
            "runtime": 0,
            "wall_time": 0,
            "error": "File not found"
        }
    
    dfa_path.parent.mkdir(parents=True, exist_ok=True)
    
    start_time = time.process_time()
    wall_start = time.time()
    
    try:
        # Use mona -u -xw to generate DFA as in original script
        with open(dfa_path, 'w') as f:
            result = subprocess.run(['mona', '-u', '-xw', str(mona_path)], stdout=f, stderr=subprocess.PIPE, timeout=300)
        
        runtime = time.process_time() - start_time
        wall_time = time.time() - wall_start
        
        if result.returncode == 0:
            return {
                "mona_file": mona_file,
                "status": "SUCCESS",
                "runtime": runtime,
                "wall_time": wall_time,
                "error": ""
            }
        else:
            return {
                "mona_file": mona_file,
                "status": "ERROR",
                "runtime": runtime,
                "wall_time": wall_time,
                "error": result.stderr.decode()
            }
    except subprocess.TimeoutExpired:
        return {
            "mona_file": mona_file,
            "status": "TIMEOUT",
            "runtime": 300,
            "wall_time": time.time() - wall_start,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "mona_file": mona_file,
            "status": "EXCEPTION",
            "runtime": 0,
            "wall_time": 0,
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="mona_tasks.json")
    parser.add_argument("--output", default="mona_results.csv")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--shard-id", type=int, default=None)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()

    with open(args.tasks, 'r') as f:
        all_tasks = json.load(f)

    # Sharding logic for job arrays
    if args.shard_id is not None:
        shard_size = (len(all_tasks) + args.num_shards - 1) // args.num_shards
        start = args.shard_id * shard_size
        end = min(start + shard_size, len(all_tasks))
        tasks = all_tasks[start:end]
        print(f"Processing shard {args.shard_id}/{args.num_shards}: tasks {start} to {end}")
        output_file = f"mona_results_{args.shard_id}.csv"
    else:
        tasks = all_tasks
        output_file = args.output

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(run_mona_task, tasks))

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["mona_file", "status", "runtime", "wall_time", "error"])
        writer.writeheader()
        for res in results:
            writer.writerow(res)

    print(f"Done. Results written to {output_file}")

if __name__ == "__main__":
    main()
