import json, os, sys
print("C2R " + json.dumps({"probe": True, "cwd": os.getcwd(), "db_secret_present": bool(os.environ.get("DATABASE_URL")), "py": sys.version.split()[0]}), flush=True)
