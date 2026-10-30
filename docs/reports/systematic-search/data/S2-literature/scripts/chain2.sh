set -e
python3 -I fupdate.py
python3 -I pass2.py | tail -1
python3 -I pass2s.py | tail -1
python3 -I pass3.py | tail -1
python3 -I mkqueue2.py
python3 hfzen.py | tail -1
python3 webtree3.py | tail -1
echo CHAIN-DONE
