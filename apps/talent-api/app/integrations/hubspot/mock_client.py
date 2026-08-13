from app.integrations.hubspot.client import HubSpotClient
from app.integrations.hubspot.schemas import HubSpotCompany, HubSpotContact, HubSpotDeal

_COMPANIES = [
    HubSpotCompany(id="hs-abc", name="ABC Company", industry="Financial Services", domain="abc-company.example"),
    HubSpotCompany(id="hs-xyz", name="XYZ Company", industry="Retail", domain="xyz-company.example"),
    HubSpotCompany(id="hs-nova", name="Nova Solutions", industry="Technology", domain="nova-solutions.example"),
]

_CONTACTS = {
    "hs-abc": [
        HubSpotContact(
            id="hs-c-abc-1", company_id="hs-abc", first_name="Priya", last_name="Fernando",
            email="priya.fernando@abc-company.example", job_title="Head of Talent",
        )
    ],
    "hs-xyz": [
        HubSpotContact(
            id="hs-c-xyz-1", company_id="hs-xyz", first_name="Daniel", last_name="Cole",
            email="daniel.cole@xyz-company.example", job_title="VP Engineering",
        )
    ],
    "hs-nova": [
        HubSpotContact(
            id="hs-c-nova-1", company_id="hs-nova", first_name="Ishara", last_name="Gunawardena",
            email="ishara.gunawardena@nova-solutions.example", job_title="COO",
        )
    ],
}

_DEALS = {
    "hs-abc": [
        HubSpotDeal(id="hs-d-abc-1", company_id="hs-abc", name="ABC Talent Partnership FY26", stage="closedwon", amount=45000)
    ],
    "hs-xyz": [
        HubSpotDeal(id="hs-d-xyz-1", company_id="hs-xyz", name="XYZ Recruitment Retainer", stage="closedwon", amount=32000)
    ],
    "hs-nova": [
        HubSpotDeal(id="hs-d-nova-1", company_id="hs-nova", name="Nova Solutions Staffing", stage="closedwon", amount=28000)
    ],
}


class MockHubSpotClient(HubSpotClient):
    """Realistic in-memory HubSpot data matching the seeded demo clients."""

    def list_companies(self) -> list[HubSpotCompany]:
        return list(_COMPANIES)

    def get_company(self, company_id: str) -> HubSpotCompany | None:
        return next((c for c in _COMPANIES if c.id == company_id), None)

    def list_contacts(self, company_id: str) -> list[HubSpotContact]:
        return list(_CONTACTS.get(company_id, []))

    def list_deals(self, company_id: str) -> list[HubSpotDeal]:
        return list(_DEALS.get(company_id, []))
