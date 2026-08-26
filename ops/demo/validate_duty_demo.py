#!/usr/bin/env python3
from __future__ import annotations

from app import create_app
from app.extensions import db
from app.models import (
    DutyAssignment,
    DutyDate,
    EmployeeAbsence,
    VacationPeriod,
)


DEMO_PERSONNEL_NUMBER = "DEMO-001"


def _has_absence(employee_id: int, duty_date) -> bool:
    return (
        EmployeeAbsence.query
        .filter(
            EmployeeAbsence.employee_id == employee_id,
            EmployeeAbsence.status == "confirmed",
            EmployeeAbsence.start_date <= duty_date,
            EmployeeAbsence.end_date >= duty_date,
        )
        .first()
        is not None
    )


def _has_approved_vacation(employee_id: int, duty_date) -> bool:
    return (
        VacationPeriod.query
        .join(VacationPeriod.plan)
        .filter(
            VacationPeriod.start_date <= duty_date,
            VacationPeriod.end_date >= duty_date,
            VacationPeriod.plan.has(
                employee_id=employee_id,
                status="approved",
            ),
        )
        .first()
        is not None
    )


def validate() -> None:
    app = create_app()

    with app.app_context():
        removed = 0
        demo_removed = 0

        duty_dates = (
            DutyDate.query
            .filter(DutyDate.is_active.is_(True))
            .order_by(DutyDate.duty_date.asc(), DutyDate.id.asc())
            .all()
        )

        for duty_date in duty_dates:
            for assignment in list(duty_date.assignments):
                employee = assignment.employee
                if employee is None:
                    continue

                unavailable = (
                    _has_absence(employee.id, duty_date.duty_date)
                    or _has_approved_vacation(employee.id, duty_date.duty_date)
                )

                if unavailable:
                    if employee.personnel_number == DEMO_PERSONNEL_NUMBER:
                        demo_removed += 1
                    db.session.delete(assignment)
                    removed += 1

        db.session.commit()

        print(
            "Demo duty validation complete: "
            f"removed {removed} conflicting assignments"
        )
        print(
            "Demo logged-in user conflicts removed: "
            f"{demo_removed}"
        )


if __name__ == "__main__":
    validate()
