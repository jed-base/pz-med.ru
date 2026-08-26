#!/usr/bin/env python3
from __future__ import annotations

from app import create_app
from app.extensions import db
from app.models import (
    DutyDate,
    EmployeeAbsence,
    VacationPeriod,
)


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
        .filter(
            VacationPeriod.period_type == "approved",
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
                    db.session.delete(assignment)
                    removed += 1

        db.session.commit()

        print(
            "Demo duty validation complete: "
            f"removed {removed} conflicting assignments"
        )


if __name__ == "__main__":
    validate()
