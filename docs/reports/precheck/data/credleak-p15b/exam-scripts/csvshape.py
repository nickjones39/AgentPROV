"""Shape of the root csv members: row lengths, section values, model labels, techniques (labels only, no content)."""
import sys, csv, io, collections
sys.path.insert(0, sys.argv[1]); from rawlib import members
for label, data in members(lambda l: l.startswith("p15b-run-data/") and l.endswith(".csv") and l.count("/") == 1):
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    print(label, "lens", collections.Counter(len(r) for r in rows))
    print(" sections", collections.Counter(r[0] for r in rows[1:]).most_common(8))
    print(" models", sorted(collections.Counter(r[1] for r in rows[1:] if len(r) > 4 and r[0]).items()))
    print(" techniques", sorted(collections.Counter(r[2] for r in rows[1:] if len(r) > 4 and r[0]).items()))
    keys = collections.Counter(tuple(r[:4]) for r in rows[1:] if r[0])
    print(" dup keys", sum(1 for k, v in keys.items() if v > 1), "N sum", sum(int(r[4]) for r in rows[1:] if r[0] and r[4].isdigit()))
    blank = [r for r in rows[1:] if not r[0]]
    print(" blank-section rows", len(blank), collections.Counter(r[1] for r in blank).most_common(5))
