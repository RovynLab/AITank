import sys, json
sys.path.insert(0, r"e:\work\AITank")
try:
    from petcar.skills.express import list_actions
    print(json.dumps(list_actions(), ensure_ascii=False))
except Exception as e:
    print("ERR express:", e)
