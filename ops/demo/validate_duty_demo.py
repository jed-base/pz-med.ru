#!/usr/bin/env python3
from __future__ import annotations

from app import create_app
from app.extensions import db
from app.models import (
    DutyAssignment,
    DutyDate,
    EmployeeAbsence,
    EmployeeAssignment,
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


def _is_unavailable(employee_id: int, duty_date) -> bool:
    return (
        _has_absence(employee_id, duty_date)
        or _has_approved_vacation(employee_id, duty_date)
    )


def _backfill_duty_date(duty_date: DutyDate) -> int:
    """Оставляет одно свободное место, но не создаёт фиктивных конфликтов."""
    department_id = duty_date.responsible_department_id
    if department_id is None:
        return 0

    desired_count = max(duty_date.people_count - 1, 0)
    current = (
        DutyAssignment.query
        .filter_by(duty_date_id=duty_date.id)
        .order_by(DutyAssignment.sort_order.asc(), DutyAssignment.id.asc())
        .all()
    )

    if len(current) >= desired_count:
        return 0

    assigned_employee_ids = {
        assignment.employee_id
        for assignment in current
    }
    next_sort_order = max(
        (assignment.sort_order or 0 for assignment in current),
        default=0,
    ) + 10

    candidates = (
        EmployeeAssignment.query
        .filter_by(
            department_id=department_id,
            is_active=True,
        )
        .order_by(EmployeeAssignment.id.asc())
        .all()
    )

    added = 0
    for employee_assignment in candidates:
        if len(current) + added >= desired_count:
            break

        employee = employee_assignment.employee
        if employee is None or not employee.is_active:
            continue
        if employee.id in assigned_employee_ids:
            continue
        if _is_unavailable(employee.id, duty_date.duty_date):
            continue

        db.session.add(
            DutyAssignment(
                duty_date_id=duty_date.id,
                employee_id=employee.id,
                employee_assignment_id=employee_assignment.id,
                sort_order=next_sort_order,
                assignment_source="manager",
                assigned_by_user_id=duty_date.created_by_user_id,
            )
        )
        assigned_employee_ids.add(employee.id)
        next_sort_order += 10
        added += 1

    return added


def validate() -> None:
    app = create_app()

    with app.app_context():
        removed = 0
        added = 0

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

                if _is_unavailable(employee.id, duty_date.duty_date):
                    db.session.delete(assignment)
                    removed += 1

            db.session.flush()
            added += _backfill_duty_date(duty_date)
            db.session.flush()

        db.session.commit()

        print(
            "Demo duty validation complete: "
            f"removed {removed} conflicting assignments; "
            f"added {added} available replacements"
        )


if __name__ == "__main__":
    validate()
