# Runs inside talent-api. Read-only: C2 integrity counts and hashes (no names or personal data).
import hashlib, json
from sqlalchemy import text as t
from app.db.session import SessionLocal

s = SessionLocal()
s.execute(t("SET TRANSACTION READ ONLY"))
q = lambda x: s.execute(t(x)).scalar()
h = lambda x: hashlib.sha256(repr([tuple(r) for r in s.execute(t(x))]).encode()).hexdigest()[:16]
o = {"read_only": q("show transaction_read_only"), "head": q("select version_num from alembic_version")}
for n in ["candidates", "applications", "talent_requests", "posting_client_mappings", "clients", "magic_link_grants",
          "recruitment_posting_refs", "interviews", "messages", "documents"]:
    o[n] = q("select count(*) from " + n)
o["map_status_source"] = [list(r) for r in s.execute(t("select status,source,count(*) from posting_client_mappings group by 1,2 order by 1,2"))]
o["map_resolution"] = [list(r) for r in s.execute(t("select resolution_status,count(*) from posting_client_mappings group by 1 order by 1"))]
o["verified_hash"] = h("select posting_external_id,client_id,source from posting_client_mappings where status='VERIFIED' order by 1")
o["verified_ids"] = [list(r) for r in s.execute(t("select posting_external_id,client_id,source from posting_client_mappings where status='VERIFIED' order by 1"))]
o["client_hash"] = h("select id,platform_client_id,name,status from clients order by 1")
o["grant_hash"] = h("select id,client_id,scope_type,expires_at,revoked_at from magic_link_grants order by 1")
o["visible_apps"] = q("select count(*) from applications where is_client_visible")
o["dup_candidate_request"] = q("select count(*) from (select candidate_id,talent_request_id from applications group by 1,2 having count(*)>1) x")
o["dup_lever_opportunity"] = q("select count(*) from (select lever_opportunity_id from applications where lever_opportunity_id is not null group by 1 having count(*)>1) x")
o["dup_lever_candidate"] = q("select count(*) from (select lever_external_id from candidates where lever_external_id is not null group by 1 having count(*)>1) x")
o["requests_per_posting_gt1"] = q("select count(*) from (select posting_external_id from talent_requests where posting_external_id is not null group by 1 having count(*)>1) x")
o["cross_client_requests"] = q("select count(*) from talent_requests r join posting_client_mappings m on m.posting_external_id=r.posting_external_id "
                               "where m.status='VERIFIED' and m.client_id<>r.client_id")
o["requests_on_unverified"] = q("select count(*) from talent_requests r where r.posting_external_id is not null and not exists "
                                "(select 1 from posting_client_mappings m where m.posting_external_id=r.posting_external_id and m.status='VERIFIED')")
o["apps_on_unverified"] = q("select count(*) from applications a join talent_requests r on r.id=a.talent_request_id where r.posting_external_id is not null and not exists "
                            "(select 1 from posting_client_mappings m where m.posting_external_id=r.posting_external_id and m.status='VERIFIED')")
o["verified_without_request"] = q("select count(*) from posting_client_mappings m where m.status='VERIFIED' and not exists "
                                  "(select 1 from talent_requests r where r.posting_external_id=m.posting_external_id)")
o["apps_from_lever"] = q("select count(*) from applications where lever_opportunity_id is not null")
o["candidates_from_lever"] = q("select count(*) from candidates where lever_external_id is not null")
o["outbox_table"] = q("select to_regclass('audit_outbox') is not null")
if o["outbox_table"]:
  o["outbox"] = [list(r) for r in s.execute(t("select status,count(*) from audit_outbox group by 1 order by 1"))]
  o["outbox_claimed"] = q("select count(*) from audit_outbox where claim_token is not null")
  o["outbox_reconcile"] = q("select count(*) from audit_outbox where payload not like '%AuditInfraTest%'")
s.rollback()
print("C2R " + json.dumps(o, default=str))
