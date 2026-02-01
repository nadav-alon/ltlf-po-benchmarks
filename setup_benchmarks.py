import os
import subprocess
import random
import shutil
import json
import math
import itertools
from pathlib import Path

# Target: 150 benchmarks total
MAX_SAMPLES = 30
categories = {
    "Two-player-Game/Single-Counter": 20,
    "Two-player-Game/Double-Counter": 20,
    "Two-player-Game/Nim": 88,
    "chomp_game": 22
}

def get_unique_samples(items, k, max_n):
    n = len(items)
    if n == 0 or k == 0:
        return [tuple()]
    
    total_possible = math.comb(n, k)
    if total_possible <= 10000:
        all_combos = list(itertools.combinations(items, k))
        random.shuffle(all_combos)
        return all_combos[:max_n]
    
    seen = set()
    samples = []
    # Avoid infinite loop if somehow logic fails, though total_possible > 10000 here
    attempts = 0
    while len(samples) < max_n and attempts < max_n * 100:
        s = tuple(sorted(random.sample(items, k)))
        if s not in seen:
            seen.add(s)
            samples.append(s)
        attempts += 1
    return samples

def run_syfco(args):
# ... (rest of the helper functions unchanged)
    result = subprocess.run(["syfco"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def detect_semantics(tlsf_path):
    # Specialized override for Nim
    if "Two-player-Game/Nim" in str(tlsf_path):
        return "mealy"
    
    res = run_syfco(["-s", str(tlsf_path)])
    if res and "Mealy" in res:
        return "mealy"
    return "moore"

def quantify_mona_content(original_content, unobservables):
    lines = original_content.splitlines()
    new_lines = []
    
    all_vars = []
    unobs_set = {v.strip().upper() for v in unobservables}
    
    m2l_line = None
    header_comment = None
    
    formula_start_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('var2'):
            vars_part = stripped[4:].rstrip(';').replace(',', ' ').split()
            all_vars.extend(vars_part)
        elif stripped.startswith('m2l-str'):
            m2l_line = line
        elif stripped.startswith('#'):
            if not header_comment:
                header_comment = line
        elif stripped:
            formula_start_idx = i
            break
            
    seen = set()
    unique_vars = [v for v in all_vars if not (v.upper() in seen or seen.add(v.upper()))]
    remaining_vars = [v for v in unique_vars if v.upper() not in unobs_set]
    
    if header_comment:
        new_lines.append(header_comment)
    if m2l_line:
        new_lines.append(m2l_line)
    if remaining_vars:
        new_lines.append(f"var2 {', '.join(remaining_vars)};")
    
    if unobservables:
        quant_prefix = " ".join([f"all2 {v.upper()}:" for v in sorted(list(unobs_set))])
        new_lines.append(f"{quant_prefix} (")
        
    if formula_start_idx != -1:
        formula_lines = lines[formula_start_idx:]
        formula_str = "\n".join(formula_lines).strip()
        if formula_str.endswith(';'):
            formula_str = formula_str[:-1]
        new_lines.append(formula_str)
        
    if unobservables:
        new_lines.append(");")
    else:
        if new_lines and not new_lines[-1].strip().endswith(';'):
             new_lines[-1] = new_lines[-1].rstrip() + ";"

    return "\n".join(new_lines) + "\n"

def negate_mona_content(content):
    lines = content.splitlines()
    new_lines = []
    formula_part = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('var2') or stripped.startswith('m2l-str') or stripped.startswith('#'):
            new_lines.append(line)
        elif stripped:
            formula_part.append(line)
    
    if formula_part:
        formula_str = " ".join(formula_part).rstrip(';')
        new_lines.append(f"~({formula_str});")
            
    return "\n".join(new_lines) + "\n"

def main():
    random.seed(42)
    benchmarks = []
    root_path = Path("/home/cowclaw/ltlf-po-benchmarks")
    tlsf_fin_path = root_path / "SYNTCOMP-benchmarks/tlsf-fin"

    for category, limit in categories.items():
        category_path = tlsf_fin_path / category
        if not category_path.exists():
            print(f"Warning: Category path {category_path} not found.")
            continue
            
        tlsf_files = sorted(list(category_path.rglob("*.tlsf")))
        priority = sorted([f for f in tlsf_files if "_pb_" in f.stem and "_pe_" in f.stem])
        others = sorted([f for f in tlsf_files if f not in priority])
        
        selected = []
        if len(priority) >= limit:
            selected = random.sample(priority, limit)
        else:
            selected = priority
            if others:
                needed = limit - len(selected)
                selected.extend(random.sample(others, min(len(others), needed)))
        
        for f in selected:
            benchmarks.append(f)

    print(f"Collected {len(benchmarks)} benchmarks total.")
    rng_state = random.getstate()

    base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/ltlf-fin-benchmarks")
    ltlf_dir = base_dir / "ltlf"
    mso_dir = base_dir / "mso"
    part_dir = base_dir / "part"

    if base_dir.exists():
        shutil.rmtree(base_dir)

    ltlf_dir.mkdir(parents=True, exist_ok=True)
    mso_dir.mkdir(parents=True, exist_ok=True)
    part_dir.mkdir(parents=True, exist_ok=True)

    po_part_dirs = {}
    po_mso_dirs = {}
    
    # Levels and sample directories
    levels = ["1-2", "1-4", "3-4", "all"]
    for level in levels:
        if level == "all":
            po_part_dirs[level] = base_dir / "po-part-all"
            po_mso_dirs[level] = base_dir / "po-mso-all"
            po_part_dirs[level].mkdir(parents=True, exist_ok=True)
            po_mso_dirs[level].mkdir(parents=True, exist_ok=True)
        else:
            for s in range(1, MAX_SAMPLES + 1):
                po_part_dirs[(level, s)] = base_dir / f"po-part-{level}_{s}"
                po_mso_dirs[(level, s)] = base_dir / f"po-mso-{level}_{s}"
                po_part_dirs[(level, s)].mkdir(parents=True, exist_ok=True)
                po_mso_dirs[(level, s)].mkdir(parents=True, exist_ok=True)
    
    po_mso_dirs["0"] = base_dir / "po-mso-0"
    po_mso_dirs["0"].mkdir(parents=True, exist_ok=True)

    LTFL2FOL = "/home/cowclaw/lucas/Syft/build/bin/ltlf2fol"
    LTFL2PFOL = "/home/cowclaw/lucas/Syft/build/bin/ltlf2pfol"

    for tlsf_path in benchmarks:
        stem = tlsf_path.stem
        semantics = detect_semantics(tlsf_path)
        
        ltlf_file = ltlf_dir / f"{stem}.ltlf"
        mso_file = mso_dir / f"{stem}.mona"
        rev_mona_file = mso_dir / f"{stem}.mona.rev"
        rev_neg_mona_file = mso_dir / f"{stem}.mona.rev.neg"
        
        print(f"Processing {stem} (Semantics: {semantics})...")
        
        ltl_formula = run_syfco(["-f", "ltlxba-fin", str(tlsf_path)])
        if ltl_formula:
            ltl_formula = ltl_formula.replace("X[!]", "N")
            with open(ltlf_file, "w") as f:
                f.write(ltl_formula + "\n")
            
            # 1. Standard MONA (for belief-states)
            try:
                with open(mso_file, "w") as f:
                    subprocess.run([LTFL2FOL, "NNF", str(ltlf_file)], stdout=f, check=True)
            except Exception as e:
                print(f"Warning: Failed to generate MSO for {stem}: {e}")

            # 2. PFOL (for projection-based)
            try:
                proc = subprocess.run([LTFL2PFOL, str(ltlf_file)], capture_output=True, text=True, check=True)
                rev_neg_content = proc.stdout
                
                with open(rev_neg_mona_file, "w") as f:
                    f.write(negate_mona_content(rev_neg_content))
                
                unnegated = rev_neg_content
                if "~(" in rev_neg_content: unnegated = rev_neg_content.replace("~(", "(", 1)
                elif "~" in rev_neg_content: unnegated = rev_neg_content.replace("~", "", 1)
                with open(rev_mona_file, "w") as f:
                    f.write(unnegated)
            except Exception as e:
                print(f"Warning: Failed to generate PFOL for {stem}: {e}")
        else:
            print(f"Skipping {stem} due to Syfco conversion failure.")
            continue
        
        inputs = run_syfco(["-ins", str(tlsf_path)])
        outputs = run_syfco(["-outs", str(tlsf_path)])
        
        input_list = sorted([i.strip(";,") for i in (inputs or "").replace(",", " ").split() if i.strip(";,")])
        output_list = sorted([o.strip(";,") for o in (outputs or "").replace(",", " ").split() if o.strip(";,")])
        
        # Write Base Part File
        base_part_file = part_dir / f"{stem}.part"
        with open(base_part_file, "w") as f:
            f.write(f"semantics {semantics}\n")
            f.write(f"inputs {' '.join(input_list)}\n")
            f.write(f"outputs {' '.join(output_list)}\n")
        
        # FO MSO variants
        shutil.copy2(mso_file, po_mso_dirs["0"] / f"{stem}.mona")
        with open(mso_file, "r") as f: mso_content = f.read()
        with open(po_mso_dirs["0"] / f"{stem}.mona.quant", "w") as f:
            f.write(quantify_mona_content(mso_content, []))
        if rev_mona_file.exists(): shutil.copy2(rev_mona_file, po_mso_dirs["0"] / f"{stem}.mona.rev")
        if rev_neg_mona_file.exists(): shutil.copy2(rev_neg_mona_file, po_mso_dirs["0"] / f"{stem}.mona.rev.neg")

    # PO levels
    for level in levels:
        random.setstate(rng_state)
        print(f"Generating samples for level {level}...")
        for tlsf_path in benchmarks:
            stem = tlsf_path.stem
            mso_file = mso_dir / f"{stem}.mona"
            if not mso_file.exists(): continue
            with open(mso_file, "r") as f: mso_content = f.read()
            rev_mona_file = mso_dir / f"{stem}.mona.rev"
            rev_neg_mona_file = mso_dir / f"{stem}.mona.rev.neg"
            
            inputs = run_syfco(["-ins", str(tlsf_path)])
            outputs = run_syfco(["-outs", str(tlsf_path)])
            semantics = detect_semantics(tlsf_path)
            
            input_list = sorted([i.strip(";,") for i in (inputs or "").replace(",", " ").split() if i.strip(";,")])
            output_list = sorted([o.strip(";,") for o in (outputs or "").replace(",", " ").split() if o.strip(";,")])

            if level == "all":
                unobs_samples = [tuple(input_list)]
            else:
                if level == "1-2":
                    count = len(input_list) // 2
                elif level == "1-4":
                    count = len(input_list) // 4
                elif level == "3-4":
                    count = (3 * len(input_list)) // 4
                else:
                    count = 0
                
                count = max(1, count) if input_list else 0
                unobs_samples = get_unique_samples(input_list, count, MAX_SAMPLES)
            
            for i, unobs in enumerate(unobs_samples):
                sample_idx = i + 1
                obs = [v for v in input_list if v not in unobs]
                
                # Determine directories
                if level == "all":
                    level_part_dir = po_part_dirs[level]
                    level_mso_dir = po_mso_dirs[level]
                else:
                    level_part_dir = po_part_dirs[(level, sample_idx)]
                    level_mso_dir = po_mso_dirs[(level, sample_idx)]
                
                # PO Part
                po_file = level_part_dir / f"{stem}.part"
                with open(po_file, "w") as f:
                    f.write(f"semantics {semantics}\n")
                    f.write(f"inputs {' '.join(obs)}\n")
                    f.write(f"outputs {' '.join(output_list)}\n")
                    if unobs: f.write(f"unobservables {' '.join(unobs)}\n")
                
                # PO MSO
                shutil.copy2(mso_file, level_mso_dir / f"{stem}.mona")
                with open(level_mso_dir / f"{stem}.mona.quant", "w") as f:
                    f.write(quantify_mona_content(mso_content, unobs))
                if rev_mona_file.exists(): shutil.copy2(rev_mona_file, level_mso_dir / f"{stem}.mona.rev")
                if rev_neg_mona_file.exists(): shutil.copy2(rev_neg_mona_file, level_mso_dir / f"{stem}.mona.rev.neg")

    print(f"Done. Prepared benchmarks in {base_dir}.")

if __name__ == "__main__":
    main()
