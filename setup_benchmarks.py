import os
import subprocess
import random
import shutil
import json
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# Target: ~100 benchmarks total
categories = {
    "Patterns": 20,
    "Random": 30,
    "Scutella": 5,
    "Two-player-Game": 30,
    "chomp_game": 15
}

def run_syfco(args):
    result = subprocess.run(["syfco"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()

def quantify_mona_content(original_content, unobservables):
    lines = original_content.splitlines()
    new_lines = []
    formula_started = False
    for line in lines:
        if line.strip().startswith('var2') and not formula_started:
            new_lines.append(line)
            if unobservables:
                quant_prefix = " ".join([f"all2 {var.upper()}:" for var in sorted(list(unobservables))])
                new_lines.append(f"{quant_prefix} (")
                formula_started = True
        else:
            new_lines.append(line)
    
    if formula_started:
        last_line = new_lines[-1]
        if last_line.strip().endswith(';'):
            new_lines[-1] = last_line.rstrip(';') + ");"
        else:
            new_lines.append(");")
            
    return "\n".join(new_lines) + "\n"

def negate_mona_content(content):
    lines = content.splitlines()
    formula_idx = -1
    for i, line in enumerate(lines):
        clean = line.strip()
        if clean and not clean.startswith('#') and not clean.startswith('m2l-str') and not clean.startswith('var2'):
            formula_idx = i
            break
            
    if formula_idx != -1:
        formula = lines[formula_idx].strip()
        if formula.endswith(';'):
            lines[formula_idx] = "~(" + formula.rstrip(';') + ");"
        else:
            lines[formula_idx] = "~(" + formula + ");"
                
    return "\n".join(lines) + "\n"

def run_single_mona_task(task_tuple):
    mona_file, dfa_file = task_tuple
    try:
        mona_path = Path(mona_file)
        if not mona_path.exists(): 
            return False
            
        with open(dfa_file, 'w') as f:
            subprocess.run(['mona', '-u', '-xw', str(mona_file)], stdout=f, check=True)
        return True
    except Exception as e:
        print(f"Error running MONA on {mona_file}: {e}")
        return False

def main():
    benchmarks = []
    root_path = Path("/home/cowclaw/ltlf-po-benchmarks")
    tlsf_fin_path = root_path / "SYNTCOMP-benchmarks/tlsf-fin"

    for category, limit in categories.items():
        category_path = tlsf_fin_path / category
        if not category_path.exists():
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
                selected.extend(random.sample(others, min(len(others), limit - len(selected))))
        
        for f in selected:
            benchmarks.append(str(f.relative_to(root_path)))

    print(f"Collected {len(benchmarks)} benchmarks total.")

    base_dir = Path("/home/cowclaw/ltlf-po-benchmarks/ltlf-fin-benchmarks")
    ltlf_dir = base_dir / "ltlf"
    mso_dir = base_dir / "mso"
    part_dir = base_dir / "part"

    levels = ["1-2", "all"]
    po_dirs = {level: base_dir / f"po-part-{level}" for level in levels}
    hpc_mona_dir = base_dir / "hpc-mona"

    if base_dir.exists():
        shutil.rmtree(base_dir)

    ltlf_dir.mkdir(parents=True, exist_ok=True)
    mso_dir.mkdir(parents=True, exist_ok=True)
    part_dir.mkdir(parents=True, exist_ok=True)
    hpc_mona_dir.mkdir(parents=True, exist_ok=True)
    for d in po_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    LTFL2FOL = "/home/cowclaw/lucas/Syft/build/bin/ltlf2fol"
    LTFL2PFOL = "/home/cowclaw/lucas/Syft/build/bin/ltlf2pfol"

    mona_tasks = []

    for tlsf_rel_path in benchmarks:
        tlsf_path = root_path / tlsf_rel_path
        stem = tlsf_path.stem
        
        ltlf_file = ltlf_dir / f"{stem}.ltlf"
        mso_file = mso_dir / f"{stem}.mona"
        rev_mona_file = mso_dir / f"{stem}.mona.rev"
        rev_neg_mona_file = mso_dir / f"{stem}.mona.rev.neg"
        
        part_file = part_dir / f"{stem}.part"
        
        print(f"Processing {stem}...")
        
        ltl_formula = run_syfco(["-f", "ltlxba-fin", str(tlsf_path)])
        
        if ltl_formula:
            ltl_formula = ltl_formula.replace("X[!]", "N")
            with open(ltlf_file, "w") as f:
                f.write(ltl_formula + "\n")
            
            try:
                with open(mso_file, "w") as f:
                    subprocess.run([LTFL2FOL, "NNF", str(ltlf_file)], stdout=f, check=True)
                mona_tasks.append((mso_file, mso_dir / f"{stem}.dfa"))
            except Exception as e:
                print(f"Warning: Failed to generate MONA for {stem}: {e}")
                if mso_file.exists(): mso_file.unlink()
                
            try:
                with open(rev_neg_mona_file, "w") as f:
                    subprocess.run([LTFL2PFOL, str(ltlf_file)], stdout=f, check=True)
                
                with open(rev_neg_mona_file, "r") as f:
                    rev_neg_content = f.read()
                
                unnegated = rev_neg_content
                if "~(" in rev_neg_content: unnegated = rev_neg_content.replace("~(", "(", 1)
                elif "~" in rev_neg_content: unnegated = rev_neg_content.replace("~", "", 1)
                    
                with open(rev_mona_file, "w") as f:
                    f.write(unnegated)
                
                mona_tasks.append((rev_mona_file, mso_dir / f"{stem}.dfa.rev"))
                mona_tasks.append((rev_neg_mona_file, mso_dir / f"{stem}.dfa.rev.neg"))
            except Exception as e:
                print(f"Warning: Failed to generate reversed MONA for {stem}: {e}")
                
        else:
            print(f"Skipping {stem} due to conversion failure.")
            continue
        
        inputs = run_syfco(["-ins", str(tlsf_path)])
        outputs = run_syfco(["-outs", str(tlsf_path)])
        
        if inputs is not None and outputs is not None:
            input_list = [i.strip(";,") for i in inputs.replace(",", " ").split() if i.strip(";,")]
            output_list = [o.strip(";,") for o in outputs.replace(",", " ").split() if o.strip(";,")]
            
            fo_mso_dir = base_dir / "po-mso-0"
            fo_mso_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mso_file, fo_mso_dir / f"{stem}.mona")
            shutil.copy2(mso_file, fo_mso_dir / f"{stem}.mona.quant")
            if rev_mona_file.exists(): shutil.copy2(rev_mona_file, fo_mso_dir / f"{stem}.mona.rev")
            if rev_neg_mona_file.exists(): shutil.copy2(rev_neg_mona_file, fo_mso_dir / f"{stem}.mona.rev.neg")
            
            mona_tasks.append((fo_mso_dir / f"{stem}.mona", fo_mso_dir / f"{stem}.dfa"))
            mona_tasks.append((fo_mso_dir / f"{stem}.mona.quant", fo_mso_dir / f"{stem}.dfa.quant"))
            if rev_mona_file.exists(): mona_tasks.append((fo_mso_dir / f"{stem}.mona.rev", fo_mso_dir / f"{stem}.dfa.rev"))
            if rev_neg_mona_file.exists(): mona_tasks.append((fo_mso_dir / f"{stem}.mona.rev.neg", fo_mso_dir / f"{stem}.dfa.rev.neg"))

            with open(part_file, "w") as f:
                f.write(f"inputs {' '.join(input_list)}\n")
                f.write(f"outputs {' '.join(output_list)}\n")
            
            for ext in [".part.quant", ".part.rev.neg"]:
                shutil.copy2(part_file, part_dir / f"{stem}{ext}")

            if len(input_list) > 0:
                for level in levels:
                    count = {"1-4": len(input_list)//4, "1-2": len(input_list)//2, "3-4": (3*len(input_list))//4, "all": len(input_list)}[level]
                    count = max(1, count) if level != "all" else count
                    
                    unobs = random.sample(input_list, count)
                    rem = [i for i in input_list if i not in unobs]
                    
                    level_part_dir = po_dirs[level]
                    level_mso_dir = base_dir / f"po-mso-{level}"
                    level_mso_dir.mkdir(parents=True, exist_ok=True)
                    
                    po_file = level_part_dir / f"{stem}.part"
                    with open(po_file, "w") as f:
                        f.write(f"inputs {' '.join(rem)}\n")
                        f.write(f"outputs {' '.join(output_list)}\n")
                        if unobs: f.write(f"unobservables {' '.join(unobs)}\n")
                    
                    for ext in [".part.quant", ".part.rev.neg"]:
                        shutil.copy2(po_file, level_part_dir / f"{stem}{ext}")
                    
                    shutil.copy2(mso_file, level_mso_dir / f"{stem}.mona")
                    if rev_mona_file.exists(): shutil.copy2(rev_mona_file, level_mso_dir / f"{stem}.mona.rev")
                    if rev_neg_mona_file.exists(): shutil.copy2(rev_neg_mona_file, level_mso_dir / f"{stem}.mona.rev.neg")
                    
                    quant_mona = level_mso_dir / f"{stem}.mona.quant"
                    with open(mso_file, "r") as f: mso_content = f.read()
                    with open(quant_mona, "w") as f: f.write(quantify_mona_content(mso_content, unobs))
                    
                    mona_tasks.append((level_mso_dir / f"{stem}.mona", level_mso_dir / f"{stem}.dfa"))
                    mona_tasks.append((quant_mona, level_mso_dir / f"{stem}.dfa.quant"))
                    if rev_mona_file.exists(): mona_tasks.append((level_mso_dir / f"{stem}.mona.rev", level_mso_dir / f"{stem}.dfa.rev"))
                    if rev_neg_mona_file.exists(): mona_tasks.append((level_mso_dir / f"{stem}.mona.rev.neg", level_mso_dir / f"{stem}.dfa.rev.neg"))
            else:
                for level in ["1-4", "1-2", "3-4", "all"]:
                    shutil.copy2(part_file, po_dirs[level] / f"{stem}.part")

    print(f"Preparation complete. Collected {len(mona_tasks)} MONA/DFA generation tasks.")
    
    # Export mona_tasks to a JSON file for HPC
    # We want relative paths to ltlf-fin-benchmarks for portability
    exported_tasks = []
    for mona_file, dfa_file in mona_tasks:
        # Copy mona files to hpc_mona_dir for easier transfer
        mona_name = mona_file.name
        if "po-mso-" in str(mona_file):
            prefix = mona_file.parent.name
            mona_name = f"{prefix}_{mona_file.name}"
        
        target_mona = hpc_mona_dir / mona_name
        shutil.copy2(mona_file, target_mona)
        
        exported_tasks.append({
            "mona_file": str(target_mona.relative_to(base_dir)),
            "dfa_file": str(dfa_file.relative_to(base_dir))
        })

    with open(base_dir / "mona_tasks.json", "w") as f:
        json.dump(exported_tasks, f, indent=2)

    print(f"Done. Files prepared in ltlf-fin-benchmarks. Tasks exported to {base_dir}/mona_tasks.json")

if __name__ == "__main__":
    main()
