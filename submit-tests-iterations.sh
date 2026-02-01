# Run the 30 samples for PO (1-2) using consolidated submission
./submit_samples.sh lucas:mso lucas:belief-states spot:ltlf --on-the-fly=true --test-dir="ltlf-fin-benchmarks"
./submit_samples.sh lucas:mso lucas:belief-states spot:ltlf --on-the-fly=false --test-dir="ltlf-fin-benchmarks"
