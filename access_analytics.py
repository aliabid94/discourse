import sqlite_utils
import json
import sys
from datetime import datetime
import os

args = sys.argv
assert len(args) == 2
cur_dir = os.path.dirname(__file__)

with open(args[1]) as f:
    access_data = json.load(f)

db = sqlite_utils.Database(os.path.join(cur_dir, "discourse.db"))

analytics_table = db["analytics"]
analytics = [{
    "key_value": "global", "key_type": "global", 
    "visitors": access_data["general"]["unique_visitors"]
}] # aggregate

for day in access_data["visitors"]["data"]:
    analytics.append({
        "key_type": "day",
        "key_value": datetime.strptime(day["data"], "%Y%m%d").strftime("%Y-%m-%d")+"T00:00:00Z",
        "visitors": day["visitors"]["count"]
    })
for browser in access_data["browsers"]["data"]:
    analytics.append({
        "key_type": "browser",
        "key_value": browser["data"],
        "visitors": browser["visitors"]["count"]
    })
for location in access_data["geolocation"]["data"]:
    for item in location["items"]:
        analytics.append({
            "key_type": "location",
            "key_value": item["data"],
            "visitors": item["visitors"]["count"]
        })

analytics_table.upsert_all(analytics, pk=("key_value", "key_type"))
