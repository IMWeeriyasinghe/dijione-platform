from dataclasses import dataclass


@dataclass
class HubSpotCompany:
    id: str
    name: str
    industry: str
    domain: str


@dataclass
class HubSpotContact:
    id: str
    company_id: str
    first_name: str
    last_name: str
    email: str
    job_title: str


@dataclass
class HubSpotDeal:
    id: str
    company_id: str
    name: str
    stage: str
    amount: float
