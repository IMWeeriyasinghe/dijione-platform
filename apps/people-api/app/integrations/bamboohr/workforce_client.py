"""BambooHRWorkforceClient interface — the provider seam behind the generic
Workforce Directory. Separate from ``client.BambooHRClient`` so the
Birthday-oriented Employee contract is never touched by workforce changes.
Never writes to BambooHR."""

from abc import ABC, abstractmethod

from app.integrations.bamboohr.workforce_schemas import BambooHRWorkforceRecord


class BambooHRWorkforceClient(ABC):
    @abstractmethod
    def list_workforce_records(self) -> list[BambooHRWorkforceRecord]:
        """Every employee record, Active and Inactive — no status or
        birthday filtering."""
        ...
