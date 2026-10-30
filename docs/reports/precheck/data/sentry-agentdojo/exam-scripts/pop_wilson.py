"""Wilson 95% interval in percent (shared by pop.py and cc07.py)."""
def wilson(k, n, z=1.959964):
    if not n: return [None, None]
    p = k/n; d = 1+z*z/n; c = p+z*z/(2*n); h = z*((p*(1-p)/n+z*z/(4*n*n))**.5)
    return [round(100*(c-h)/d, 2), round(100*(c+h)/d, 2)]
