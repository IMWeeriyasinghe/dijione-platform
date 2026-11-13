
import time; T0 = time.monotonic()
import json, resource
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services import recruitment_consumer_service as c
from app.services.audit_outbox_service import audit_outbox_scope
from app.services.side_effects import collect_side_effects
V = "select posting_external_id,client_id,source,status,resolution_status,dtc_source_tag from posting_client_mappings where status='VERIFIED'"
out = {"timing": {}}; tm = out["timing"]
with SessionLocal() as db:
    db.execute(text("select 1")); tm["startup_and_connect_s"] = round(time.monotonic() - T0, 1)
    before = {r[0]: r for r in db.execute(text(V))}
    prior = {r[0]: list(r[1:]) for r in db.execute(text("select posting_external_id,client_id,source,status,resolution_status,dtc_source_tag from posting_client_mappings"))}
    db.rollback()
    with collect_side_effects() as fx, c.reconcile_guard(db) as ok:   # the guard always rolls back
        if not ok:
            out = {"lock": "held"}
        else:
            svc = c.RecruitmentConsumerService(db, client=c.get_recruitment_batch_client())
            t1 = time.monotonic(); hold, snap = c.upstream_hold(svc.client); tm["freshness_check_s"] = round(time.monotonic() - t1, 1)
            out["upstream"] = snap
            if hold:
                out["hold"] = hold
            else:
                db.commit = lambda: None   # rehearsal: nothing may commit
                t2 = time.monotonic()
                with audit_outbox_scope(db):
                    out["result"] = svc.refresh_projection_and_reconcile(budget_seconds=c.RECONCILE_BUDGET_SECONDS)
                tm["reconcile_processing_s"] = round(time.monotonic() - t2, 1)
                out["side_effects_discarded"] = len(fx)
                out["outcome"] = c.classify_reconcile_result(out["result"])
                after = {r[0]: r for r in db.execute(text(V))}
                out["verified_before"], out["verified_after"] = len(before), len(after)
                out["lost_verified"] = sorted(set(before) - set(after))
                out["changed_verified"] = sorted(k for k in before if k in after and tuple(before[k]) != tuple(after[k]))
                new = []
                for k in sorted(set(after) - set(before)):
                    r = after[k]; cl = db.execute(text("select id,platform_client_id,name,status from clients where id=:i"), {"i": r[1]}).first()
                    tag_name = (r[5] or "")[len("DTC - "):] if (r[5] or "").startswith("DTC - ") else None
                    matches = db.execute(text("select count(*) from clients where lower(trim(name))=lower(trim(:n))"), {"n": tag_name or ""}).scalar()
                    ref = db.execute(text("select count(*) from recruitment_posting_refs where external_id=:p"), {"p": k}).scalar()
                    new.append({"posting_external_id": k, "prior": prior.get(k), "now": list(r[1:]), "tag": r[5],
                                "client": list(cl) if cl else None, "clients_matching_tag_name": matches, "posting_ref_rows": ref})
                out["newly_verified"] = new
    db.rollback()
tm["total_wall_clock_s"] = round(time.monotonic() - T0, 1)
out["elapsed_seconds"] = tm["total_wall_clock_s"]
out["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
print("C2R " + json.dumps(out, default=str), flush=True)
