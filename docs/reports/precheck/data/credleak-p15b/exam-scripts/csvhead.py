"""Header and row count of the deposit's root csv members (column names only)."""
import sys, csv, io
sys.path.insert(0, sys.argv[1]); from rawlib import members
for label, data in members(lambda l: l.startswith("p15b-run-data/") and l.endswith(".csv") and l.count("/") == 1):
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    print(label, len(rows) - 1, rows[0]); print("  first-row-shape", [c[:24] for c in rows[1]])
