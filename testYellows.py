from runTests import normalize_part_with_dots
from os import mkdir
from runTests import load_samples
import os
import subprocess

def main():
    test_list = ["1-2:chomp.ltlf", "1-2:chomp_pb_2_2_pe_.ltlf", "1-2:chomp_pb_2_3_pe_.ltlf", "1-2:chomp_pb_3_2_pe_.ltlf", "1-2:countersDouble_pb_01_pe_.ltlf", "1-2:countersDouble_pb_02_pe_.ltlf", "1-4:chomp.ltlf", "1-4:chomp_pb_2_2_pe_.ltlf", "1-4:chomp_pb_2_3_pe_.ltlf", "1-4:chomp_pb_2_4_pe_.ltlf", "1-4:chomp_pb_2_5_pe_.ltlf", "1-4:chomp_pb_2_6_pe_.ltlf", "1-4:chomp_pb_3_2_pe_.ltlf", "1-4:chomp_pb_3_3_pe_.ltlf", "1-4:chomp_pb_3_4_pe_.ltlf", "1-4:chomp_pb_4_2_pe_.ltlf", "1-4:chomp_pb_4_3_pe_.ltlf", "1-4:countersDouble_pb_01_pe_.ltlf", "1-4:countersDouble_pb_02_pe_.ltlf", "1-4:countersDouble_pb_03_pe_.ltlf", "1-4:countersDouble_pb_04_pe_.ltlf", "1-4:countersDouble_pb_05_pe_.ltlf", "1-4:countersDouble_pb_06_pe_.ltlf", "1-4:nim_pb_03_07_pe_.ltlf", "1-4:nim_pb_03_12_pe_.ltlf", "1-4:nim_pb_05_04_pe_.ltlf", "3-4:countersDouble_pb_01_pe_.ltlf"]

    list_tuples = [tuple(d.split(":")) for d in test_list]
    SAMPLES = load_samples("ltlf-fin-benchmarks")

    if not os.path.exists("yellow_results"):
        mkdir("yellow_results")

    for [level, test] in list_tuples:
        test_path = os.path.join("ltlf-fin-benchmarks", "ltlf", test)
        original_part_path = os.path.join("ltlf-fin-benchmarks", "part", test.split(".")[0] + ".part")
        
        # Normalize the part file format for ltlfsynt
        if os.path.exists(original_part_path):
            with open(original_part_path, "r") as f:
                content = f.read()
            normalized = normalize_part_with_dots(content)
            temp_part = f"yellow_results/{test.split('.')[0]}.spot.part"
            with open(temp_part, "w") as f:
                f.write(normalized)
            part_path = temp_part
        else:
            part_path = "" # Fallback

        for i in range(1, 11):
            sample_key = f"{level}_{i}_{test.split('.')[0]}"
            if sample_key not in SAMPLES:
                continue
            
            unobservable_ins = ",".join(SAMPLES[sample_key])
            command = f"cat {test_path} | paste -sd'&' | ltlfsynt --part-file={part_path} --semantics=mealy --verbose --unobservable-ins='{unobservable_ins}'"

            print(f"Running: {sample_key}")
            try:
                output = subprocess.check_output(command, timeout=180, shell=True, cwd="/home/cowclaw/ltlf-po-benchmarks", stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                # Capture output even on failure (like unrealizable or syntax error)
                output = e.output
            except subprocess.TimeoutExpired as e:
                output = b"TIMEOUT\n" + (e.output or b"")

            if not os.path.exists(f"yellow_results/{level}"):
                mkdir(f"yellow_results/{level}")
            with open(f"yellow_results/{level}/{test.split('.')[0]}_{i}.txt", "w") as f:
                f.write(output.decode("utf-8", errors="ignore"))

if __name__ == '__main__':
    main()