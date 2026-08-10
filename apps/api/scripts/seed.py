"""Seeds realistic local demo data (CLAUDE.md §70).

Run with:  python scripts/seed.py [--reset]

Deliberately drives the same service layer the API uses (not raw INSERTs)
so seeding also exercises audit logging, notification fan-out and workflow
transitions exactly as a real user session would.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import (  # noqa: E402
    MODULE_BIRTHDAY,
    MODULE_SPARK,
    MODULE_TALENT_FLOW,
    CanonicalStage,
    CustomerSuccessStatus,
    PlatformRole,
    TalentFlowRole,
)
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.external_mapping import ExternalMapping  # noqa: E402
from app.models.module import ApplicationModule  # noqa: E402
from app.models.user import User, UserModuleRole  # noqa: E402
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


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed() -> None:
    db = SessionLocal()
    try:
        # --- Module registry --------------------------------------------
        db.add_all(
            [
                ApplicationModule(
                    key=MODULE_TALENT_FLOW,
                    name="DijiTalentFlow",
                    description="Talent Operations and Client Tracking",
                    icon="Users",
                    route="/talent-flow",
                    status="ACTIVE",
                    enabled=True,
                    display_order=1,
                    required_roles="ANY",
                ),
                ApplicationModule(
                    key=MODULE_BIRTHDAY,
                    name="DijiBirthday",
                    description="Birthday Workflow Automation",
                    icon="Cake",
                    route="/birthday",
                    status="COMING_SOON",
                    enabled=True,
                    display_order=2,
                    required_roles="ANY",
                ),
                ApplicationModule(
                    key=MODULE_SPARK,
                    name="DijiSpark",
                    description="HR / Spark Hire Workflows",
                    icon="Sparkles",
                    route="/spark",
                    status="COMING_SOON",
                    enabled=True,
                    display_order=3,
                    required_roles="ANY",
                ),
            ]
        )

        # --- Clients ------------------------------------------------------
        abc = Client(name="ABC Company", industry="Financial Services", account_manager="Tharindu Fernando", status="ACTIVE")
        xyz = Client(name="XYZ Company", industry="Retail", account_manager="Tharindu Fernando", status="ACTIVE")
        nova = Client(name="Nova Solutions", industry="Technology", account_manager="Sanduni Wickrama", status="ACTIVE")
        db.add_all([abc, xyz, nova])
        db.flush()

        # --- Users / dev personas -----------------------------------------
        madushanka = User(
            email="madushanka@dijitalteam.com", full_name="Madushanka Weeriyasinghe",
            title="Talent Acquisition Specialist", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="madushanka-ta", avatar_color="#c9431d",
        )
        cs_user = User(
            email="tharindu.fernando@dijitalteam.com", full_name="Tharindu Fernando",
            title="Customer Success Lead", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="customer-success", avatar_color="#db4d18",
        )
        ta_manager = User(
            email="sanduni.wickrama@dijitalteam.com", full_name="Sanduni Wickrama",
            title="TA Manager", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="ta-manager", avatar_color="#aa2f1d",
        )
        platform_admin = User(
            email="admin@dijitalteam.com", full_name="Dilani Rathnayake",
            title="Platform Administrator", platform_role=PlatformRole.PLATFORM_ADMIN.value,
            persona_key="platform-admin", avatar_color="#8f2417",
        )
        abc_client_user = User(
            email="amal.perera@abc-company.example", full_name="Amal Perera",
            title="Head of Talent, ABC Company", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="abc-client", avatar_color="#f26a1b",
        )
        xyz_client_user = User(
            email="nadeesha.silva@xyz-company.example", full_name="Nadeesha Silva",
            title="VP Engineering, XYZ Company", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="xyz-client", avatar_color="#f59e0b",
        )
        nova_client_user = User(
            email="kasun.jayasuriya@nova-solutions.example", full_name="Kasun Jayasuriya",
            title="COO, Nova Solutions", platform_role=PlatformRole.PLATFORM_USER.value,
            persona_key="nova-client", avatar_color="#fbc34a",
        )
        db.add_all(
            [madushanka, cs_user, ta_manager, platform_admin, abc_client_user, xyz_client_user, nova_client_user]
        )
        db.flush()

        db.add_all(
            [
                UserModuleRole(user_id=madushanka.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MEMBER.value),
                UserModuleRole(user_id=cs_user.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.CUSTOMER_SUCCESS.value),
                UserModuleRole(user_id=ta_manager.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MANAGER.value),
                UserModuleRole(user_id=platform_admin.id, module_key=MODULE_TALENT_FLOW, role=TalentFlowRole.TA_MANAGER.value),
                UserModuleRole(
                    user_id=abc_client_user.id, module_key=MODULE_TALENT_FLOW,
                    role=TalentFlowRole.TALENT_CLIENT.value, client_id=abc.id,
                ),
                UserModuleRole(
                    user_id=xyz_client_user.id, module_key=MODULE_TALENT_FLOW,
                    role=TalentFlowRole.TALENT_CLIENT.value, client_id=xyz.id,
                ),
                UserModuleRole(
                    user_id=nova_client_user.id, module_key=MODULE_TALENT_FLOW,
                    role=TalentFlowRole.TALENT_CLIENT.value, client_id=nova.id,
                ),
            ]
        )
        db.commit()

        # --- Talent requests (via service, exercises workflow + audit) ----
        request_service = TalentRequestService(db)

        req1 = request_service.create_request(
            client_id=abc.id, created_by=abc_client_user.id,
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
            client_id=abc.id, created_by=abc_client_user.id,
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
            client_id=xyz.id, created_by=xyz_client_user.id,
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
            client_id=nova.id, created_by=nova_client_user.id,
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
            client_id=nova.id, created_by=nova_client_user.id,
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
                request_id=req.id, actor_id=cs_user.id,
                decision=CustomerSuccessStatus.APPROVED.value, reason="Validated scope and budget with client.",
            )
        db.commit()

        request_service.update_stage(
            request_id=req1.id, actor_id=madushanka.id, stage=CanonicalStage.SCREENING.value,
            client_safe_status_text="Screening candidates against the brand strategy brief",
        )
        request_service.update_stage(
            request_id=req2.id, actor_id=madushanka.id, stage=CanonicalStage.INTERVIEWS.value,
            client_safe_status_text="Client interviews in progress",
        )
        request_service.update_stage(
            request_id=req3.id, actor_id=madushanka.id, stage=CanonicalStage.SOURCING.value,
            client_safe_status_text="Sourcing senior Python engineers",
        )
        request_service.update_stage(
            request_id=req4.id, actor_id=madushanka.id, stage=CanonicalStage.OFFER.value,
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

        # --- Applications (Ron Axel spans two clients — CLAUDE.md §19) -----
        application_service = ApplicationService(db)

        ron_ppd_app = application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=ron_axel.id, talent_request_id=req2.id, current_stage=CanonicalStage.INTERVIEWS.value
            ),
        )
        application_service.update_status(
            application_id=ron_ppd_app.id, actor_id=madushanka.id, status="CLIENT_REVIEW", rejection_reason=""
        )
        application_service.update_score(
            application_id=ron_ppd_app.id, actor_id=madushanka.id, score=8.9,
            recruiter_notes="Strong Dataverse depth; client is enthusiastic.",
        )
        application_service.update_visibility(
            application_id=ron_ppd_app.id, actor_id=madushanka.id, is_client_visible=True,
            client_visible_notes="Strong technical match with recent enterprise Power Platform delivery experience.",
        )

        ron_py_app = application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=ron_axel.id, talent_request_id=req3.id, current_stage=CanonicalStage.SOURCING.value
            ),
        )
        application_service.update_score(
            application_id=ron_py_app.id, actor_id=madushanka.id, score=7.4,
            recruiter_notes="Secondary fit — Python skills are dated but promising.",
        )

        ayesha_app = application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=ayesha.id, talent_request_id=req1.id, current_stage=CanonicalStage.SCREENING.value
            ),
        )
        application_service.update_visibility(
            application_id=ayesha_app.id, actor_id=madushanka.id, is_client_visible=True,
            client_visible_notes="Strong brand campaign portfolio; scheduling internal screen.",
        )

        dinuka_app = application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=dinuka.id, talent_request_id=req4.id, current_stage=CanonicalStage.OFFER.value
            ),
        )
        application_service.update_status(
            application_id=dinuka_app.id, actor_id=madushanka.id, status="OFFER", rejection_reason=""
        )
        application_service.update_score(
            application_id=dinuka_app.id, actor_id=madushanka.id, score=9.2,
            recruiter_notes="Top candidate; offer in final negotiation.",
        )
        application_service.update_visibility(
            application_id=dinuka_app.id, actor_id=madushanka.id, is_client_visible=True,
            client_visible_notes="Offer being finalized — expected start within two weeks of acceptance.",
        )

        kavindu_app = application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=kavindu.id, talent_request_id=req2.id, current_stage=CanonicalStage.SCREENING.value
            ),
        )
        application_service.update_status(
            application_id=kavindu_app.id, actor_id=madushanka.id, status="SHORTLISTED", rejection_reason=""
        )

        application_service.create_application(
            actor_id=madushanka.id,
            payload=ApplicationCreate(
                candidate_id=sarah.id, talent_request_id=req3.id, current_stage=CanonicalStage.SOURCING.value
            ),
        )
        db.commit()

        # --- Interviews -------------------------------------------------------
        interview_service = InterviewService(db)
        interview_service.create_interview(
            actor_id=madushanka.id,
            payload=InterviewCreate(
                application_id=ron_ppd_app.id, scheduled_at=datetime.now(UTC) + timedelta(days=2, hours=3),
                interview_type="CLIENT_INTERVIEW", meeting_link="https://meet.dijitalteam.com/abc-ron-axel",
                client_visible=True, notes="Panel: ABC engineering lead + delivery manager.",
            ),
        )
        interview_service.create_interview(
            actor_id=madushanka.id,
            payload=InterviewCreate(
                application_id=dinuka_app.id, scheduled_at=datetime.now(UTC) - timedelta(days=3),
                interview_type="FINAL", meeting_link="https://meet.dijitalteam.com/nova-dinuka-peris",
                client_visible=True, notes="Final round — architecture deep dive completed.",
            ),
        )
        completed = interview_service.repo.list_for_application(dinuka_app.id)[0]
        interview_service.update_status(
            interview_id=completed.id, actor_id=madushanka.id, status="COMPLETED",
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
            talent_request_id=req2.id, sender_id=abc_client_user.id,
            sender_role=TalentFlowRole.TALENT_CLIENT.value,
            body="Excited about Ron's profile — can we get the interview scheduled this week?",
        )
        message_service.send_message(
            talent_request_id=req2.id, sender_id=madushanka.id,
            sender_role=TalentFlowRole.TA_MEMBER.value,
            body="Absolutely — client interview is booked, calendar invite going out shortly.",
        )
        db.commit()

        # --- Documents ------------------------------------------------------
        document_service = DocumentService(db)
        document_service.upload_document(
            actor_id=madushanka.id,
            payload=DocumentCreate(talent_request_id=req2.id, file_name="Ron_Axel_CV.pdf", category="CV"),
        )
        document_service.upload_document(
            actor_id=abc_client_user.id,
            payload=DocumentCreate(
                talent_request_id=req2.id, file_name="ABC_Power_Platform_Requirement.pdf", category="REQUIREMENT"
            ),
        )
        db.commit()

        request_codes = ", ".join(r.request_code for r in (req1, req2, req3, req4, req5))
        print("Seed complete.")
        print(f"  Clients: {abc.name}, {xyz.name}, {nova.name}")
        print(f"  Talent requests: {request_codes}")
        print(
            "  Dev personas: madushanka-ta, customer-success, ta-manager, "
            "platform-admin, abc-client, xyz-client, nova-client"
        )
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_schema()
    seed()
