import rawload, re, collections
rx = re.compile(r"\\([nrt])([A-Za-z]*)")
d = rawload.load_all(); c = collections.Counter()
for p, x in d.items():
    for m in x["messages"]:
        for part in (m.get("content") or []):
            t = part.get("content") if isinstance(part, dict) else None
            if isinstance(t, str):
                for mm in rx.finditer(t): c["\\" + mm.group(1) + mm.group(2)] += 1
print(dict(c))
