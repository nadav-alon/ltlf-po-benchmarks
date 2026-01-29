import os
import unittest
import shutil
import tempfile
import subprocess
from pathlib import Path

# Add project root to path so we can import runTests
import sys
project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import runTests

# Constants
REPO_ROOT = Path(project_root)
LUCAS_SYFT_PATH = REPO_ROOT.parent / "lucas" / "Syft" / "build" / "bin" / "Syft"

class TestSolversIsolated(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def get_expected(self, name):
        expected_file = REPO_ROOT / "lucas" / "expected" / f"{name}.txt"
        with open(expected_file, "r") as f:
            content = f.read().strip().lower()
            if content == "realizable":
                return 1
            elif content == "unrealizable":
                return 0
            return None

    def run_solver_logic(self, solver, example_name, ltlf_rel_path, mode, semantics="moore"):
        """
        Isolated test logic for a solver.
        Mimics execution steps in runTests.executeTest but runs in isolation.
        """
        expected_val = self.get_expected(example_name)
        self.assertIsNotNone(expected_val)
        
        ltlf_src = REPO_ROOT / ltlf_rel_path
        test_stem = ltlf_src.stem
        
        # Determine part file source
        parts = list(ltlf_src.parts)
        if "ltlf" in parts:
            idx = parts.index("ltlf")
            part_parts = list(parts)
            part_parts[idx] = "part"
            original_part = Path(*part_parts).with_suffix(".part")
        else:
            original_part = ltlf_src.with_suffix(".part")

        # Copy files to temp dir
        inputfile = os.path.join(self.test_dir, ltlf_src.name)
        partfile = os.path.join(self.test_dir, test_stem + ".part")
        shutil.copy2(ltlf_src, inputfile)
        if original_part.exists():
            shutil.copy2(original_part, partfile)

        # 1. Preprocess
        auto_time = solver.preprocess(inputfile, partfile, mode, semantics=semantics)
        print(f"\nDEBUG: Preprocessed {example_name} in {mode} ({partfile})")
        with open(partfile, 'r') as f:
            print(f"DEBUG: Part File ({partfile}):\n{f.read()}")
        
        with open(inputfile, 'r') as f:
            print(f"DEBUG: Input File ({inputfile}):\n{f.read()}")
        
        # 2. Get command
        cmd = solver.get_command(inputfile, partfile, mode, semantics=semantics)
        print(f"DEBUG: Command for {example_name} in {mode}:\n{cmd}")
        self.assertTrue(cmd, f"Failed to get command for {example_name} in {mode}")
        
        # 3. Execute
        try:
            # We use shell=True because some solvers return complex command strings (pipes, redirects)
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=60, cwd=REPO_ROOT)
        except subprocess.CalledProcessError as e:
            output = e.output
        
        # 4. Parse output
        result, t_ms, t_src = solver.parse_output(output)
        
        self.assertEqual(result, expected_val, f"Solver {solver.get_name()} for {example_name} ({mode}) returned {result}, expected {expected_val}. Output: {output.decode()}")

    # --- Individual Test Methods ---
    def test_lucas_bs_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "belief-states")

    def test_lucas_bs_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "belief-states")
    
    def test_lucas_bs_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "belief-states")

    def test_lucas_bs_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "belief-states")

    def test_lucas_bs_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "belief-states")

    def test_lucas_mso_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "mso")

    def test_lucas_mso_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "mso")

    def test_lucas_mso_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "mso")

    def test_lucas_mso_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "mso")

    def test_lucas_mso_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "mso")

    def test_spot_ltlf_coins_3(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "ltlf")

    def test_spot_ltlf_coins_4(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "ltlf")

    def test_spot_ltlf_seek_5(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "ltlf")

    def test_spot_ltlf_peek_1_1_1(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "ltlf")

    def test_spot_ltlf_peek_1_1_89(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "ltlf")

    def test_spot_ltlf_peek_4_3_68(self):
        solver = runTests.SpotSolver("ltlfsynt", name="spot")
        self.run_solver_logic(solver, "peek_4_3_68", "lucas/ltlf/peek/peek_4_3_68.ltlf", "ltlf")

    # def test_spot_ltlfilt_simple(self):
    #     solver = runTests.SpotSolver("ltlfsynt", name="spot")
    #     self.run_solver_logic(solver, "simple", "simple.ltlf", "ltlfilt")

    # def test_spot_ltlfilt_coins_3(self):
    #     solver = runTests.SpotSolver("ltlfsynt", name="spot")
    #     self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "ltlfilt")
    
    # def test_spot_ltlfilt_coins_4(self):
    #     solver = runTests.SpotSolver("ltlfsynt", name="spot")
    #     self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "ltlfilt")

    # def test_spot_ltlfilt_seek_5(self):
    #     solver = runTests.SpotSolver("ltlfsynt", name="spot")
    #     self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "ltlfilt")

    def test_lucas_proj_peek_1_1_1(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_1", "lucas/ltlf/peek/peek_1_1_1.ltlf", "projection")

    def test_lucas_proj_peek_1_1_89(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "peek_1_1_89", "lucas/ltlf/peek/peek_1_1_89.ltlf", "projection")
    
    def test_lucas_proj_coins_3(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_3", "lucas/ltlf/coins_3.ltlf", "projection")

    def test_lucas_proj_coins_4(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "coins_4", "lucas/ltlf/coins_4.ltlf", "projection")

    def test_lucas_proj_seek_5(self):
        solver = runTests.LucasSyftSolver(str(LUCAS_SYFT_PATH), name="lucas")
        self.run_solver_logic(solver, "seek_5", "lucas/ltlf/seek_5.ltlf", "belief-states")

if __name__ == "__main__":
    unittest.main()
