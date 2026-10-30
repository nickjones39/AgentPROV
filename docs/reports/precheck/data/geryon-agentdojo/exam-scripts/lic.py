import sys
sys.path.insert(0, sys.argv[1])
import gx_lib
E = gx_lib.entries(); R = gx_lib.Reader()
b = R.r.read(E["LICENSE"].sha1)
print("LICENSE bytes", len(b), "has 'Copyright 2026'", b"Copyright 2026" in b, "has appendix placeholder '[yyyy]'", b"[yyyy]" in b)
