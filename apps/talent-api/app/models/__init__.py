from app.db.base import Base
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.client import Client
from app.models.document import Document
from app.models.interview import Interview
from app.models.magic_link_grant import MagicLinkGrant
from app.models.message import Message
from app.models.posting_client_mapping import PostingClientMapping
from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.models.talent_request import TalentRequest

__all__ = [
    "Base",
    "Application",
    "Candidate",
    "Client",
    "Document",
    "Interview",
    "MagicLinkGrant",
    "Message",
    "PostingClientMapping",
    "RecruitmentPostingRef",
    "TalentRequest",
]
