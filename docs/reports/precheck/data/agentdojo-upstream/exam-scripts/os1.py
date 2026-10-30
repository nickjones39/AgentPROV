"""OS-1: population raw rates per arm vs paper numbers (prereg section 4), README gap rule. Counts only."""
import json, sys
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson

pop = json.load(open(sys.argv[1]))
P = {  # dir: (U, UA, ASR)
    "P3": {"gpt-4o-2024-05-13": (69.00, 50.08, 47.69), "claude-3-opus-20240229": (66.61, 52.46, 11.29), "claude-3-sonnet-20240229": (53.10, 33.23, 26.71),
           "command-r-plus": (25.44, 25.12, 0.95), "gpt-3.5-turbo-0125": (33.86, 34.66, 8.43), "gpt-4-turbo-2024-04-09": (63.43, 54.05, 28.62),
           "gemini-1.5-flash-001": (36.09, 34.18, 12.24), "gemini-1.5-pro-001": (45.63, 28.93, 25.60), "meta-llama_Llama-3-70b-chat-hf": (34.50, 18.28, 20.03),
           "claude-3-5-sonnet-20240620": (78.22, 51.19, 33.86), "gpt-4o-2024-05-13-spotlighting_with_delimiting": (72.66, 55.64, 41.65),
           "gpt-4o-2024-05-13-transformers_pi_detector": (41.49, 21.14, 7.95), "gpt-4o-2024-05-13-repeat_user_prompt": (85.53, 67.25, 27.82),
           "gpt-4o-2024-05-13-tool_filter": (73.13, 56.28, 6.84)},
    "P1": {"gpt-4o-2024-05-13": (69.00, 44.99, 53.10), "claude-3-opus-20240229": (64.39, 49.60, 12.89), "claude-3-sonnet-20240229": (53.10, 30.05, 30.52),
           "command-r-plus": (27.78, 25.60, 0.95), "gpt-3.5-turbo-0125": (34.98, 34.82, 8.90), "gpt-4-turbo-2024-04-09": (58.98, 51.67, 31.96),
           "gemini-1.5-flash-001": (36.09, 34.02, 13.35), "gemini-1.5-pro-001": (42.29, 29.61, 27.50), "meta-llama_Llama-3-70b-chat-hf": (31.16, 19.39, 15.10),
           "gpt-4o-2024-05-13-spotlighting_with_delimiting": (72.66, 50.24, 46.26), "gpt-4o-2024-05-13-transformers_pi_detector": (41.49, 20.67, 7.95),
           "gpt-4o-2024-05-13-repeat_user_prompt": (73.13, 65.66, 30.84), "gpt-4o-2024-05-13-tool_filter": (73.13, 53.26, 7.47)},
    "SA1": {"meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt": (56.7, 39.0, 14.1), "Meta-SecAlign-70B-repeat_user_prompt": (77.3, 72.3, 2.1),
            "meta-llama_Llama-3.3-70B-Instruct": (55.7, 37.4, 22.6), "Meta-SecAlign-70B": (75.3, 72.7, 2.3)},
    "SA2": {"meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt": (59.8, 43.4, 14.7), "Meta-SecAlign-70B-repeat_user_prompt": (84.5, 79.5, 1.9),
            "meta-llama_Llama-3.3-70B-Instruct": (62.9, 41.9, 23.0), "Meta-SecAlign-70B": (79.4, 77.1, 2.3)},
}
ATT = {"P1": {"direct": 3.66, "ignore_previous": 5.41, "injecagent": 5.72, "important_instructions_no_names": 45.8,
              "important_instructions_wrong_user_name": 23.2, "important_instructions_wrong_model_name": 25.1,
              "important_instructions_no_model_name": 49.8, "important_instructions_no_user_name": 44.4},
       "P3": {"direct": 3.66, "ignore_previous": 5.41, "injecagent": 5.72, "important_instructions_no_names": 45.8,
              "important_instructions_wrong_user_name": 23.2, "important_instructions_wrong_model_name": 23.7,
              "important_instructions_no_model_name": 46.1, "important_instructions_no_user_name": 44.8}}


def row(arm, part, paper, metric, k, n, rate_pct, exp, note=""):
    lo, hi = wilson(k, n)
    g = rate_pct - exp
    excl = max(100 * lo - exp, exp - 100 * hi, 0)
    flag = (abs(g) > 15 and n >= 20) or excl > 5
    return {"arm": arm, "part": part, "paper": paper, "metric": metric, "n": n, "k": k, "rate": round(rate_pct, 2),
            "wilson95": [round(100 * lo, 2), round(100 * hi, 2)], "paper_value": exp, "gap_pp": round(g, 2),
            "excluded_by_pp": round(excl, 2), "flag": flag, "cell_diff": round(n * g / 100, 1), "note": note}


rows = []
for part, papers in (("head", ("P3", "SA1", "SA2")), ("2024-06", ("P1",))):
    arms = pop[part]["arms"]
    for paper in papers:
        for d, (U, UA, ASR) in P[paper].items():
            a = arms[d]
            ii = a["attacks"]["important_instructions"]
            if paper.startswith("SA"):
                rows.append(row(d, part, paper, "utility k/97", a["benign_k"], a["benign_n"], a["benign_u_pct"], U))
                rows.append(row(d, part, paper, "UA k/n_II", ii["ua_k"], ii["n"], ii["ua_pct"], UA, f"n_II={ii['n']}"))
                rows.append(row(d, part, paper, "ASR k/n_II", ii["asr_k"], ii["n"], ii["asr_pct"], ASR, f"n_II={ii['n']}"))
            else:
                rows.append(row(d, part, paper, "utility (suite-weighted /629)", a["benign_k"], a["benign_n"], a["benign_paper_weighted_pct"], U,
                                "Wilson from k/97; rate is the inferred paper weighting"))
                rows.append(row(d, part, paper, "UA k/629", ii["ua629_k"], ii["n629"], ii["ua629_pct"], UA))
                rows.append(row(d, part, paper, "ASR k/629", ii["asr629_k"], ii["n629"], ii["asr629_pct"], ASR,
                                f"run errors with security=true: {ii['asr629_k_run_error']}; excl. run errors {round(100*ii['asr629_k_excl_run_errors']/629,2)}"))
        if paper in ATT:
            for at, v in ATT[paper].items():
                c = arms["gpt-4o-2024-05-13"]["attacks"][at]
                rows.append(row("gpt-4o-2024-05-13/" + at, part, paper, "ASR k/629", c["asr629_k"], c["n629"], c["asr629_pct"], v))
json.dump(rows, open(sys.argv[2], "w"), indent=1)
for r in rows:
    if r["flag"] or abs(r["cell_diff"]) >= 1:
        print(r["part"], r["paper"], r["arm"], r["metric"], r["rate"], r["paper_value"], r["gap_pp"], r["wilson95"], "FLAG" if r["flag"] else "", r["note"])
print(len(rows), "rows;", sum(r["flag"] for r in rows), "flagged")
