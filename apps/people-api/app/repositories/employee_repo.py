from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee import Employee


class EmployeeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_bamboohr_id(self, bamboohr_id: str) -> Employee | None:
        return self.db.execute(
            select(Employee).where(Employee.bamboohr_id == bamboohr_id)
        ).scalars().first()

    def list_active(self) -> list[Employee]:
        return list(
            self.db.execute(
                select(Employee).where(Employee.employment_status == "Active")
                .order_by(Employee.full_name)
            ).scalars().all()
        )

    def list_all(self) -> list[Employee]:
        return list(self.db.execute(select(Employee).order_by(Employee.full_name)).scalars().all())

    def upsert(self, bamboohr_id: str, fields: dict) -> tuple[Employee, bool]:
        existing = self.get_by_bamboohr_id(bamboohr_id)
        if existing is None:
            row = Employee(bamboohr_id=bamboohr_id, **fields)
            self.db.add(row)
            self.db.flush()
            return row, True
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing, False
