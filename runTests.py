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

    def get_command(self, input_file, part_file, mode, semantics="moore")-> str:
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

    def parse_output(self, output_bytes)-> (int, float):
        """Returns (result_code, time_ms) from tool output. result: 1=Realizable, 0=Unrealizable"""
        raise NotImplementedError

    def get_name(self)-> str:
        return self.name


def get_variables_from_part(part_file):
    vars = set()
    if os.path.exists(part_file):
        with open(part_file, 'r') as f:
            for line in f:
                line = line.strip().lower()
                if line.startswith('.') and ':' in line:
                    vars.update(line.split(':')[1].strip().split())
                elif any(line.startswith(k) for k in ['inputs', 'outputs', 'unobservables']):
                    parts = line.split()
                    if len(parts) > 0 and (parts[0].endswith(':') or len(parts) > 1):
                        start_idx = 1 if not parts[0].endswith(':') else 0
                        # This logic is a bit messy, let's simplify
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
    def get_command(self, input_file, part_file, mode, semantics)-> str:
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

    def parse_output(self, output_bytes)-> (int, float):
        l_str = str(output_bytes)
        lines = l_str.split("\\n")
        # Try to find the time in output 
        try:
            rr = re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", lines[-2])
            assert(len(rr) == 1)
            time_ms = float(rr[0])
        except Exception:
            # Fallback for if output structure differs
            time_ms = 0.0
        
        result = None 
        if "Unrealizable" in l_str:
            result = 0
        if "Realizable" in l_str:
            result = 1

        # if result == 1:
            # TODO: need to save the output of the tool

        return result, time_ms


class LucasSyftSolver(Solver):
    def get_command(self, input_file, part_file, mode, semantics)-> str:
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
        
        dfa_file = input_file + dfa_suffix
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
        l_str = str(output_bytes)
        result = None 
        if "unrealizable" in l_str: result = 0
        elif "realizable" in l_str: result = 1
        
        # Lucas Syft often prints time in ms at the end
        lines = l_str.strip().split("\\n")
        time_ms = 0.0
        for line in reversed(lines):
            rr = re.findall(r"(\d+\.?\d*)\s*ms", line)
            if rr:
                time_ms = float(rr[0])
                break

        # TODO: need to save the output of the tool
        return result, time_ms

class SpotSolver(Solver):
    def get_command(self, input_file, part_file, mode, semantics)-> str:
        if not part_file.endswith('.spot.part'):
            spot_part = part_file + '.spot.part'
            if not os.path.exists(spot_part):
                with open(part_file, 'r') as f:
                    content = f.read()
                with open(spot_part, 'w') as f:
                    f.write(fix_part_content_for_christian(content))
            part_file = spot_part

        transformation = f"sed 's/X/X[!]/g;s/N/X/g;s/^/(/;s/$/)/' {input_file} | paste -sd'&'"
        if mode == "ltlf":
            return  f"{transformation} | ltlfsynt --part-file={part_file} --semantics={semantics} --real --verbose"
        elif mode == "ltl":
            return f"{transformation} | ltlsynt --part-file={part_file} --real --verbose --algo=ds"
        elif mode == "ltlfilt":
            with open(part_file, 'r') as f:
                content = f.read()
                # add alive to outputs to account for the new variable introduced by ltlfilt --from-ltlf
                content = content.replace('.output', '.output alive')
            with open(part_file, 'w') as f:
                f.write(content)
            return f"{transformation} | ltlfilt --part-file={part_file} --from-ltlf --relabel=io | ltlsynt --real --verbose --algo=ds"

    def parse_output(self, output_bytes):
        l_str = str(output_bytes)
        result = None 
        if "UNREALIZABLE" in l_str: result = 0
        elif "REALIZABLE" in l_str: result = 1
        
        # Spot often prints time in ms or seconds at the end
        lines = l_str.strip().split("\\n")
        time_ms = 0.0
        for line in reversed(lines):
            # Matches "123 ms"
            rr_ms = re.findall(r"(\d+\.?\d*)\s*ms", line)
            if rr_ms:
                time_ms = float(rr_ms[0])
                break
            # Matches "took 1.23 seconds"
            rr_sec = re.findall(r"took\s*(\d+\.?\d*)\s*seconds", line)
            if rr_sec:
                time_ms = float(rr_sec[0]) * 1000
                break

        return result, time_ms


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
        self.stats = {'passed': 0, 'failed': 0, 'timeout': 0, 'other': 0, 'error': 0, 'inconsistent': 0}
        self.results = {} # test_path -> (time, status)
        self.lock = threading.Lock()


    def add_result(self, test_path, time, status, outcome):
        with self.lock:
            self.results[test_path] = (time, status)
            if outcome == 'passed': self.stats['passed'] += 1
            elif outcome == 'failed': self.stats['failed'] += 1
            elif outcome == 'timeout': self.stats['timeout'] += 1
            elif outcome == 'other': self.stats['other'] += 1
            elif outcome == 'error': self.stats['error'] += 1
            elif outcome == 'inconsistent': self.stats['inconsistent'] += 1

# for statistics 
statistics = Statistics()


def collectTest(testDir):
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
            part_parts[idx] = "part"
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

def executeTest(test, timeout, solver: Solver, mode="direct", iter=1, semantics="moore"):
    temp_dir = tempfile.mkdtemp()
    try:
        test_path = Path(test).resolve()
        test_name = test_path.name
        test_stem = test_path.stem
        
        # Strategy: find the index of "ltlf" in the parts of the path
        # and replace it with "part" or "mso" to find related files
        parts = list(test_path.parts)
        if "ltlf" not in parts:
            print(f"Error: {test} is not under an 'ltlf' directory.")
            return

        ltlf_idx = parts.index("ltlf")
        
        # Construct part file path
        part_parts = list(parts)
        part_parts[ltlf_idx] = "part"
        original_part = Path(*part_parts).with_suffix(".part")

        # Construct mso directory path
        mso_parts = list(parts)
        mso_parts[ltlf_idx] = "mso"
        mso_dir = Path(*mso_parts).parent

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
        
        # Copy .mona files from mso directory if they exist
        if mso_dir.exists():
            for mona_suffix in [".mona", ".mona.rev.neg", ".mona.quant"]:
                mona_src = mso_dir / (test_stem + mona_suffix)
                if mona_src.exists():
                    mona_dst = os.path.join(temp_dir, test_stem + mona_suffix)
                    shutil.copy2(mona_src, mona_dst)

        command = solver.get_command(inputfile, partfile, mode, semantics)
        if not command:
            return

        times = []
        results = []

        for i in range(iter):
            try:
                try:
                    start_wall = time.time()
                    l = subprocess.check_output(command, timeout=timeout, shell=True, cwd=solver.path.parent, stderr=subprocess.STDOUT)
                    end_wall = time.time()
                except subprocess.CalledProcessError as e:
                    end_wall = time.time()
                    # Some tools might return non-zero exit codes even if they produced a valid result.
                    # We try to parse the output; if it contains a valid result, we treat it as success.
                    result, t_val = solver.parse_output(e.output)
                    if result is not None:
                        l = e.output
                    else:
                        raise e

                result, t_val = solver.parse_output(l)
                if result is None:
                    print(f"raw output: {l}")
                    expected = get_expected_result(test_path)
                    outcome = "failed" if expected is not None else "other"
                    statistics.add_result(test, t_val, 0, outcome)
                    print(f"Failed to parse output for {test}")
                    return
                
                # If tool didn't report time, use wall clock measurement
                if t_val == 0.0:
                    t_val = (end_wall - start_wall) * 1000

                results.append(result)
                times.append(t_val)

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
        expected = get_expected_result(test_path)

        if TIMEOUT_CODE in results:
            outcome = "failed" if expected is not None else "timeout"
            statistics.add_result(test, average_time, TIMEOUT_CODE, outcome)
        elif ERROR_CODE in results:
            outcome = "failed" if expected is not None else "error"
            statistics.add_result(test, average_time, ERROR_CODE, outcome)
        elif not all(elem == results[0] for elem in (results if results else [None])):
            outcome = "failed" if expected is not None else "inconsistent"
            statistics.add_result(test, average_time, -1, outcome)
        else:
            status = results[0] if results else -1
            if expected is not None:
                outcome = "passed" if status == expected else "failed"
            else:
                outcome = "other"
            statistics.add_result(test, average_time, status, outcome)
    finally:
        shutil.rmtree(temp_dir)
        


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
    args = parser.parse_args()

    commit_hash = get_git_revision_hash()

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
    
    tests = sorted(collectTest(test_dir))
    
    if args.num_shards > 1:
        total_tests = len(tests)
        tests = tests[args.shard_id::args.num_shards]
        print(f"Shard {args.shard_id}/{args.num_shards}: Running {len(tests)} out of {total_tests} tests.")
    else:
        print(f"Running all {len(tests)} tests.")

    for test in tests:
        executeTest(test, timeout, solver, internal_mode, iterations, args.semantics)

    print("===========")
    print("Statistics:")
    print("===========")
    print(f"Passed: {statistics.stats['passed']}")
    print(f"Failed: {statistics.stats['failed']}")
    print(f"Timeout: {statistics.stats['timeout']}")
    print(f"Other: {statistics.stats['other']}")
    print(f"Error: {statistics.stats['error']}")
    print(f"Inconsistent: {statistics.stats['inconsistent']}")

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
        csvfile.write(f"# OS: {sys_info['os']}\n")
        csvfile.write(f"# CPU: {sys_info['cpu']}\n")
        csvfile.write(f"# Cores: {sys_info['cores']}\n")
        csvfile.write(f"# RAM: {sys_info['mem']}\n")
        writer = csv.writer(csvfile)
        writer.writerow(["test", "time", "status"])
        for test, (time, status) in statistics.results.items():
            writer.writerow([test, time, status])



    