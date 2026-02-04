import os
import unittest
import shutil
import tempfile
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

# Add project root to path so we can import runTests
project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import runTests

class TestPrepareTestArtifacts(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.benchmark_root = Path(self.test_dir) / "benchmark"
        self.ltlf_dir = self.benchmark_root / "ltlf"
        self.part_dir = self.benchmark_root / "part"
        self.mso_dir = self.benchmark_root / "mso"
        
        for d in [self.ltlf_dir, self.part_dir, self.mso_dir]:
            d.mkdir(parents=True)
            
        self.temp_run_dir = Path(self.test_dir) / "run"
        self.temp_run_dir.mkdir()
        
        # Mock solver
        self.solver = MagicMock()
        self.solver.get_name.return_value = "mock_solver"
        
        # Reset SAMPLES_DATA cache
        runTests.SAMPLES_DATA = None

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        runTests.SAMPLES_DATA = None

    def create_ltlf(self, name, content="formula;"):
        path = self.ltlf_dir / f"{name}.ltlf"
        path.write_text(content)
        return path

    def create_part(self, name, content=".inputs i\n.outputs o\n", dir_path=None):
        if dir_path is None:
            dir_path = self.part_dir
        path = dir_path / f"{name}.part"
        path.write_text(content)
        return path

    def create_mona(self, name, content="m2l-str; var2 X; X;"):
        path = self.mso_dir / f"{name}.mona"
        path.write_text(content)
        return path

    def write_samples(self, data):
        samples_json = self.benchmark_root / "samples.json"
        with open(samples_json, 'w') as f:
            json.dump(data, f)

    def test_fo_artifact_copy(self):
        # Create test files
        self.create_ltlf("test1")
        self.create_part("test1", "semantics mealy\n.inputs a\n.outputs b\n")
        
        test_file = self.ltlf_dir / "test1.ltlf"
        
        inputfile, partfile, actual_semantics, gen_time = runTests.prepare_test_artifacts(
            test_file, "part", self.solver, "direct", 1, self.temp_run_dir, test_dir_origin=self.benchmark_root
        )
        
        self.assertTrue(os.path.exists(inputfile))
        self.assertTrue(os.path.exists(partfile))
        self.assertEqual(actual_semantics, "mealy")
        
        with open(partfile, 'r') as f:
            content = f.read()
            self.assertIn(".inputs a", content)

    def test_po_on_the_fly_generation(self):
        self.create_ltlf("test2")
        self.create_part("test2", ".inputs i1 i2\n.outputs o1\n") # Base part in 'part' dir
        
        self.write_samples({
            "1-2_1_test2": ["i1"]
        })
        
        test_file = self.ltlf_dir / "test2.ltlf"
        
        # Running with level 1-2
        inputfile, partfile, actual_semantics, gen_time = runTests.prepare_test_artifacts(
            test_file, "po-part-1-2", self.solver, "direct", 1, self.temp_run_dir, test_dir_origin=self.benchmark_root
        )
        
        self.assertTrue(os.path.exists(partfile))
        with open(partfile, 'r') as f:
            content = f.read()
            self.assertIn(".unobservables: i1", content)
            self.assertIn(".inputs i1 i2", content)
            self.assertIn(".outputs o1", content)

    def test_mona_quantification_on_the_fly(self):
        self.create_ltlf("test3")
        self.create_part("test3", ".inputs i1 i2\n.outputs o1\n")
        self.create_mona("test3", "m2l-str;\nvar2 I1, I2, O1;\nI1 & I2;")
        
        self.write_samples({
            "all_1_test3": ["i1", "i2"]
        })
        
        # Solver name needs 'lucas' for mona generation logic in prepare_test_artifacts
        self.solver.get_name.return_value = "lucas_solver"
        
        test_file = self.ltlf_dir / "test3.ltlf"
        
        inputfile, partfile, actual_semantics, gen_time = runTests.prepare_test_artifacts(
            test_file, "po-part-all", self.solver, "belief-states", 1, self.temp_run_dir, test_dir_origin=self.benchmark_root
        )
        
        mona_quant = Path(self.temp_run_dir) / "test3.mona.quant"
        self.assertTrue(mona_quant.exists())
        
        with open(mona_quant, 'r') as f:
            content = f.read()
            self.assertIn("all2 I1:", content)
            self.assertIn("all2 I2:", content)
            # Both I1 and I2 should be removed from var2 line and put into all2
            self.assertIn("var2 O1;", content)

    def test_dfa_variants_copying(self):
        ltlf_path = self.create_ltlf("test4")
        # Create a .dfa file next to ltlf
        dfa_path = ltlf_path.with_suffix(".ltlf.dfa")
        dfa_path.write_text("DFA content")
        
        self.create_part("test4")
        
        inputfile, partfile, actual_semantics, gen_time = runTests.prepare_test_artifacts(
            ltlf_path, "part", self.solver, "direct", 1, self.temp_run_dir, test_dir_origin=self.benchmark_root
        )
        
        self.assertTrue(os.path.exists(inputfile + ".dfa"))
        self.assertEqual(Path(inputfile + ".dfa").read_text(), "DFA content")

    def test_semantics_precedence(self):
        # Part file say mealy, default is moore
        self.create_ltlf("test5")
        self.create_part("test5", "semantics mealy\n")
        
        test_file = self.ltlf_dir / "test5.ltlf"
        
        _, _, actual_semantics, _ = runTests.prepare_test_artifacts(
            test_file, "part", self.solver, "direct", 1, self.temp_run_dir, test_dir_origin=self.benchmark_root, semantics="moore"
        )
        
        self.assertEqual(actual_semantics, "mealy")

if __name__ == "__main__":
    unittest.main()
