import json, sys, os
sys.path.insert(0, r"e:\work\AITank")
from petcar.core import runtime_config
from petcar.blocks.catalog import get_schema
out = {"config": {"ok": True, "groups": runtime_config.GROUPS, "fields": runtime_config.snapshot()["fields"]},
       "schema": get_schema()}
p = r"e:\work\AITank\petcar\docs\_mock_seed.json"
with open(p, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print("ok", len(out["config"]["fields"]), "fields,", len(json.dumps(out["schema"])), "bytes schema")
