import os
import pandas as pd
import glob
import re

# 1. Current results from summarize_yellows.py logic
results_dir_current = "/home/cowclaw/ltlf-po-benchmarks/yellow_results"
summary_current = {}

if os.path.exists(results_dir_current):
    for level in os.listdir(results_dir_current):
        level_path = os.path.join(results_dir_current, level)
        if not os.path.isdir(level_path): continue
        for filename in os.listdir(level_path):
            if not filename.endswith(".txt"): continue
            parts = filename.rsplit("_", 1)
            test_stem = parts[0]
            file_path = os.path.join(level_path, filename)
            with open(file_path, "r") as f:
                content = f.read()
                is_realizable = "REALIZABLE" in content and "UNREALIZABLE" not in content
                key = (level.replace("-", "_"), test_stem)
                if key not in summary_current: summary_current[key] = {"realizable": 0, "total": 0}
                summary_current[key]["total"] += 1
                if is_realizable: summary_current[key]["realizable"] += 1

# 2. Original results from results_shards
base_dir_orig = "/home/cowclaw/results_shards/data/results/latest_ltlf_fin_benchmarks"
pattern = os.path.join(base_dir_orig, "**", "consolidated_averaged*.csv")
files_orig = glob.glob(pattern, recursive=True)
summary_orig = {}

def extract_level(path):
    match = re.search(r"po_(\d+)_(\d+)_", path)
    if match: return f"{match.group(1)}_{match.group(2)}"
    return None

for f in files_orig:
    level = extract_level(f)
    if not level: continue
    try:
        df = pd.read_csv(f)
        for _, row in df.iterrows():
            test_stem = os.path.basename(row['test']).split(".")[0]
            key = (level, test_stem)
            if key in summary_current:
                if key not in summary_orig: summary_orig[key] = {"real": 0, "succ": 0}
                # Use max to get the best reported successful run count for that test/level across tools
                if row['num_success'] > summary_orig[key]['succ']:
                    summary_orig[key]['succ'] = int(row['num_success'])
                    summary_orig[key]['real'] = int(row['num_realizable'])
    except: continue

# 3. Print comparison
print(f"{'Test (Level)':<45} | {'Original (Shards)':<20} | {'Current (Local)'}")
print("-" * 85)
for key in sorted(summary_current.keys()):
    level, test = key
    curr = summary_current[key]
    orig = summary_orig.get(key, {"real": "N/A", "succ": "N/A"})
    orig_str = f"{orig['real']}/{orig['succ']}" if orig['real'] != "N/A" else "N/A"
    curr_str = f"{curr['realizable']}/{curr['total']}"
    display_name = f"{test} ({level})"
    print(f"{display_name:<45} | {orig_str:<20} | {curr_str}")
