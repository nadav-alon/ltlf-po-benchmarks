import os
import unittest
import shutil
import tempfile
import json
from pathlib import Path
import sys

# Add project root to path so we can import runTests
project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import runTests

class TestCollectTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ltlf_dir = Path(self.test_dir) / "ltlf"
        self.ltlf_dir.mkdir()
        self.part_base_dir = Path(self.test_dir) / "part"
        self.part_base_dir.mkdir()
        
        # Reset SAMPLES_DATA cache in runTests
        runTests.SAMPLES_DATA = None

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        runTests.SAMPLES_DATA = None

    def create_test_file(self, name):
        path = self.ltlf_dir / f"{name}.ltlf"
        path.write_text("formula dummy;")
        return path

    def create_part_file(self, name, part_dir_name="part"):
        target_dir = Path(self.test_dir) / part_dir_name
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{name}.part"
        path.write_text(".inputs a\n.outputs b\n")
        return path

    def write_samples_json(self, data):
        samples_json = Path(self.test_dir) / "samples.json"
        with open(samples_json, 'w') as f:
            json.dump(data, f)

    def test_collect_simple_fo(self):
        # Create a test file and its part file in the standard 'part' dir
        self.create_test_file("test1")
        self.create_part_file("test1")
        
        # Test collection for FO (partDir="part")
        tests = runTests.collectTest(self.test_dir, "part")
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].name, "test1.ltlf")

    def test_collect_missing_part_skips_fo(self):
        # Create a test file but NO part file
        self.create_test_file("test1")
        
        tests = runTests.collectTest(self.test_dir, "part")
        self.assertEqual(len(tests), 0)

    def test_collect_po_on_the_fly(self):
        # Create base test and part file
        self.create_test_file("test1")
        self.create_part_file("test1") # Base part exists in 'part' dir
        
        # Define samples.json
        expected_unobs = ["v1", "v2"]
        self.write_samples_json({
            "1-2_1_test1": expected_unobs
        })
        
        # Test collection for po-part-1-2_1
        tests = runTests.collectTest(self.test_dir, "po-part-1-2_1")
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].name, "test1.ltlf")
        
        # Assert variables from samples.json match
        samples = runTests.load_samples(self.test_dir)
        self.assertEqual(samples.get("1-2_1_test1"), expected_unobs)
        
        # Test collection for po-part-1-2_2 (not in samples)
        tests = runTests.collectTest(self.test_dir, "po-part-1-2_2")
        self.assertEqual(len(tests), 0)

    def test_collect_po_on_the_fly_explicit_sample_id(self):
        # Create base test and part file
        self.create_test_file("test2")
        self.create_part_file("test2")
        
        expected_unobs = ["v1"]
        self.write_samples_json({
            "1-2_5_test2": expected_unobs
        })
        
        # Use level 1-2 and explicit sample_id 5
        tests = runTests.collectTest(self.test_dir, "po-part-1-2", sample_id=5)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].name, "test2.ltlf")
        
        samples = runTests.load_samples(self.test_dir)
        self.assertEqual(samples.get("1-2_5_test2"), expected_unobs)

    def test_collect_fu_on_the_fly(self):
        self.create_test_file("test3")
        self.create_part_file("test3")
        
        expected_unobs = ["v1", "v2", "v3"]
        self.write_samples_json({
            "all_1_test3": expected_unobs
        })
        
        # Test collection for po-part-all
        tests = runTests.collectTest(self.test_dir, "po-part-all")
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].name, "test3.ltlf")
        
        samples = runTests.load_samples(self.test_dir)
        self.assertEqual(samples.get("all_1_test3"), expected_unobs)

    def test_redundant_task_skipping_existing_files(self):
        # Case where part file exists physically
        self.create_test_file("test4")
        self.create_part_file("test4", "po-part-all")
        
        # LEVEL=all, sample_id=1 should run
        tests = runTests.collectTest(self.test_dir, "po-part-all", sample_id=1)
        self.assertEqual(len(tests), 1)

        # LEVEL=all, sample_id=2 should skip because FU (singleton) only runs once
        tests = runTests.collectTest(self.test_dir, "po-part-all", sample_id=2)
        self.assertEqual(len(tests), 0)

    def test_po_filtering_in_samples_json(self):
        self.create_test_file("test5")
        self.create_part_file("test5")
        
        # test5 only exists for sample 2 and 4 of level 1-4
        self.write_samples_json({
            "1-4_2_test5": ["a"],
            "1-4_4_test5": ["b"]
        })

        tests = runTests.collectTest(self.test_dir, "po-part-1-4_1")
        self.assertEqual(len(tests), 0)

        tests = runTests.collectTest(self.test_dir, "po-part-1-4_2")
        self.assertEqual(len(tests), 1)

        tests = runTests.collectTest(self.test_dir, "po-part-1-4_4")
        self.assertEqual(len(tests), 1)

if __name__ == "__main__":
    unittest.main()
