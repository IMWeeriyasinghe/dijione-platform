"""Seeds DijiTalentFlow's local demo data: clients, talent requests,
candidates, applications, interviews, messages, documents and external
(Lever/HubSpot) mappings.

Run with:  python scripts/seed.py [--reset]

Deliberately drives the same service layer the API uses (not raw INSERTs)
so seeding also exercises the audit/notification calls to Platform Core
exactly as a real user session would (best-effort — this still succeeds
even if platform-api isn't running locally, just without those side
writes landing).

Phase 2.5 coordinated seeding: run ``apps/platform-api/scripts/seed.py``
*first* — its dev personas (madushanka=1, cs_user=2, ta_manager=3,
platform_admin=4, super_admin=5, abc_client=6, xyz_client=7, nova_client=8,
ta_portfolio=9) and client-scope rows (ABC=1, XYZ=2, Nova=3) are referenced
by user id / client id convention here, not a foreign key (talent-api and
platform-api are separate databases now). See
docs/platform/local-development.md.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import CanonicalStage, CustomerSuccessStatus, TalentFlowRole  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.external_mapping import ExternalMapping  # noqa: E402
from app.schemas.application import ApplicationCreate  # noqa: E402
from app.schemas.candidate import CandidateCreate  # noqa: E402
from app.schemas.document import DocumentCreate  # noqa: E402
from app.schemas.interview import InterviewCreate  # noqa: E402
from app.schemas.talent_request import TalentRequestCreate  # noqa: E402
from app.services.application_service import ApplicationService  # noqa: E402
from app.services.candidate_service import CandidateService  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.services.interview_service import InterviewService  # noqa: E402
from app.services.message_service import MessageService  # noqa: E402
from app.services.talent_request_service import TalentRequestService  # noqa: E402

# User id convention shared with apps/platform-api/scripts/seed.py — see
# module docstring. talent.db has no `users` table to look these up in.
MADUSHANKA_ID = 1
CS_USER_ID = 2
TA_MANAGER_ID = 3
ABC_CLIENT_USER_ID = 6
XYZ_CLIENT_USER_ID = 7
NOVA_CLIENT_USER_ID = 8

MADUSHANKA_NAME = "Madushanka Weeriyasinghe"
CS_USER_NAME = "Tharindu Fernando"
ABC_CLIENT_USER_NAME = "Amal Perera"
XYZ_CLIENT_USER_NAME = "Nadeesha Silva"
NOVA_CLIENT_USER_NAME = "Kasun Jayasuriya"


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed() -> None:
    db = SessionLocal()
    try:
        # --- Clients — inserted in this exact order so a fresh --reset
        # reseed gets ids 1/2/3, matching platform-api's seed convention. ---
        # platform_client_id references platform-api's canonical Client
        # identity (Architecture Completion Plan §6.1) — must match the slugs
        # in platform-api migration d4e5f6a7b8c9 / its seed.
        abc = Client(
            name="ABC Company", platform_client_id="cli-abc-company",
            industry="Financial Services", account_manager="Tharindu Fernando", status="ACTIVE",
        )
        xyz = Client(
            name="XYZ Company", platform_client_id="cli-xyz-company",
            industry="Retail", account_manager="Tharindu Fernando", status="ACTIVE",
        )
        nova = Client(
            name="Nova Solutions", platform_client_id="cli-nova-solutions",
            industry="Technology", account_manager="Sanduni Wickrama", status="ACTIVE",
        )
        db.add_all([abc, xyz, nova])
        db.commit()

        # --- Talent requests (via service, exercises workflow + audit) ----
        request_service = TalentRequestService(db)

        req1 = request_service.create_request(
            client_id=abc.id, created_by=ABC_CLIENT_USER_ID,
            payload=TalentRequestCreate(
                designation="Marketing Manager",
                description="Own brand strategy and campaign execution for the ABC consumer division.",
                required_skills=["Brand Strategy", "Digital Marketing", "Campaign Management"],
                seniority="Manager", location="Colombo, Sri Lanka (Hybrid)", engagement_type="FULL_TIME",
                target_start_date=date.today() + timedelta(days=45),
                notes="Replacing an internal promotion; ideally bilingual EN/SI.",
            ),
        )
        req2 = request_service.create_request(
            client_id=abc.id, created_by=ABC_CLIENT_USER_ID,
            payload=TalentRequestCreate(
                designation="Senior Power Platform Developer",
                description="Lead Power Platform delivery for ABC's internal automation roadmap.",
                required_skills=["Power Apps", "Dataverse", "Power Automate", "Azure"],
                seniority="Senior", location="Remote (Sri Lanka)", engagement_type="CONTRACT",
                target_start_date=date.today() + timedelta(days=21),
                notes="Client has already interviewed one candidate informally.",
            ),
        )
        req3 = request_service.create_request(
            client_id=xyz.id, created_by=XYZ_CLIENT_USER_ID,
            payload=TalentRequestCreate(
                designation="Senior Python Developer",
                description="Backend services for XYZ's e-commerce platform migration.",
                required_skills=["Python", "Django", "PostgreSQL", "AWS"],
                seniority="Senior", location="Colombo, Sri Lanka", engagement_type="FULL_TIME",
                target_start_date=date.today() + timedelta(days=30),
                notes="",
            ),
        )
        req4 = request_service.create_request(
            client_id=nova.id, created_by=NOVA_CLIENT_USER_ID,
            payload=TalentRequestCreate(
                designation="Cloud Solutions Architect",
                description="Own Nova Solutions' multi-cloud architecture and cost governance.",
                required_skills=["Azure", "AWS", "Kubernetes", "Solution Architecture"],
                seniority="Principal", location="Colombo, Sri Lanka (Hybrid)", engagement_type="FULL_TIME",
                target_start_date=date.today() + timedelta(days=14),
                notes="Client wants to move fast — offer stage already in discussion.",
            ),
        )
        req5 = request_service.create_request(
            client_id=nova.id, created_by=NOVA_CLIENT_USER_ID,
            payload=TalentRequestCreate(
                designation="Service Delivery Manager",
                description="Manage day-to-day delivery for Nova's largest managed-services account.",
                required_skills=["Service Delivery", "ITIL", "Stakeholder Management"],
                seniority="Manager", location="Colombo, Sri Lanka", engagement_type="FULL_TIME",
                target_start_date=date.today() + timedelta(days=60),
                notes="Newly identified need — awaiting Customer Success triage.",
            ),
        )
        db.commit()

        for req in (req1, req2, req3, req4):
            request_service.review_request(
                request_id=req.id, actor_id=CS_USER_ID,
                decision=CustomerSuccessStatus.APPROVED.value, reason="Validated scope and budget with client.",
            )
        db.commit()

        request_service.update_stage(
            request_id=req1.id, actor_id=MADUSHANKA_ID, stage=CanonicalStage.SCREENING.value,
            client_safe_status_text="Screening candidates against the brand strategy brief",
        )
        request_service.update_stage(
            request_id=req2.id, actor_id=MADUSHANKA_ID, stage=CanonicalStage.INTERVIEWS.value,
            client_safe_status_text="Client interviews in progress",
        )
        request_service.update_stage(
            request_id=req3.id, actor_id=MADUSHANKA_ID, stage=CanonicalStage.SOURCING.value,
            client_safe_status_text="Sourcing senior Python engineers",
        )
        request_service.update_stage(
            request_id=req4.id, actor_id=MADUSHANKA_ID, stage=CanonicalStage.OFFER.value,
            client_safe_status_text="Offer being finalized with the candidate",
        )
        db.commit()

        # --- Candidates -----------------------------------------------------
        candidate_service = CandidateService(db)
        ron_axel = candidate_service.create_candidate(
            CandidateCreate(
                full_name="Ron Axel", email="ron.axel@example.com", phone="+94 77 123 4567",
                professional_title="Senior Power Platform Developer",
                summary=(
                    "8+ years building enterprise automation on Power Platform and Azure; "
                    "led three greenfield Dataverse implementations."
                ),
                location="Colombo, Sri Lanka", skills=["Power Apps", "Dataverse", "Power Automate", "Azure"],
                source="LEVER",
            )
        )
        ayesha = candidate_service.create_candidate(
            CandidateCreate(
                full_name="Ayesha Wijeratne", email="ayesha.wijeratne@example.com", phone="+94 71 234 5678",
                professional_title="Marketing Manager",
                summary="6 years leading integrated brand campaigns for consumer and B2B clients across South Asia.",
                location="Colombo, Sri Lanka", skills=["Brand Strategy", "Digital Marketing", "Campaign Management"],
                source="MANUAL",
            )
        )
        dinuka = candidate_service.create_candidate(
            CandidateCreate(
                full_name="Dinuka Peris", email="dinuka.peris@example.com", phone="+94 76 345 6789",
                professional_title="Cloud Solutions Architect",
                summary="10 years designing multi-cloud architectures; AWS and Azure dual-certified solutions architect.",
                location="Colombo, Sri Lanka", skills=["Azure", "AWS", "Kubernetes", "Solution Architecture"],
                source="LEVER",
            )
        )
        kavindu = candidate_service.create_candidate(
            CandidateCreate(
                full_name="Kavindu Silva", email="kavindu.silva@example.com", phone="+94 70 456 7890",
                professional_title="Power Platform Developer",
                summary="4 years delivering Power Platform and SharePoint solutions for mid-market clients.",
                location="Kandy, Sri Lanka", skills=["Power Apps", "SharePoint", "Power Automate"],
                source="MANUAL",
            )
        )
        sarah = candidate_service.create_candidate(
            CandidateCreate(
                full_name="Sarah Perera", email="sarah.perera@example.com", phone="+94 75 567 8901",
                professional_title="Python Developer",
                summary="5 years building high-throughput backend services in Python/Django for e-commerce platforms.",
                location="Colombo, Sri Lanka", skills=["Python", "Django", "PostgreSQL"],
                source="LEVER",
            )
        )
        db.commit()

        # --- Applications (Ron Axel spans two clients) ----------------------
        application_service = ApplicationService(db)

        ron_ppd_app = application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=ron_axel.id, talent_request_id=req2.id, current_stage=CanonicalStage.INTERVIEWS.value
            ),
        )
        application_service.update_status(
            application_id=ron_ppd_app.id, actor_id=MADUSHANKA_ID, status="CLIENT_REVIEW", rejection_reason=""
        )
        application_service.update_score(
            application_id=ron_ppd_app.id, actor_id=MADUSHANKA_ID, score=8.9,
            recruiter_notes="Strong Dataverse depth; client is enthusiastic.",
        )
        application_service.update_visibility(
            application_id=ron_ppd_app.id, actor_id=MADUSHANKA_ID, is_client_visible=True,
            client_visible_notes="Strong technical match with recent enterprise Power Platform delivery experience.",
        )

        ron_py_app = application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=ron_axel.id, talent_request_id=req3.id, current_stage=CanonicalStage.SOURCING.value
            ),
        )
        application_service.update_score(
            application_id=ron_py_app.id, actor_id=MADUSHANKA_ID, score=7.4,
            recruiter_notes="Secondary fit — Python skills are dated but promising.",
        )

        ayesha_app = application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=ayesha.id, talent_request_id=req1.id, current_stage=CanonicalStage.SCREENING.value
            ),
        )
        application_service.update_visibility(
            application_id=ayesha_app.id, actor_id=MADUSHANKA_ID, is_client_visible=True,
            client_visible_notes="Strong brand campaign portfolio; scheduling internal screen.",
        )

        dinuka_app = application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=dinuka.id, talent_request_id=req4.id, current_stage=CanonicalStage.OFFER.value
            ),
        )
        application_service.update_status(
            application_id=dinuka_app.id, actor_id=MADUSHANKA_ID, status="OFFER", rejection_reason=""
        )
        application_service.update_score(
            application_id=dinuka_app.id, actor_id=MADUSHANKA_ID, score=9.2,
            recruiter_notes="Top candidate; offer in final negotiation.",
        )
        application_service.update_visibility(
            application_id=dinuka_app.id, actor_id=MADUSHANKA_ID, is_client_visible=True,
            client_visible_notes="Offer being finalized — expected start within two weeks of acceptance.",
        )

        kavindu_app = application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=kavindu.id, talent_request_id=req2.id, current_stage=CanonicalStage.SCREENING.value
            ),
        )
        application_service.update_status(
            application_id=kavindu_app.id, actor_id=MADUSHANKA_ID, status="SHORTLISTED", rejection_reason=""
        )

        application_service.create_application(
            actor_id=MADUSHANKA_ID,
            payload=ApplicationCreate(
                candidate_id=sarah.id, talent_request_id=req3.id, current_stage=CanonicalStage.SOURCING.value
            ),
        )
        db.commit()

        # --- Interviews -------------------------------------------------------
        interview_service = InterviewService(db)
        interview_service.create_interview(
            actor_id=MADUSHANKA_ID,
            payload=InterviewCreate(
                application_id=ron_ppd_app.id, scheduled_at=datetime.now(UTC) + timedelta(days=2, hours=3),
                interview_type="CLIENT_INTERVIEW", meeting_link="https://meet.dijitalteam.com/abc-ron-axel",
                client_visible=True, notes="Panel: ABC engineering lead + delivery manager.",
            ),
        )
        interview_service.create_interview(
            actor_id=MADUSHANKA_ID,
            payload=InterviewCreate(
                application_id=dinuka_app.id, scheduled_at=datetime.now(UTC) - timedelta(days=3),
                interview_type="FINAL", meeting_link="https://meet.dijitalteam.com/nova-dinuka-peris",
                client_visible=True, notes="Final round — architecture deep dive completed.",
            ),
        )
        completed = interview_service.repo.list_for_application(dinuka_app.id)[0]
        interview_service.update_status(
            interview_id=completed.id, actor_id=MADUSHANKA_ID, status="COMPLETED",
            notes="Strong final round; proceeding to offer.",
        )
        db.commit()

        # --- External mappings (Lever/HubSpot, read-only demo linkage) ------
        db.add_all(
            [
                ExternalMapping(
                    provider="LEVER", external_object_type="opportunity", external_id="opp-ron-axel-ppd",
                    internal_object_type="Application", internal_id=ron_ppd_app.id,
                    last_synced_at=datetime.now(UTC), sync_status="SYNCED",
                ),
                ExternalMapping(
                    provider="LEVER", external_object_type="opportunity", external_id="opp-ron-axel-py",
                    internal_object_type="Application", internal_id=ron_py_app.id,
                    last_synced_at=datetime.now(UTC), sync_status="SYNCED",
                ),
                ExternalMapping(
                    provider="HUBSPOT", external_object_type="company", external_id="hs-abc",
                    internal_object_type="Client", internal_id=abc.id,
                    last_synced_at=datetime.now(UTC), sync_status="SYNCED",
                ),
                ExternalMapping(
                    provider="HUBSPOT", external_object_type="company", external_id="hs-xyz",
                    internal_object_type="Client", internal_id=xyz.id,
                    last_synced_at=datetime.now(UTC), sync_status="SYNCED",
                ),
                ExternalMapping(
                    provider="HUBSPOT", external_object_type="company", external_id="hs-nova",
                    internal_object_type="Client", internal_id=nova.id,
                    last_synced_at=datetime.now(UTC), sync_status="SYNCED",
                ),
            ]
        )
        db.commit()

        # --- Messages -----------------------------------------------------
        message_service = MessageService(db)
        message_service.send_message(
            talent_request_id=req2.id, sender_id=ABC_CLIENT_USER_ID, sender_name=ABC_CLIENT_USER_NAME,
            sender_role=TalentFlowRole.TALENT_CLIENT.value,
            body="Excited about Ron's profile — can we get the interview scheduled this week?",
        )
        message_service.send_message(
            talent_request_id=req2.id, sender_id=MADUSHANKA_ID, sender_name=MADUSHANKA_NAME,
            sender_role=TalentFlowRole.TA_MEMBER.value,
            body="Absolutely — client interview is booked, calendar invite going out shortly.",
        )
        db.commit()

        # --- Documents ------------------------------------------------------
        document_service = DocumentService(db)
        document_service.upload_document(
            actor_id=MADUSHANKA_ID, actor_name=MADUSHANKA_NAME,
            payload=DocumentCreate(talent_request_id=req2.id, file_name="Ron_Axel_CV.pdf", category="CV"),
        )
        document_service.upload_document(
            actor_id=ABC_CLIENT_USER_ID, actor_name=ABC_CLIENT_USER_NAME,
            payload=DocumentCreate(
                talent_request_id=req2.id, file_name="ABC_Power_Platform_Requirement.pdf", category="REQUIREMENT"
            ),
        )
        db.commit()

        request_codes = ", ".join(r.request_code for r in (req1, req2, req3, req4, req5))
        print("DijiTalentFlow seed complete.")
        print(f"  Clients: {abc.name} (id={abc.id}), {xyz.name} (id={xyz.id}), {nova.name} (id={nova.id})")
        print(f"  Talent requests: {request_codes}")
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_schema()
    seed()
