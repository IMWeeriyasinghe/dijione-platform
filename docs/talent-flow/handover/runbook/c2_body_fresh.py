import json
from app.services.recruitment_consumer_service import get_recruitment_batch_client
print("C2R " + json.dumps(get_recruitment_batch_client().get_freshness().get("source_snapshot") or {}, default=str), flush=True)
