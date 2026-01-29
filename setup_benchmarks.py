import os
import subprocess
import random
import shutil
import json
from pathlib import Path

# Target: 150 benchmarks total
categories = {
    "Two-player-Game/Single-Counter": 20,
    "Two-player-Game/Double-Counter": 20,
    "Two-player-Game/Nim": 88,
    "chomp_game": 22
}

def run_syfco(args):
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
    benchmarks = []
    root_path = Path("/home/cowclaw/ltlf-po-benchmarks")
    tlsf_fin_path = root_path / "SYNTCOMP-benchmarks/tlsf-fin"

    for category, limit in categories.items():
        category_path = tlsf_fin_path / category
        if not category_path.exists():
            print(f"Warning: Category path {category_path} not found.")
            continue
            
        tlsf_files = list(category_path.rglob("*.tlsf"))
        priority = [f for f in tlsf_files if "_pb_" in f.stem and "_pe_" in f.stem]
        others = [f for f in tlsf_files if f not in priority]
        
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

    base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/ltlf-fin-benchmarks")
    ltlf_dir = base_dir / "ltlf"
    mso_dir = base_dir / "mso"
    part_dir = base_dir / "part"

    levels = ["1-2", "all"]
    po_part_dirs = {level: base_dir / f"po-part-{level}" for level in levels}
    po_mso_dirs = {level: base_dir / f"po-mso-{level}" for level in levels}
    po_mso_dirs["0"] = base_dir / "po-mso-0"

    if base_dir.exists():
        shutil.rmtree(base_dir)

    ltlf_dir.mkdir(parents=True, exist_ok=True)
    mso_dir.mkdir(parents=True, exist_ok=True)
    part_dir.mkdir(parents=True, exist_ok=True)
    for d in po_part_dirs.values(): d.mkdir(parents=True, exist_ok=True)
    for d in po_mso_dirs.values(): d.mkdir(parents=True, exist_ok=True)

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
        
        input_list = [i.strip(";,") for i in (inputs or "").replace(",", " ").split() if i.strip(";,")]
        output_list = [o.strip(";,") for o in (outputs or "").replace(",", " ").split() if o.strip(";,")]
        
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
            count = (len(input_list) // 2) if level == "1-2" else len(input_list)
            count = max(1, count) if level == "1-2" and input_list else count
            
            unobs = random.sample(input_list, count) if input_list else []
            obs = [i for i in input_list if i not in unobs]
            
            # PO Part
            po_file = po_part_dirs[level] / f"{stem}.part"
            with open(po_file, "w") as f:
                f.write(f"semantics {semantics}\n")
                f.write(f"inputs {' '.join(obs)}\n")
                f.write(f"outputs {' '.join(output_list)}\n")
                if unobs: f.write(f"unobservables {' '.join(unobs)}\n")
            
            # PO MSO
            level_mso_dir = po_mso_dirs[level]
            shutil.copy2(mso_file, level_mso_dir / f"{stem}.mona")
            with open(level_mso_dir / f"{stem}.mona.quant", "w") as f:
                f.write(quantify_mona_content(mso_content, unobs))
            if rev_mona_file.exists(): shutil.copy2(rev_mona_file, level_mso_dir / f"{stem}.mona.rev")
            if rev_neg_mona_file.exists(): shutil.copy2(rev_neg_mona_file, level_mso_dir / f"{stem}.mona.rev.neg")

    print(f"Done. Prepared 150 benchmarks in ltlf-fin-benchmarks.")

if __name__ == "__main__":
    main()
