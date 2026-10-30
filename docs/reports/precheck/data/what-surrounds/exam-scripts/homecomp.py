"""Is the single named /home/<x> component of the MCPTox source quotes also in PAPER.md (App. A quote)? Booleans/counts only."""
import sys, re, collections, hashlib
sys.path.insert(0, sys.argv[1]); from rawzip import members, js
mem = members(); comps = collections.Counter()
for lab, b in mem.items():
    if lab.endswith('meta.json') or lab == 'attacks.json':
        for m in re.finditer(rb'/home/([^/\s"\'\\]+)', b): comps[m.group(1)] += 1
paper = mem.get('PAPER.md') or next((b for l, b in mem.items() if l.endswith('PAPER.md')), b'')
print({'distinct_components': len(comps), 'hits': sum(comps.values()), 'component_digests': [hashlib.sha256(c).hexdigest()[:8] for c in comps],
       'in_paper_md': {hashlib.sha256(c).hexdigest()[:8]: c in paper for c in comps}, 'paper_md_read': bool(paper), 'len': [len(c) for c in comps]})
