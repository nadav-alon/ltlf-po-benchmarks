import subprocess
import os
import sys
import re
import csv 
from pathlib import Path
import time 
import tempfile
import argparse
import threading
import shutil
import platform
from datetime import datetime
import json

def parse_part_dir(part_dir, sample_id=1):
    """
    Parses part directory name to extract level and sample index.
    Supports formats: 'part', 'po-part-LEVEL', 'po-part-LEVEL_SAMPLEID'
    Returns (level, s_idx, is_part_dir, has_explicit_sample)
    """
    match = re.search(r"(?:po-)?part(?:-(.+?))?(?:_(\d+))?$", part_dir)
    if match:
        level = match.group(1) if match.group(1) else "part"
        has_explicit_sample = match.group(2) is not None
        s_idx = int(match.group(2)) if has_explicit_sample else sample_id
        return level, s_idx, True, has_explicit_sample
    return part_dir, sample_id, False, False


def get_git_revision_hash():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], 
                                     cwd=os.path.dirname(os.path.abspath(__file__)),
                                     stderr=subprocess.DEVNULL).decode('ascii').strip()
    except Exception:
        return "unknown"


def get_system_info():
    info = {
        'cpu': platform.processor() or "unknown",
        'cores': os.cpu_count(),
        'mem': 'unknown',
        'os': f"{platform.system()} {platform.release()}"
    }
    try:
        if sys.platform == "linux":
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            info['cpu'] = line.split(":")[1].strip()
                            break
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if "MemTotal" in line:
                            val_kb = int(line.split(":")[1].strip().split()[0])
                            info['mem'] = f"{val_kb / (1024*1024):.2f} GB"
                            break
    except Exception:
        pass
    return info

def get_spot_version():
    try:
        result = subprocess.run(["ltlfsynt", "--version"], capture_output=True, text=True, check=True)
        return result.stdout.splitlines()[0].strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


class Solver():
    def __init__(self, path, name=None):
        self.path = Path(path).expanduser().resolve()
        self.name = name if name else str(self.path)

    def get_command(self, input_file, part_file, mode, semantics="moore", verify=False, on_the_fly=True)-> str:
        """Returns the command string to execute.

        Args:
            input_file (str): The input file path.
            part_file (str): The part file path.
            mode (str): The mode.
            semantics (str): The semantics (mealy/moore).
        Returns:
            str: The command string to execute.
        """
        raise NotImplementedError

    def parse_output(self, output_bytes)-> (int, float, str):
        """Returns (result_code, time_ms, time_source) from tool output. 
        result: 1=Realizable, 0=Unrealizable, None=Unknown
        time_source: 'tool' or None
        """
        raise NotImplementedError

    def preprocess(self, input_file, part_file, mode, semantics="moore", verify=False)-> float:
        """Returns the time spent on preprocessing (e.g., automaton construction) in ms."""
        return 0.0

    def get_name(self)-> str:
        return self.name


def get_variables_from_part(part_file, var_type='all'):
    vars = set()
    targets = ['inputs', 'outputs', 'unobservables'] if var_type == 'all' else [var_type]
    
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Normalize line: replace ':' with ' ' and split
                clean_line = line.replace(':', ' ')
                parts = clean_line.split()
                if not parts: continue
    
                header = parts[0]
                if header.startswith('.'):
                    header = header[1:]
                
                if header in targets:
                    vars.update(parts[1:])
                    
    return sorted(list(vars))


def get_unobservables_from_part(part_file):
    unobs = set()
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip().lower()
                if '.unobservables:' in line:
                    unobs.update(line.split(':')[1].strip().split())
                elif line.startswith('unobservables'):
                    line_content = line.replace(':', ' ').split()
                    if len(line_content) > 1:
                        unobs.update(line_content[1:])
    return unobs


def get_semantics_from_part(part_file):
    """Parses semantics (mealy/moore) from the part file if present."""
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip().lower()
                if line.startswith('semantics'):
                    parts = line.split()
                    if len(parts) > 1:
                        val = parts[1].strip()
                        if val in ['mealy', 'moore']:
                            return val
    return None


def get_safe_true(part_file, exclude_unobs=False):
    vars = set(get_variables_from_part(part_file))
    if exclude_unobs:
        unobs = get_unobservables_from_part(part_file)
        vars = vars - unobs
    
    if not vars:
        return "true"
    # Return a list of tautologies, one for each variable
    return " && ".join([f"{v} | ~{v}" for v in sorted(list(vars))])

def normalize_part_with_dots(content):
    new_content = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed: continue
        if trimmed.lower().startswith('semantics'): continue
        if not trimmed.startswith('.'):
            if trimmed.lower().startswith('inputs'):
                line = '.inputs: ' + ' '.join(trimmed.split()[1:]).replace(':', '')
            elif trimmed.lower().startswith('outputs'):
                line = '.outputs: ' + ' '.join(trimmed.split()[1:]).replace(':', '')
            elif trimmed.lower().startswith('unobservables'):
                line = '.unobservables: ' + ' '.join(trimmed.split()[1:]).replace(':', '')
        new_content.append(line)
    new_content = '\n'.join(new_content)
    return new_content

def quantify_mona_content(original_content, unobservables):
    """
    Quantifies the MONA formula based on the unobservables list.
    Collects all variables from var2 declarations and outputs a single unified var2 line.
    """
    lines = original_content.splitlines()
    new_lines = []
    
    all_vars = []
    unobs_set = {v.strip().upper() for v in unobservables}
    
    # First pass: collect all variables and filter out non-header/non-var2 lines
    m2l_line = None
    header_comment = None
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('var2'):
            # Format: var2 V1, V2, ...;
            vars_part = stripped[4:].rstrip(';').replace(',', ' ').split()
            all_vars.extend(vars_part)
        elif stripped.startswith('m2l-str'):
            m2l_line = line
        elif stripped.startswith('#'):
            if not header_comment:
                header_comment = line
        elif stripped:
            # This is likely the start of the formula
            break
            
    # Remove duplicates from all_vars but preserve order if possible
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
        
    # Second pass: append the actual formula
    formula_lines = []
    in_formula = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('var2') and not stripped.startswith('m2l-str') and not stripped.startswith('#'):
            in_formula = True
        if in_formula:
            formula_lines.append(line)
            
    if formula_lines:
        formula_str = "\n".join(formula_lines).strip()
        if formula_str.endswith(';'):
            formula_str = formula_str[:-1]
        new_lines.append(formula_str)
        
    if unobservables:
        new_lines.append(");")
    else:
        # If no quantification, still need the semicolon
        if new_lines and not new_lines[-1].strip().endswith(';'):
             new_lines[-1] = new_lines[-1].rstrip() + ";"

    return "\n".join(new_lines) + "\n"

def negate_mona_content(original_content):
    """
    Negates the MONA formula. Based on lucas-negate.py.
    """
    lines = original_content.splitlines()
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

class ChristianSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode, semantics, verify=False, on_the_fly=True)-> str:
        # Christian's Syft expects .main and .backup files
        # and handles ltlf2fol conversion internally
        
        if not part_file.endswith('.christian.part'):
            christian_part = part_file + '.christian.part'
            if not os.path.exists(christian_part):
                with open(part_file, 'r') as f:
                    content = f.read()
                # Christian's tool expects .inputs: .outputs: .unobservables:
                
                new_content = normalize_part_with_dots(content)
                with open(christian_part, 'w') as f:
                    f.write(new_content)
            part_file = christian_part

        if not input_file.endswith('christian.ltlf'):
            christian_input = input_file + '.christian.ltlf'
            if not os.path.exists(christian_input):
                with open(input_file, 'r') as f:
                    content = f.read().strip()
                
                # Christian's Syft expects the .ltlf file to have exactly 2 lines:
                # Line 1: main formula (usually a tautology in MSO mode to define alphabet)
                # Line 2: backup formula (the spec to be quantified)
                # For MSO mode, we MUST exclude unobservables from line 1 so they don't stay free in MONA.
                safe_true = get_safe_true(part_file, exclude_unobs=(mode == 'mso'))
                
                with open(christian_input, 'w') as f:
                    f.write(safe_true + '\n')
                    f.write(content + '\n')
                    
            input_file = christian_input
        
        # Christian's Syft takes the .ltlf file and handles conversion internally
        sem_val = 1 if semantics == "mealy" else 0
        return f'"{self.path}" {input_file} {part_file} {sem_val} {mode}'

    def parse_output(self, output_bytes)-> (int, float, str):
        l_str = output_bytes.decode('utf-8', errors='ignore')
        lines = l_str.split("\n")
        time_ms = 0.0
        time_source = None
        
        # Search for a line that looks like it contains the total time
        # Christian's tool often prints it at the end
        for line in reversed(lines):
            # Look for a line with just a float (time in ms), support scientific notation
            rr = re.findall(r"^([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)$", line.strip())
            if rr:
                time_ms = float(rr[0])
                time_source = "tool"
                break

        result = None 
        if "Unrealizable" in l_str:
            result = 0
        if "Realizable" in l_str:
            result = 1

        return result, time_ms, time_source


class LucasSyftSolver(Solver):
    def preprocess(self, input_file, part_file, mode, semantics="moore", verify=False)-> float:
        """
        Dynamically generates the MONA DFA from the LTLf file.
        Detects ltlf2fol and ltlf2pfol in the Syft directory.
        """
        # Mapping mode to tools and suffixes
        # belief-states -> ltlf2fol -> dfa
        # projection-based -> ltlf2pfol -> negate -> dfa.rev.neg
        # mso -> ltlf2fol -> quantify -> dfa.quant
        
        config = {
            "belief-states":    ("ltlf2fol",  ".dfa",         None),
            "projection-based": ("ltlf2pfol", ".dfa.rev.neg", "negate"),
            "mso":              ("ltlf2fol",  ".dfa.quant",   "quantify")
        }
        tool_name, dfa_suffix, post_process = config.get(mode, ("ltlf2fol", ".dfa", None))
        
        syft_bin_dir = self.path.parent
        tool_path = syft_bin_dir / tool_name
        
        if not tool_path.exists():
            print(f"[{self.get_name()}] Error: Tool {tool_path} not found.")
            return 0.0

        target_dfa = os.path.join(os.path.dirname(input_file), Path(input_file).stem + dfa_suffix)
        
        if not os.path.exists(target_dfa):
            # Pre-filter part file for Lucas to handle unobservables correctly
            filter_part_file_for_lucas(part_file)
            
            start = time.time()
            
            try:
                cmd = [str(tool_path), "NNF", input_file] if tool_name == "ltlf2fol" else [str(tool_path), input_file]
                proc = subprocess.run(cmd, text=True, capture_output=True, check=True)
                mona_content = proc.stdout
            except subprocess.CalledProcessError as e:
                print(f"[{self.get_name()}] Error running {tool_name}: {e}\n{e.stderr}")
                return 0.0

            # Step 2: Post-processing (Quantification or Negation)
            if post_process == "quantify":
                # Determine part file for quantification info
                part_suffix = ".quant" if mode == "mso" else ""
                actual_part = part_file + part_suffix
                if not os.path.exists(actual_part):
                    actual_part = part_file
                unobs = get_unobservables_from_part(actual_part)
                # Fallback to base part file if no unobservables in .quant file
                if not unobs and actual_part != part_file:
                    unobs = get_unobservables_from_part(part_file)
                mona_content = quantify_mona_content(mona_content, unobs)
            elif post_process == "negate":
                mona_content = negate_mona_content(mona_content)

            # Step 3: Compile with MONA
            mona_tmp = os.path.join(os.path.dirname(input_file), Path(input_file).stem + dfa_suffix.replace(".dfa", ".mona"))
            with open(mona_tmp, 'w') as f:
                f.write(mona_content)
                
            mona_proc = subprocess.run(["mona", "-u", "-xw", mona_tmp], text=True, capture_output=True)
            end = time.time()
            
            if mona_proc.returncode == 0:
                with open(target_dfa, 'w') as f:
                    f.write(mona_proc.stdout)
                return (end - start) * 1000
            else:
                print(f"[{self.get_name()}] MONA failed on {mona_tmp}:\n{mona_proc.stderr}")
                return 0.0
                
        return 0.0

    def get_command(self, input_file, part_file, mode, semantics, verify=False, on_the_fly=True)-> str:
        config = {
            "belief-states":    ("partial", "dfa", ".dfa", ""),
            "projection-based": ("partial", "cordfa", ".dfa.rev.neg", ".rev.neg"),
            "mso":              ("full",    "dfa", ".dfa.quant",   ".quant")
        }
        obs, inp_type, dfa_suffix, part_suffix = config.get(mode, ("partial", "dfa", ".dfa", ""))
        dfa_file = os.path.join(os.path.dirname(input_file), Path(input_file).stem + dfa_suffix)
        actual_part_file = part_file + part_suffix
        if not os.path.exists(actual_part_file):
            actual_part_file = part_file
        
        if not os.path.exists(dfa_file):
            print(f"[{self.get_name()}] Error: {dfa_file} not found. Preprocess may have failed.")
            return ""
        
        if globals().get('args') and args.dry_run:
            if not os.path.exists('dry_run_results'):
                os.mkdir('dry_run_results')
            with open(os.path.join('dry_run_results', Path(input_file).stem + f'.{mode}.dfa'), 'w') as f:
                print(f'writing {dfa_file} to {f.name}')
                with open(dfa_file, 'r') as d:
                    f.write(d.read())

        sem_val = 1 if semantics == "mealy" else 0
        return f'"{self.path}" {dfa_file} {actual_part_file} {sem_val} {obs} {inp_type}'

    def parse_output(self, output_bytes):
        # Reuse logic or customize if lucas output differs significantly
        l_str = output_bytes.decode('utf-8', errors='ignore')
        result = None 
        if "unrealizable" in l_str: result = 0
        elif "realizable" in l_str: result = 1
        
        # Lucas Syft often prints time in ms at the end
        lines = l_str.strip().split("\n")
        time_ms = 0.0
        time_source = None
        for line in reversed(lines):
            rr = re.findall(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*ms", line)
            if rr:
                time_ms = float(rr[0])
                time_source = "tool"
                break

        return result, time_ms, time_source

class SpotSolver(Solver):
    def get_command(self, input_file, part_file, mode, semantics, verify=False, on_the_fly=True)-> str:
        if not part_file.endswith('.spot.part'):
            spot_part = part_file + '.spot.part'
            if not os.path.exists(spot_part):
                content = ""
                if os.path.exists(part_file):
                    with open(part_file, 'r') as f:
                        content = f.read()
                with open(spot_part, 'w') as f:
                    f.write(normalize_part_with_dots(content))
            part_file = spot_part

        transformation = f"cat {input_file} | paste -sd'&'"
        verify_flag = " --verify" if verify else ""

        restricted_flag = "" if on_the_fly else " --translation=restricted"

        if mode == "ltlf":
            if verify:
                print("Verification not supported for spot in ltlf mode.")
            
            unobs = get_unobservables_from_part(part_file)
            inputs = get_variables_from_part(part_file, "inputs")
            outputs = get_variables_from_part(part_file, "outputs")
            
            if unobs:
                all_inputs = sorted(list(set(inputs) | set(unobs)))
                # Note: using single quotes for formula and comma-separated lists to prevent shell expansion
                return f"{transformation} | ltlfsynt --part-file={part_file} --semantics={semantics} --verbose {restricted_flag} --unobservable-ins='{','.join(unobs)}'"
            
            return f"{transformation} | ltlfsynt --part-file={part_file} --semantics={semantics} --verbose {restricted_flag}"
        elif mode == "ltl":
            return f"{transformation} | ltlsynt --part-file={part_file} --verbose --algo=ds -H{verify_flag}"
        elif mode == "ltlfilt":
            with open(part_file, 'r') as f:
                content = f.read().lower()
            # add alive to outputs to account for the new variable introduced by ltlfilt --from-ltlf
            # fix: replace '.outputs:' instead of '.output' to avoid mangling the keyword
            if '.outputs:' in content:
                content = content.replace('.outputs:', '.outputs: alive ')
            elif '.output:' in content:
                content = content.replace('.output:', '.output: alive ')
            else:
                content += "\n.outputs: alive\n"
            
            
            with open(part_file, 'w') as f:
                print(f"DEBUG: Part File ({part_file}):\n{content}\n")
                f.write(content)

            unobs = get_unobservables_from_part(part_file)
            inputs = get_variables_from_part(part_file, "inputs")
            outputs = get_variables_from_part(part_file, "outputs")

            all_inputs = sorted(list(set(inputs) | set(unobs)))

            return f"{transformation} | ltlfilt --from-ltlf | ltlsynt --verbose --algo=ds -H --unobservable-ins='{', '.join(unobs)}' --ins='{', '.join(all_inputs)}' --outs='{', '.join(outputs)}'"
        else:
            print(f"[{self.get_name()}] Error: Unknown mode '{mode}' for SpotSolver.")
            return ""

    def parse_output(self, output_bytes):
        l_str = output_bytes.decode('utf-8', errors='ignore')
        result = None 
        if "UNREALIZABLE" in l_str: result = 0
        elif "REALIZABLE" in l_str: result = 1
        
        # Spot often prints multiple "done in" or "took" lines.
        # We want the 'total' if possible, or the very last summary line.
        lines = l_str.strip().split("\n")
        time_ms = 0.0
        time_source = None
        
        for line in reversed(lines):
            # Matches "took 1.23 seconds" (often total time)
            rr_sec_total = re.findall(r"took\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*seconds", line)
            if rr_sec_total:
                time_ms = float(rr_sec_total[0]) * 1000
                time_source = "tool"
                break
            # Matches "game solved in 0.000227668 seconds"
            rr_solved = re.findall(r"solved in\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*seconds", line)
            if rr_solved:
                time_ms = float(rr_solved[0]) * 1000
                time_source = "tool"
                break
            # Matches "123 ms"
            rr_ms = re.findall(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*ms", line)
            if rr_ms:
                time_ms = float(rr_ms[0])
                time_source = "tool"
                break
        
        return result, time_ms, time_source


class Statistics:
    def __init__(self):
        self.stats = {
            'realizable': 0, 
            'unrealizable': 0, 
            'timeout': 0, 
            'error': 0, 
            'inconsistent': 0, 
            'verified': 0, 
            'verification_failed': 0
        }
        self.results = {} # test_path -> (time, automaton_time, generation_time, status, verified, time_source)
        self.lock = threading.Lock()

    def add_result(self, test_path, time, automaton_time, generation_time, status, outcome, verified=None, time_source="tool"):
        with self.lock:
            self.results[str(test_path)] = (time, automaton_time, generation_time, status, verified, time_source)
            if outcome in self.stats:
                self.stats[outcome] += 1
            if verified is True:
                self.stats['verified'] += 1
            elif verified is False:
                self.stats['verification_failed'] += 1

# for statistics 
statistics = Statistics()


def collectTest(testDir, partDir="part", sample_id=1):
    global statistics
    p = Path(testDir).resolve()
    
    tests = []

    if p.is_file():
        if p.suffix == ".ltlf":
            test_files = [p]
        else:
            print(f"File {p} is not an .ltlf file.")
            return []
    else:
        test_files = list(p.rglob("**/ltlf/**/*.ltlf"))

    samples = load_samples(testDir)

    for file in test_files:
        test_path = file.resolve()
        test_stem = test_path.stem
        
        # Strategy: find the index of "ltlf" in the parts of the path
        # and replace it with "part" or "mso" to find related files
        parts = list(test_path.parts)
        if "ltlf" in parts:
            idx = parts.index("ltlf")
            part_parts = list(parts)
            part_parts[idx] = partDir
            part_file = Path(*part_parts).with_suffix(".part")
            
            level, s_idx, level_match, has_explicit_sample = parse_part_dir(partDir, sample_id)
            sample_key = f"{level}_{s_idx}_{test_stem}"

            # Skip logic: only run tests as many times as they have part files/samples
            if not part_file.exists():
                # On-the-fly generation case
                if level_match:
                    # If it's a specific sample or level entry in samples.json, check it
                    if level != "all" and level != "0" and sample_key not in samples:
                        continue
                    # Check if base part exists
                    base_part_parts = list(parts)
                    base_part_parts[idx] = "part"
                    base_part = Path(*base_part_parts).with_suffix(".part")
                    if not base_part.exists():
                        continue
                else:
                    # Non-PO levels must have part files on disk to be collected
                    continue
            else:
                # File exists on disk, but we might be running a redundant Slurm task for a singleton level
                # (e.g., Job 10 running LEVEL=all, which should only run once)
                if not level_match or not has_explicit_sample:
                    if s_idx > 1:
                        continue
                
                # For levels that DO have entries in samples.json, still respect the limit
                if level_match and sample_key not in samples and level != "all":
                     # If it's on disk but not in samples, maybe it's custom. We allow it if s_idx=1.
                     if s_idx > 1:
                         continue

            tests.append(test_path)
        else:
            print(f"Test file {test_path} not under an 'ltlf' directory, skipping.")

    return tests


TIMEOUT_CODE = -2
ERROR_CODE = -1

SAMPLES_CACHE = {}

def load_samples(test_dir_origin):
    global SAMPLES_CACHE
    
    current = Path(test_dir_origin).resolve()
    # If it's a file, start from its parent
    if current.is_file():
        current = current.parent
        
    samples_json = None
    # Search upwards for samples.json
    while current != current.parent:
        candidate = current / "samples.json"
        if candidate.exists():
            samples_json = candidate
            break
        current = current.parent
    
    if samples_json and samples_json.exists():
        samples_key = str(samples_json)
        if samples_key in SAMPLES_CACHE:
            return SAMPLES_CACHE[samples_key]
            
        try:
            with open(samples_json, "r") as f:
                data = json.load(f)
                SAMPLES_CACHE[samples_key] = data
                return data
        except Exception as e:
            print(f"Error loading samples.json: {e}")
            return {}
    else:
        # print(f"Warning: samples.json not found searching up from {test_dir_origin}")
        return {}

def filter_part_file_for_lucas(part_file):
    """
    Lucas Syft has a bug where if a variable is in both 'inputs' and 'unobservables',
    it treats it as an observable input. This function removes unobservables from inputs.
    """
    if not os.path.exists(part_file):
        return
    
    with open(part_file, 'r') as f:
        lines = f.readlines()
    
    unobs = []
    for line in lines:
        if line.lower().strip().startswith('unobservables') or line.lower().strip().startswith('.unobservables'):
            parts = line.strip().split()
            if parts[0].endswith(':'):
                unobs.extend(parts[1:])
            else:
                unobs.extend(parts[1:])
    
    if not unobs:
        return

    new_lines = []
    for line in lines:
        if line.lower().strip().startswith('inputs') or line.lower().strip().startswith('.inputs'):
            parts = line.strip().split()
            header = parts[0]
            current_inputs = parts[1:]
            filtered_inputs = [i for i in current_inputs if i not in unobs]
            new_lines.append(f"{header} {' '.join(filtered_inputs)}\n")
        else:
            new_lines.append(line)
            
    with open(part_file, 'w') as f:
        f.writelines(new_lines)

def prepare_test_artifacts(test, partDir, solver, mode, sample_id, temp_dir, test_dir_origin=None, semantics="moore"):
    """
    Sets up the test environment in temp_dir. 
    Handles on-the-fly generation of part files and MONA files.
    Returns (inputfile, partfile, actual_semantics, generation_time)
    """
    test_path = Path(test).resolve()
    test_name = test_path.name
    test_stem = test_path.stem
    
    # Strategy: find the index of "ltlf" in the parts of the path
    # and replace it with "part" or "mso" to find related files
    parts = list(test_path.parts)
    if "ltlf" not in parts:
        ltlf_idx = -1
    else:
        ltlf_idx = parts.index("ltlf")
    
    # Construct part file path
    if ltlf_idx != -1:
        part_parts = list(parts)
        part_parts[ltlf_idx] = partDir
        original_part = Path(*part_parts).with_suffix(".part")
    else:
        original_part = test_path.with_suffix(".part")

    # Construct mso directory path
    if ltlf_idx != -1:
        mso_parts = list(parts)
        mso_level = "mso"
        if partDir.startswith("po-part-"):
            mso_level = partDir.replace("po-part-", "po-mso-")
        
        mso_parts[ltlf_idx] = mso_level
        mso_dir = Path(*mso_parts).parent
    else:
        mso_dir = test_path.parent / "mso"

    inputfile = os.path.join(temp_dir, test_name)
    partfile = os.path.join(temp_dir, test_stem + ".part")

    # Copy the test files
    shutil.copy2(test, inputfile)
    
    # Determine if we need to generate part/mso on the fly
    start_gen = time.time()
    if test_dir_origin:
        benchmark_root = test_dir_origin
    elif ltlf_idx != -1:
        benchmark_root = Path(*parts[:ltlf_idx])
    else:
        benchmark_root = test_path.parent.parent
        
    samples = load_samples(benchmark_root)
    level, s_idx, level_match, has_explicit_sample = parse_part_dir(partDir, sample_id)
    sample_key = f"{level}_{s_idx}_{test_stem}"
    unobs = None
    
    # We use on-the-fly generation if:
    # 1. We found an entry in samples.json
    # 2. OR the level is FO (0) or FU (all)
    if sample_key in samples:
        unobs = samples[sample_key]
    elif level == "0":
        unobs = []
    elif level == "all":
        # FU fallback: unobs is everything. We'll extract it from base_part later.
        unobs = "ALL_VARS" 

    if unobs is not None:
        # Generate .part file on the fly
        if original_part.exists() and not (sample_key in samples or level in ["all", "0"]):
            shutil.copy2(original_part, partfile)
        else:
            # Need base part info
            if ltlf_idx != -1:
                base_part_parts = list(parts)
                base_part_parts[ltlf_idx] = "part"
                base_part = Path(*base_part_parts).with_suffix(".part")
            else:
                base_part = original_part # Fallback
            
            if base_part.exists():
                with open(base_part, "r") as f:
                    base_content = f.read()
                
                # Heuristic: decide if it needs a dot based on base file style
                has_dots = any(line.strip().startswith(".") for line in base_content.splitlines())
                
                # Ensure unobservables is at the end or replaced
                new_content = []
                for line in base_content.splitlines():
                    trimmed = line.strip().lower()
                    if not (trimmed.startswith("unobservables") or trimmed.startswith(".unobservables")):
                        new_content.append(line)
                
                if unobs == "ALL_VARS":
                    unobs = sorted(get_variables_from_part(base_part, "inputs"))
                
                if unobs:
                    keyword = ".unobservables:" if has_dots else "unobservables"
                    new_content.append(f"{keyword} {' '.join(unobs)}")
                
                with open(partfile, "w") as f:
                    f.write("\n".join(new_content) + "\n")
            else:
                unobs = [] # Fallback
                print(f"Warning: Base part file {base_part} not found for on-the-fly generation.")

        # Generate .mona.quant on the fly if needed
        if mode == "mso" or "lucas" in solver.get_name():
            if ltlf_idx != -1:
                base_mona_parts = list(parts)
                base_mona_parts[ltlf_idx] = "mso"
                base_mona = Path(*base_mona_parts).with_suffix(".mona")
            else:
                base_mona = mso_dir / (test_stem + ".mona")
            
            if base_mona.exists():
                with open(base_mona, "r") as f:
                    mona_content = f.read()
                quant_content = quantify_mona_content(mona_content, unobs)
                with open(os.path.join(temp_dir, test_stem + ".mona.quant"), "w") as f:
                    f.write(quant_content)
                # Also copy base for belief-states if needed
                shutil.copy2(base_mona, os.path.join(temp_dir, test_stem + ".mona"))
            else:
                print(f"Warning: Base MONA file {base_mona} not found.")

    else:
        # Traditional behavior
        if original_part.exists():
            shutil.copy2(original_part, partfile)
        else:
            print(f"Warning: Part file {original_part} not found.")
    generation_time = (time.time() - start_gen) * 1000
    
    # Copy DFA files if they exist (next to the .ltlf file)
    for dfa_suffix in [".dfa", ".dfa.rev.neg", ".dfa.quant"]:
        dfa_src = str(test) + dfa_suffix
        if os.path.exists(dfa_src):
            shutil.copy2(dfa_src, inputfile + dfa_suffix)
    
    # Copy part file variants if they exist
    for part_suffix in [".rev.neg", ".quant"]:
        part_src = str(original_part) + part_suffix
        if os.path.exists(part_src):
            shutil.copy2(part_src, partfile + part_suffix)
    
    # Copy .mona and .dfa files from mso directory if they exist
    if mso_dir.exists():
        suffixes = [".mona", ".mona.rev.neg", ".mona.rev", ".mona.quant", ".dfa", ".dfa.rev.neg", ".dfa.rev", ".dfa.quant"]
        for sfx in suffixes:
            src = mso_dir / (test_stem + sfx)
            if src.exists():
                dst = os.path.join(temp_dir, test_stem + sfx)
                if not os.path.exists(dst): # Don't overwrite what we might have generated
                    shutil.copy2(src, dst)

    # Auto-detect semantics from part file
    part_semantics = get_semantics_from_part(partfile)
    actual_semantics = part_semantics if part_semantics else semantics

    if 'lucas' in solver.get_name():
        with open(inputfile, 'r') as f:
            content = f.read()
        
        with open(inputfile, 'w') as f:
            content = content.replace("X[!]", "*").replace("X", "N").replace("*", "X")
            f.write(content)
    
    if os.path.exists(partfile):
        with open(partfile, 'r') as f:
            content = f.read()
    
        with open(partfile, 'w') as f:
            if content.splitlines() and content.splitlines()[0].startswith("semantics"):
                f.write("\n".join(content.splitlines()[1:]))
            else:
                f.write(content)
    
    return inputfile, partfile, actual_semantics, generation_time

def executeTest(test, timeout, solver: Solver, partDir="part", mode="direct", iter_count=1, semantics="moore", results_dir=None, verify=False, test_dir_origin=None, on_the_fly=True, sample_id=1):
    test_path = Path(test).resolve()
    generation_time = 0.0
    temp_dir = tempfile.mkdtemp()
    try:
        
        # Determine relative path for result saving
        rel_path = test_path.name
        if results_dir and test_dir_origin:
            try:
                rel_path = test_path.relative_to(Path(test_dir_origin).resolve())
            except ValueError:
                pass
        
        inputfile, partfile, actual_semantics, generation_time = prepare_test_artifacts(
            test, partDir, solver, mode, sample_id, temp_dir, test_dir_origin, semantics
        )
        if actual_semantics != semantics:
             print(f"[{test_path.name}] Using semantics from part file: {actual_semantics}")

        automaton_time = solver.preprocess(inputfile, partfile, mode, actual_semantics, verify=verify)
        command = solver.get_command(inputfile, partfile, mode, actual_semantics, verify=verify, on_the_fly=on_the_fly)
        if globals().get('args') and args.dry_run:
            print(f"[{test_path.name}] Command: {command}")
            if not os.path.exists('dry_run_results'):
                os.mkdir('dry_run_results')
            with open(os.path.join('dry_run_results', test_path.name), 'w') as f:
                f.write(command)
            with open(os.path.join('dry_run_results', test_path.name + '.part'), 'w') as f:
                with open(partfile, 'r') as p:
                    f.write(p.read())
            return
        if not command:
            statistics.add_result(test, 0, automaton_time, generation_time, ERROR_CODE, "error")
            return

        times = []
        time_sources = []
        results = []
        last_output = b""
        verify_status = None # None means not performed, True/False for success/fail

        for i in range(iter_count):
            try:
                try:
                    start_wall = time.time()
                    l = subprocess.check_output(command, timeout=timeout, shell=True, cwd=solver.path.parent, stderr=subprocess.STDOUT)
                    end_wall = time.time()
                    last_output = l
                except subprocess.CalledProcessError as e:
                    end_wall = time.time()
                    last_output = e.output
                    # Some tools might return non-zero exit codes even if they produced a valid result.
                    # We try to parse the output; if it contains a valid result, we treat it as success.
                    result, t_val, t_source = solver.parse_output(e.output)
                    if result is not None:
                        l = e.output
                    else:
                        raise e

                result, t_val, t_source = solver.parse_output(l)
                if result is None:
                    print(f"raw output: {l}")
                    expected = get_expected_result(test_path)
                    outcome = "failed" if expected is not None else "other"
                    statistics.add_result(test, t_val, automaton_time, 0, outcome, time_source=t_source or "wall")
                    print(f"Failed to parse output for {test}")
                    return
                
                # If tool didn't report time, use wall clock measurement
                if t_val == 0.0 or t_source is None:
                    t_val = (end_wall - start_wall) * 1000
                    t_source = "wall"

                results.append(result)
                times.append(t_val)
                time_sources.append(t_source)
                
                if verify and result == 1:
                    # For Spot tools, if --verify was passed, we assume it's valid if exit code was 0
                    # and it's realizable. For other tools, we might need more logic.
                    if "spot" in solver.get_name():
                        # If we reached here, exit code was 0 (or handled in CalledProcessError)
                        # and it was realizable. 
                        # We should also check for "Verification failed" if we want to be sure.
                        l_str = l.decode('utf-8', errors='ignore')
                        if "Verification failed" in l_str:
                            verify_status = False
                        else:
                            verify_status = True

            except subprocess.TimeoutExpired:
                print(f"Timeout for {test}")
                results.append(TIMEOUT_CODE)
                times.append(timeout * 1000) # Store in ms
                time_sources.append("wall")
                continue

            except subprocess.CalledProcessError as e:
                print(f"Failed to run {test}: {e}, {e.output}")
                results.append(ERROR_CODE)
                times.append(0)
                time_sources.append("wall")
                continue
        

        average_time = sum(times) / len(times) if times else 0
        final_time_source = time_sources[0] if time_sources else "wall"
        
        # Save results to results_dir if specified
        if results_dir:
            test_res_dir = Path(results_dir) / rel_path
            test_res_dir.mkdir(parents=True, exist_ok=True)
            
            with open(test_res_dir / "output.log", "wb") as f:
                header = f"# Test: {test}\n"
                header += f"# Command: {command}\n"
                header += f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                header += f"# Solver: {solver.get_name()}\n"
                header += f"# Mode: {mode}\n"
                header += f"# Semantics: {actual_semantics} (detected: {part_semantics})\n"
                header += f"# Reported Runtime: {average_time:.2f} ms ({final_time_source})\n"
                header += f"# Automaton Construction Time: {automaton_time:.2f} ms\n"
                header += f"# Resource Generation Time: {generation_time:.2f} ms\n"
                header += "-" * 40 + "\n"
                f.write(header.encode('utf-8'))
                f.write(last_output)
            
            # If it's realizable and contains HOA, save it
            if results and results[0] == 1:
                l_str = last_output.decode('utf-8', errors='ignore')
                # Improved HOA extraction regex to be more robust
                hoa_match = re.search(r"(HOA:[\s\S]*?--END--)", l_str, re.MULTILINE)
                if hoa_match:
                    with open(test_res_dir / "controller.hoa", "w") as f:
                        f.write(hoa_match.group(1))
                elif "HOA:" in l_str:
                    # Fallback for if --END-- is missing or differently formatted
                    lines = l_str.splitlines()
                    start_idx = -1
                    for i, line in enumerate(lines):
                        if line.startswith("HOA:"):
                            start_idx = i
                            break
                    if start_idx != -1:
                        with open(test_res_dir / "controller.hoa", "w") as f:
                            f.write("\n".join(lines[start_idx:]))
        if TIMEOUT_CODE in results:
            outcome = "timeout"
        elif ERROR_CODE in results:
            outcome = "error"
        elif not all(elem == results[0] for elem in (results if results else [None])):
            outcome = "inconsistent"
        else:
            status = results[0] if results else ERROR_CODE
            if status == 1:
                outcome = "realizable"
            elif status == 0:
                outcome = "unrealizable"
            else:
                outcome = "error"
        
        statistics.add_result(test, average_time, automaton_time, generation_time, results[0] if results else ERROR_CODE, outcome, verified=verify_status, time_source=final_time_source)
    finally:
        shutil.rmtree(temp_dir)
        


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

if __name__ == "__main__":
    MODES = [
        "christian:direct", "christian:belief", "christian:mso",
        "lucas:belief-states", "lucas:projection-based", "lucas:mso",
        "spot:ltlf", "spot:ltl", "spot:ltlfilt"
    ]
    parser = argparse.ArgumentParser(description="Run tests for Syft.")
    parser.add_argument("--timeout", type=int, default=1500, help="Timeout in seconds")
    parser.add_argument("--iter", type=int, default=1, help="Number of iterations")
    parser.add_argument("--mode", type=str, required=True, help="Algorithm mode", choices=MODES)
    parser.add_argument("--path", type=str, help="Path to Syft executable")
    parser.add_argument("--test-dir", type=str, default="lucas", help="Test directory")
    parser.add_argument("--output", type=str, help="Output file")
    parser.add_argument("--shard-id", type=int, default=0, help="Shard index (0-indexed)")
    parser.add_argument("--num-shards", type=int, default=1, help="Total number of shards")
    parser.add_argument("--semantics", type=str, default="moore", choices=["moore", "mealy"], help="Semantics")
    parser.add_argument("--part-dir", type=str, default="part", help="Part directory name (relative to ltlf directory)")
    parser.add_argument("--results-dir", type=str, help="Directory to save detailed results (logs, controllers)")
    parser.add_argument("--verify", action="store_true", help="Perform verification on the resulting controller")
    parser.add_argument("--on-the-fly", type=str2bool, nargs='?', const=True, default=True, help="Perform translation on the fly")
    parser.add_argument("--sample-id", type=int, default=1, help="Sample index for singleton levels")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of tests to run (0 for all)")
    parser.add_argument("--filter", type=str, help="Filter tests by name (substring match)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    args = parser.parse_args()

    commit_hash = get_git_revision_hash()

    print("Starting Run with Parameters:")
    print(f"  Mode: {args.mode}")
    print(f"  Test Dir: {args.test_dir}")
    print(f"  Part Dir: {args.part_dir}")
    print(f"  Semantics: {args.semantics}")
    print(f"  Shard: {args.shard_id}/{args.num_shards}")
    print(f"  On The Fly: {args.on_the_fly}")
    print("-" * 30)

    # Derive solver and internal mode
    solver_name, internal_mode = args.mode.split(":")
    
    # Expand user path and validate
    syft_path = Path(args.path or "").expanduser().resolve()
    if not syft_path.exists() and solver_name != "spot":
        print(f"Error: Syft executable not found at {syft_path}")
        sys.exit(1)

    test_dir = args.test_dir
    timeout = args.timeout
    iterations = args.iter
    
    solver = ChristianSyftSolver(str(syft_path), name="christian") \
        if solver_name == 'christian' else LucasSyftSolver(str(syft_path), name="lucas") \
        if solver_name == 'lucas' else SpotSolver(str(syft_path), name="spot") 
    
    tests = sorted(collectTest(test_dir, args.part_dir, args.sample_id))
    
    if args.filter:
        tests = [t for t in tests if args.filter in t.name]
        print(f"Filtered to {len(tests)} tests matching '{args.filter}'")

    if args.limit > 0:
        print(f"Limiting to first {args.limit} tests globally.")
        tests = tests[:args.limit]

    if args.num_shards > 1:
        total_tests = len(tests)
        tests = tests[args.shard_id::args.num_shards]
        print(f"Shard {args.shard_id}/{args.num_shards}: Running {len(tests)} out of {total_tests} tests.")
    else:
        print(f"Running all {len(tests)} tests.")

    for test in tests:
        executeTest(test, timeout, solver, args.part_dir, internal_mode, iterations, args.semantics, 
                    results_dir=args.results_dir, verify=args.verify, test_dir_origin=test_dir, 
                    on_the_fly=args.on_the_fly, sample_id=args.sample_id)

    print("===========")
    print("Statistics:")
    print("===========")
    print(f"Realizable: {statistics.stats['realizable']}")
    print(f"Unrealizable: {statistics.stats['unrealizable']}")
    print(f"Timeout: {statistics.stats['timeout']}")
    print(f"Error: {statistics.stats['error']}")
    print(f"Inconsistent: {statistics.stats['inconsistent']}")
    if args.verify:
        print(f"Verified: {statistics.stats['verified']}")
        print(f"Verification Failed: {statistics.stats['verification_failed']}")

    if not args.output:
        # Replace colon with underscore for a cleaner filename
        safe_mode = args.mode.replace(":", "_")
        safe_semantics = args.semantics.replace(":", "_")
        output_file = f"results_{safe_mode}_{safe_semantics}.csv"
    else:
        output_file = args.output

    sys_info = get_system_info()
    spot_version = get_spot_version()
    with open(output_file, "w") as csvfile:
        csvfile.write(f"# Commit: {commit_hash}\n")
        csvfile.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        csvfile.write(f"# Machine: {platform.node()}\n")
        csvfile.write(f"# Mode: {args.mode}\n")
        csvfile.write(f"# Test Dir: {args.test_dir}\n")
        csvfile.write(f"# Part Dir: {args.part_dir}\n")
        csvfile.write(f"# Semantics: {args.semantics}\n")
        csvfile.write(f"# On The Fly: {args.on_the_fly}\n")
        csvfile.write(f"# OS: {sys_info['os']}\n")
        csvfile.write(f"# CPU: {sys_info['cpu']}\n")
        csvfile.write(f"# Cores: {sys_info['cores']}\n")
        csvfile.write(f"# RAM: {sys_info['mem']}\n")
        csvfile.write(f"# Spot Version: {spot_version}\n")
        writer = csv.writer(csvfile)
        writer.writerow(["test", "time", "automaton_time", "generation_time", "status", "verified", "time_source"])
        for test, (time, auto_time, gen_time, status, verified, time_source) in statistics.results.items():
            writer.writerow([test, time, auto_time, gen_time, status, verified, time_source])



    