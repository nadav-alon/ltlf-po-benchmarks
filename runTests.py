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


class Solver():
    def __init__(self, path, name=None):
        self.path = Path(path).expanduser().resolve()
        self.name = name if name else str(self.path)

    def get_command(self, input_file, part_file, mode, semantics="moore", verify=False)-> str:
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

    def get_name(self)-> str:
        return self.name


def get_variables_from_part(part_file, var_type='all'):
    vars = set()
    postfix = '' if var_type == 'all' else var_type
    line_titles = [var_type] if var_type != 'all' else ['inputs', 'outputs', 'unobservables']
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f'.{postfix}') and ':' in line:
                    vars.update(line.split(':')[1].strip().split())
                elif any(line.startswith(k) for k in line_titles):
                    parts = line.split()
                    if len(parts) > 0 and (parts[0].endswith(':') or len(parts) > 1):
                        line_content = line.replace(':', ' ').split()
                    if len(line_content) > 1:
                        vars.update(line_content[1:])
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

def add_useless_unobservables(part_file, num_useless_unobservables):
    with open(part_file, 'r') as f:
        outputs = get_variables_from_part(part_file, 'outputs')
        unobservables = get_variables_from_part(part_file, 'unobservables')
        inputs = get_variables_from_part(part_file, 'inputs')
    with open(part_file, 'w') as f:
        f.write('.inputs: ' + ' '.join(inputs) + '\n')
        f.write('.outputs: ' + ' '.join(outputs) + '\n')
        f.write('.unobservables: ' + ' '.join(unobservables + [f'u_useless_{i}' for i in range(num_useless_unobservables)]) + '\n')

def make_fully_observable(part_file):
    with open(part_file, 'r') as f:
        outputs = get_variables_from_part(part_file, 'outputs')
        unobservables = get_variables_from_part(part_file, 'unobservables')
        inputs = get_variables_from_part(part_file, 'inputs')
    with open(part_file, 'w') as f:
        f.write('.inputs: ' + ' '.join(inputs + unobservables) + '\n')
        f.write('.outputs: ' + ' '.join(outputs) + '\n')

def get_safe_true(part_file, exclude_unobs=False):
    vars = set(get_variables_from_part(part_file))
    if exclude_unobs:
        unobs = get_unobservables_from_part(part_file)
        vars = vars - unobs
    
    if not vars:
        return "true"
    # Return a list of tautologies, one for each variable
    return " && ".join([f"{v} | ~{v}" for v in sorted(list(vars))])

def fix_part_content_for_christian(content):
    new_content = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed: continue
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

class ChristianSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode, semantics, verify=False)-> str:
        # Christian's Syft expects .main and .backup files
        # and handles ltlf2fol conversion internally
        
        if not part_file.endswith('.christian.part'):
            christian_part = part_file + '.christian.part'
            if not os.path.exists(christian_part):
                with open(part_file, 'r') as f:
                    content = f.read()
                # Christian's tool expects .inputs: .outputs: .unobservables:
                
                new_content = fix_part_content_for_christian(content)
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
    def get_command(self, input_file, part_file, mode, semantics, verify=False)-> str:
        # Configuration based on lucas-benchmarks-instructions.txt:
        # belief-states: partial dfa, uses .dfa, .part
        # projection-based: partial cordfa, uses .dfa.rev.neg, .part.rev.neg
        # mso: full dfa, uses .dfa.quant, .part.quant
        config = {
            "belief-states":    ("partial", "dfa", ".dfa", ""),
            "projection-based": ("partial", "cordfa", ".dfa.rev.neg", ".rev.neg"),
            "mso":              ("full",    "dfa", ".dfa.quant",   ".quant")
        }
        
        obs, inp_type, dfa_suffix, part_suffix = config.get(mode, ("partial", "dfa", ".dfa", ""))
        
        dfa_file = os.path.join(os.path.dirname(input_file), Path(input_file).stem + dfa_suffix)
        actual_part_file = part_file + part_suffix
        
        # Check if actual_part_file exists, else use base part_file
        if not os.path.exists(actual_part_file):
            print(f"Missing part file for {input_file}, missing suffix {part_suffix}")
            actual_part_file = part_file
        
        if not os.path.exists(dfa_file):
            # Try to find a source MONA file to generate the DFA
            # For .dfa, look for .mona; for .dfa.quant, look for .mona.quant; for .dfa.rev.neg, look for .mona.rev.neg
            mona_source_suffix = dfa_suffix.replace(".dfa", ".mona")
            stem = Path(input_file).stem
            mona_source = os.path.join(os.path.dirname(input_file), stem + mona_source_suffix)
            
            if os.path.exists(mona_source):
                # Run MONA on the source file to get the DFA
                mona_out = subprocess.run(["mona", "-u", "-xw", mona_source], text=True, capture_output=True)
                with open(dfa_file, 'w') as f:
                    f.write(mona_out.stdout)
            else:
                print(f"[{self.get_name()}] Error: {dfa_file} not found and no source {mona_source} to generate it.")
                return ""

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
    def get_command(self, input_file, part_file, mode, semantics, verify=False)-> str:
        if not part_file.endswith('.spot.part'):
            spot_part = part_file + '.spot.part'
            if not os.path.exists(spot_part):
                with open(part_file, 'r') as f:
                    content = f.read()
                with open(spot_part, 'w') as f:
                    f.write(fix_part_content_for_christian(content))
            part_file = spot_part

        if mode == "ltlf-fo":
            make_fully_observable(part_file)
        
        if args.num_useless_unobservables > 0:
            add_useless_unobservables(part_file, args.num_useless_unobservables)
            with open(input_file, 'r') as f:
                content = f.read().strip()
            with open(input_file, 'w') as f:
                f.write(content + '\n')
                for i in range(args.num_useless_unobservables):
                    f.write(f"G (u_useless_{i} | ~u_useless_{i})\n")

        transformation = f"sed 's/X/X[!]/g;s/N/X/g;s/^/(/;s/$/)/' {input_file} | paste -sd'&'"
        
        if mode == "ltlfilt":
            with open(part_file, 'r') as f:
                content = f.read()
            # add alive to outputs to account for the new variable introduced by ltlfilt --from-ltlf
            # fix: replace '.outputs:' instead of '.output' to avoid mangling the keyword
            if '.outputs:' in content:
                content = content.replace('.outputs:', '.outputs: alive ')
            elif '.output:' in content:
                content = content.replace('.output:', '.output: alive ')
            else:
                content += "\n.outputs: alive\n"
            
            with open(part_file, 'w') as f:
                f.write(content)
        
        verify_flag = " --verify" if verify else ""
        if mode == "ltlf" or mode == "ltlf-fo":
            return  f"{transformation} | ltlfsynt --part-file={part_file} --semantics={semantics} --verbose -H"
        elif mode == "ltl":
            return f"{transformation} | ltlsynt --part-file={part_file} --verbose --algo=ds -H{verify_flag}"
        elif mode == "ltlfilt":
            return f"{transformation} | ltlfilt --part-file={part_file} --from-ltlf --relabel=io | ltlsynt --verbose --algo=ds -H{verify_flag}"

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


def get_expected_result(test_path):
    parts = list(test_path.parts)
    if "ltlf" not in parts:
        return None
    
    try:
        idx = parts.index("ltlf")
        expected_parts = list(parts)
        expected_parts[idx] = "expected"
        expected_file = Path(*expected_parts).with_suffix(".txt")
        
        if expected_file.exists():
            with open(expected_file, 'r') as f:
                content = f.read().strip().lower()
                if "unrealizable" in content:
                    return 0
                if "realizable" in content:
                    return 1
    except Exception:
        pass
    return None


class Statistics():
    def __init__(self):
        self.stats = {'passed': 0, 'failed': 0, 'timeout': 0, 'other': 0, 'na': 0, 'error': 0, 'inconsistent': 0, 'verified': 0, 'verification_failed': 0}
        self.results = {} # test_path -> (time, status, verified, time_source)
        self.lock = threading.Lock()


    def add_result(self, test_path, time, status, outcome, verified=None, time_source="tool"):
        with self.lock:
            self.results[test_path] = (time, status, verified, time_source)
            if outcome == 'passed': self.stats['passed'] += 1
            elif outcome == 'failed': self.stats['failed'] += 1
            elif outcome == 'timeout': self.stats['timeout'] += 1
            elif outcome == 'other': self.stats['other'] += 1
            elif outcome == 'na': self.stats['na'] += 1
            elif outcome == 'error': self.stats['error'] += 1
            elif outcome == 'inconsistent': self.stats['inconsistent'] += 1
            
            if verified is True:
                self.stats['verified'] += 1
            elif verified is False:
                self.stats['verification_failed'] += 1

# for statistics 
statistics = Statistics()


def collectTest(testDir, partDir="part"):
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

    for file in test_files:
        test_path = file.resolve()
        
        # Try to find part file by replacing "ltlf" with "part" in the path
        parts = list(test_path.parts)
        if "ltlf" in parts:
            idx = parts.index("ltlf")
            part_parts = list(parts)
            part_parts[idx] = partDir
            part_file = Path(*part_parts).with_suffix(".part")
            
            if not part_file.exists():
                statistics.add_result(test_path, 0, 0, "other")
                print(f"Missing part file for {test_path} (expected at {part_file})")
                continue
            
            tests.append(test_path)
        else:
            print(f"Test file {test_path} not under an 'ltlf' directory, skipping.")

    return tests


TIMEOUT_CODE = -2
ERROR_CODE = -1

def executeTest(test, timeout, solver: Solver, partDir="part", mode="direct", iter_count=1, semantics="moore", results_dir=None, verify=False, test_dir_origin=None):
    temp_dir = tempfile.mkdtemp()
    try:
        test_path = Path(test).resolve()
        
        # Determine relative path for result saving
        rel_path = test_path.name
        if results_dir and test_dir_origin:
            try:
                rel_path = test_path.relative_to(Path(test_dir_origin).resolve())
            except ValueError:
                pass
        
        # FO tests are always run to collect timing data, but we label them 'na' 
        # if the benchmark was unrealizable in PO (since realizability changes).
        test_name = test_path.name
        test_stem = test_path.stem
        
        # Strategy: find the index of "ltlf" in the parts of the path
        # and replace it with "part" or "mso" to find related files
        parts = list(test_path.parts)
        if "ltlf" not in parts:
            # Try to handle cases where it's not under 'ltlf' but maybe it's a file
            ltlf_idx = -1
        else:
            ltlf_idx = parts.index("ltlf")
        
        # Construct part file path
        if ltlf_idx != -1:
            part_parts = list(parts)
            part_parts[ltlf_idx] = partDir
            original_part = Path(*part_parts).with_suffix(".part")
        else:
            # Fallback: look for .part next to the file
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
        if original_part.exists():
            shutil.copy2(original_part, partfile)
        else:
            print(f"Warning: Part file {original_part} not found.")
        
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
            suffixes = [".mona", ".mona.rev.neg", ".mona.quant", ".dfa", ".dfa.rev.neg", ".dfa.quant"]
            for sfx in suffixes:
                src = mso_dir / (test_stem + sfx)
                if src.exists():
                    dst = os.path.join(temp_dir, test_stem + sfx)
                    shutil.copy2(src, dst)

        command = solver.get_command(inputfile, partfile, mode, semantics, verify=verify)
        if not command:
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
                    statistics.add_result(test, t_val, 0, outcome, time_source=t_source or "wall")
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
                times.append(timeout)
                continue

            except subprocess.CalledProcessError as e:
                print(f"Failed to run {test}: {e}, {e.output}")
                results.append(ERROR_CODE)
                times.append(0)
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
                header += f"# Semantics: {semantics}\n"
                header += f"# Reported Runtime: {average_time:.2f} ms ({final_time_source})\n"
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
        expected = get_expected_result(test_path)

        if TIMEOUT_CODE in results:
            if mode == "ltlf-fo" and expected == 0:
                outcome = "na"
            else:
                outcome = "failed" if expected is not None else "timeout"
            statistics.add_result(test, average_time, TIMEOUT_CODE, outcome, verified=verify_status, time_source=final_time_source)
        elif ERROR_CODE in results:
            if mode == "ltlf-fo" and expected == 0:
                outcome = "na"
            else:
                outcome = "failed" if expected is not None else "error"
            statistics.add_result(test, average_time, ERROR_CODE, outcome, verified=verify_status, time_source=final_time_source)
        elif not all(elem == results[0] for elem in (results if results else [None])):
            outcome = "failed" if expected is not None else "inconsistent"
            statistics.add_result(test, average_time, -1, outcome, verified=verify_status, time_source=final_time_source)
        else:
            status = results[0] if results else -1
            if expected is not None:
                if mode == "ltlf-fo" and expected == 0:
                    outcome = "na" # Don't count as pass/fail for FO compared to unrealizable PO
                else:
                    outcome = "passed" if status == expected else "failed"
            else:
                outcome = "other"
            statistics.add_result(test, average_time, status, outcome, verified=verify_status, time_source=final_time_source)
    finally:
        shutil.rmtree(temp_dir)
        


if __name__ == "__main__":
    MODES = [
        "christian:direct", "christian:belief", "christian:mso",
        "lucas:belief-states", "lucas:projection-based", "lucas:mso",
        "spot:ltlf", "spot:ltl", "spot:ltlfilt", "spot:ltlf-fo"
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
    parser.add_argument("--num-useless-unobservables", type=int, default=0, help="Number of useless unobservables")
    parser.add_argument("--part-dir", type=str, default="part", help="Part directory name (relative to ltlf directory)")
    parser.add_argument("--results-dir", type=str, help="Directory to save detailed results (logs, controllers)")
    parser.add_argument("--verify", action="store_true", help="Perform verification on the resulting controller")
    args = parser.parse_args()

    commit_hash = get_git_revision_hash()

    print("Starting Run with Parameters:")
    print(f"  Mode: {args.mode}")
    print(f"  Test Dir: {args.test_dir}")
    print(f"  Part Dir: {args.part_dir}")
    print(f"  Semantics: {args.semantics}")
    print(f"  Useless Unobservables: {args.num_useless_unobservables}")
    print(f"  Shard: {args.shard_id}/{args.num_shards}")
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
    
    tests = sorted(collectTest(test_dir, args.part_dir))
    
    if args.num_shards > 1:
        total_tests = len(tests)
        tests = tests[args.shard_id::args.num_shards]
        print(f"Shard {args.shard_id}/{args.num_shards}: Running {len(tests)} out of {total_tests} tests.")
    else:
        print(f"Running all {len(tests)} tests.")

    for test in tests:
        executeTest(test, timeout, solver, args.part_dir, internal_mode, iterations, args.semantics, 
                    results_dir=args.results_dir, verify=args.verify, test_dir_origin=test_dir)

    print("===========")
    print("Statistics:")
    print("===========")
    print(f"Passed: {statistics.stats['passed']}")
    print(f"Failed: {statistics.stats['failed']}")
    print(f"Timeout: {statistics.stats['timeout']}")
    print(f"Other: {statistics.stats['other']}")
    print(f"N/A: {statistics.stats['na']}")
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
    with open(output_file, "w") as csvfile:
        csvfile.write(f"# Commit: {commit_hash}\n")
        csvfile.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        csvfile.write(f"# Machine: {platform.node()}\n")
        csvfile.write(f"# Mode: {args.mode}\n")
        csvfile.write(f"# Test Dir: {args.test_dir}\n")
        csvfile.write(f"# Part Dir: {args.part_dir}\n")
        csvfile.write(f"# Semantics: {args.semantics}\n")
        csvfile.write(f"# Useless Unobservables: {args.num_useless_unobservables}\n")
        csvfile.write(f"# OS: {sys_info['os']}\n")
        csvfile.write(f"# CPU: {sys_info['cpu']}\n")
        csvfile.write(f"# Cores: {sys_info['cores']}\n")
        csvfile.write(f"# RAM: {sys_info['mem']}\n")
        writer = csv.writer(csvfile)
        writer.writerow(["test", "time", "status", "verified", "time_source"])
        for test, (time, status, verified, time_source) in statistics.results.items():
            writer.writerow([test, time, status, verified, time_source])



    