exec(open("oa.py").read().split("run(\"cites")[0])
run(None,"oa_search_agentdojo_title_abs.json",search=None) if False else None
# title/abstract searches
import urllib.parse
def run2(filt,name):
    run(filt,name)
run2("title_and_abstract.search:AgentDojo","oa_q1_tiabs_AgentDojo.json")
run2("title_and_abstract.search:(prompt injection) AND (agent benchmark),publication_year:>2023","oa_q2_pi_agent_benchmark.json")
run2("fulltext.search:AgentDojo,publication_year:>2023","oa_q3_fulltext_AgentDojo.json")
run2("title_and_abstract.search:(agent trajectories) AND (security benchmark),publication_year:>2023","oa_q4_traj_security.json")
