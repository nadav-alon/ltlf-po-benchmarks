from pathlib import Path
import subprocess
import os
import re
import shutil
import sys
import csv 
import time 
import tempfile
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class Statistics():
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.timeout = 0
        self.other = 0
        self.rows = []
# for statistics 
statistics = Statistics()
statLock = threading.Lock()

def replace_line_in_file(filename, line_number, new_line):
    """
        Replaces a line in a file.
    """
    with open(filename, 'r') as file:
        lines = file.readlines()

    if line_number < 1 or line_number > len(lines):
        raise IndexError("Line number out of range")
    lines[line_number - 1] = new_line + '\n'
    with open(filename, 'w') as file:
        file.writelines(lines)


def collectTests(testdir):
    global statistics
    p = Path(testdir)
    tests = []
    for file in p.rglob("*/*.ltlf"):
        # Check for corresponding .part 
        corresponding_partfile = file.with_suffix(".part")
        corresponding_output = file.with_name("expected.txt")
        if (not corresponding_partfile.is_file()) or (not corresponding_output.is_file()):
            print('One of the tests is missing the correct files')
            if not corresponding_partfile.is_file():
                print('Expected to find ' + str(corresponding_partfile))
            if not corresponding_output.is_file():
                print('Expected to find ' + str(corresponding_output))
            sys.exit(-1)
        # Read the expected file and save this information about the test
        expected_res = None
        with open(corresponding_output, "r") as f:
            try:
                expected_res = int(f.read())
            except Exception:
                print("Expected to find 0 / 1 in {str(corresponding_output)}")
                sys.exit(-1)
        tests.append((file, corresponding_partfile, expected_res))

    return tests

def executeTest(test, mode, timeout, syftpath, disregard, iter):
    SyftPath = Path(syftpath)
    # Create a unique temporary directory
    temp_dir = tempfile.mkdtemp()
    
    # Get the original filenames
    file1_name = os.path.basename(test[0])
    file2_name = os.path.basename(test[1])

    # Create unique filenames resembling the original names
    inputfile = os.path.join(temp_dir, file1_name)
    partfile = os.path.join(temp_dir, file2_name)

    # Copy files to the unique temporary directory
    shutil.copy2(test[0], inputfile)
    shutil.copy2(test[1], partfile)

    # Depending on the disregard argument, replace either first or second line in file with tt
    if disregard:
        if disregard == "main":
            replace_line_in_file(inputfile, 1, "true")
        elif disregard == "backup":
            replace_line_in_file(inputfile, 2, "true") 
    print(inputfile)
    results = []
    times   = []
    for i in range(iter):
        syft_command = f"./Syft {inputfile} {partfile} 0 {mode}" 
        try:
            print(syft_command)
            l = subprocess.check_output(
                        syft_command,
                        timeout=timeout,
                        cwd=SyftPath.parent,
                        shell=True
                    )
            # Try to find the time in output 
            # https://stackoverflow.com/questions/4289331/how-to-extract-numbers-from-a-string-in-python : Regex 
            lines = str(l).split("\\n")
            print(lines)
            rr = re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?",lines[-2])
            assert(len(rr) == 1)
            time_ms_syft = float(rr[0])
            # Get the result to analyse it
            result = None 
            if "Unrealizable" in str(l):
                result = 0
            if "Realizable" in str(l):
                result = 1
            results.append(result)
            times.append(time_ms_syft)
        except subprocess.TimeoutExpired:
            with statLock:
                statistics.timeout += 1
                statistics.rows.append([str(test[0]), -1, "timeout"])
                return
        except subprocess.CalledProcessError as e:
            with statLock:
                statistics.other += 1
                statistics.rows.append([str(test[0]), -1, "error"])
                return

        # Check that all results are identical 
    if not all(elem == results[0] for elem in results):
        statistics.rows.append([str(test[0]), -1, "rnid"])
        return 
    if not disregard and results[0] != test[2]: # If we disregard smth, realizability possibilities change!
        with statLock:
            statistics.failed += 1
            # Compute average of times
            average_time = sum(times) / len(times)
            statistics.rows.append([str(test[0]), average_time /1000, "WA"])
    else:
        with statLock:
            statistics.passed += 1
            average_time = sum(times) / len(times)
            statistics.rows.append([str(test[0]), time_ms_syft/1000, ""])
                



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('impl',
                        choices=['direct', 'belief', 'mso'],
                        help='Select which implementation to run the tests with')
    parser.add_argument('-disregard', default=None, choices=[None, "backup", "main"])
    parser.add_argument('-o',
                        help="Specify the result file",
                        default=None)
    parser.add_argument('-tdir',
                        help="Specify the directory where tests are stord",
                        default="../../tests/")
    parser.add_argument('-syft',
                        help="Specify the path to Syft executable",
                        default="../../Syft/build/bin/Syft")
    #parser.add_argument('-test', help="Specify which test to run", default=None)
    parser.add_argument('-j', type=int,
                        help="Number of threads to use (t >= 1 --> mutithreading)",
                        default=None)
    parser.add_argument('-timeout',
                        help="The timeout to use",
                        default=1500)
    parser.add_argument('-iter',
                        help="How often to run each test for better comparability",
                        default=1, type=int)

    args = parser.parse_args()
    print("Collecting tests")
    tests = collectTests(args.tdir)

    # Create csvwriter + lock for output file + write initial row
    threads = []

    max_workers = args.j if args.j else None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(executeTest, test, args.impl, args.timeout, args.syft, args.disregard, args.iter) for test in tests]

        for future in as_completed(futures):
            future.result()  # Wait for all futures to complete


    for t in threads:
        t.join()
    # Timeout (1) / Unexpected Output (2) / Failure (3), 
    print("================================")
    print("========= STATISTICS ===========")
    print(f"SUCCESS: {statistics.passed}")
    print(f"FAILED: {statistics.failed}")
    print(f"TIMEOUT: {statistics.timeout}")
    print(f"ERROR: {statistics.other}")
    if not args.o:
        args.o = f"results-{args.impl}.csv"
    with open(args.o, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(statistics.rows)

    