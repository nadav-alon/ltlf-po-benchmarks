import os

results_dir = "yellow_results"
summary = {}

for level in os.listdir(results_dir):
    level_path = os.path.join(results_dir, level)
    if not os.path.isdir(level_path):
        continue
    
    for filename in os.listdir(level_path):
        if not filename.endswith(".txt"):
            continue
        
        # filename is like chomp_1.txt
        parts = filename.rsplit("_", 1)
        test_stem = parts[0]
        
        file_path = os.path.join(level_path, filename)
        with open(file_path, "r") as f:
            content = f.read()
            is_realizable = "REALIZABLE" in content and "UNREALIZABLE" not in content
            
            key = (level, test_stem)
            if key not in summary:
                summary[key] = {"realizable": 0, "total": 0}
            
            summary[key]["total"] += 1
            if is_realizable:
                summary[key]["realizable"] += 1

# Print the results
sorted_keys = sorted(summary.keys())
for level, test in sorted_keys:
    stats = summary[(level, test)]
    print(f"{level}:{test}.ltlf {stats['realizable']}/{stats['total']} realizable")
