#!/usr/bin/env python3
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    Algorithm,
    AssignmentSchedulePeriod,
    Conversation,
    ConversationParticipant,
    Department,
    DutyAssignment,
    DutyDate,
    DutyType,
    Employee,
    EmployeeAbsence,
    EmployeeAssignment,
    Notification,
    PersonalMessage,
    TableReportCell,
    TableReportColumnDefinition,
    TableReportDefinition,
    TableReportPeriod,
    TableReportRowDefinition,
    TableReportSubmission,
    Timesheet,
    TimesheetDayValue,
    TimesheetRow,
    User,
    WorkSchedule,
    WorkScheduleDay,
)


MARKER_TITLE = "Порядок работы при отсутствии свободной записи"
SCHEDULE_NAME = "Пятидневная рабочая неделя — 39 часов"


def _employee(personnel_number: str) -> Employee:
    employee = Employee.query.filter_by(
        personnel_number=personnel_number,
    ).first()
    if employee is None:
        raise RuntimeError(
            f"Demo showcase: employee {personnel_number} not found"
        )
    return employee


def _user_for_employee(employee: Employee) -> User:
    user = User.query.filter_by(employee_id=employee.id).first()
    if user is None:
        raise RuntimeError(
            f"Demo showcase: user for {employee.personnel_number} not found"
        )
    return user


def _assignment_for_employee(employee: Employee) -> EmployeeAssignment:
    assignment = (
        EmployeeAssignment.query
        .filter_by(employee_id=employee.id, is_active=True)
        .order_by(
            EmployeeAssignment.is_primary.desc(),
            EmployeeAssignment.id.asc(),
        )
        .first()
    )
    if assignment is None:
        raise RuntimeError(
            f"Demo showcase: assignment for {employee.personnel_number} not found"
        )
    return assignment


def _next_saturday(today: date) -> date:
    delta = (5 - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return (
        date(year, month, 1),
        date(year, month, monthrange(year, month)[1]),
    )


def _previous_month(today: date) -> tuple[int, int]:
    previous_last = today.replace(day=1) - timedelta(days=1)
    return previous_last.year, previous_last.month


def _seed_algorithms(*, creator: User, now: datetime) -> int:
    rows = (
        (
            "Порядок работы при отсутствии свободной записи",
            """
<p><strong>Демонстрационный внутренний алгоритм.</strong></p>
<ol>
  <li>Если свободного слота на исследование или консультацию нет, зарегистрировать запрос в журнале отложенной записи.</li>
  <li>Указать услугу, приоритет, желаемый срок и уровень очереди: сотрудник, отделение, подразделение или учреждение.</li>
  <li>При появлении слота связаться с пациентом и зафиксировать результат работы с записью.</li>
  <li>После фактической записи перевести обращение в завершённый статус.</li>
</ol>
<p>Алгоритм предназначен только для демонстрации возможностей PZ-Med.</p>
""".strip(),
            2,
        ),
        (
            "Передача дел на период отсутствия сотрудника",
            """
<p><strong>Демонстрационный организационный алгоритм.</strong></p>
<ol>
  <li>До начала планового отсутствия проверить незавершённые задачи и отчёты.</li>
  <li>Передать срочные вопросы назначенному сотруднику и при необходимости предоставить ему доступ.</li>
  <li>Зафиксировать важные сроки и ожидаемые результаты в задачах PZ-Med.</li>
  <li>После возвращения проверить исполнение переданных поручений.</li>
</ol>
<p>Конкретный порядок организация настраивает самостоятельно.</p>
""".strip(),
            9,
        ),
    )

    for title, content, age_days in rows:
        db.session.add(
            Algorithm(
                title=title,
                content=content,
                is_active=True,
                show_to_all=True,
                created_by_user_id=creator.id,
                created_at=now - timedelta(days=age_days),
                updated_at=now - timedelta(days=max(age_days - 1, 0)),
            )
        )
    return len(rows)


def _new_conversation(
    *,
    users: list[User],
    now: datetime,
    messages: list[tuple[int, str, timedelta]],
    title: str | None = None,
) -> Conversation:
    is_group = len(users) > 2
    if is_group:
        pair_key = None
        conversation_type = Conversation.TYPE_GROUP
    else:
        ids = sorted((users[0].id, users[1].id))
        pair_key = f"{ids[0]}:{ids[1]}"
        conversation_type = Conversation.TYPE_DIRECT

    conversation = Conversation(
        conversation_type=conversation_type,
        pair_key=pair_key,
        title=title,
        created_by_user_id=users[0].id,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    db.session.add(conversation)
    db.session.flush()

    participants: dict[int, ConversationParticipant] = {}
    for user in users:
        participant = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=user.id,
            joined_at=conversation.created_at,
        )
        participants[user.id] = participant
        db.session.add(participant)

    db.session.flush()

    created_messages: list[PersonalMessage] = []
    for sender_index, body, age in messages:
        message = PersonalMessage(
            conversation_id=conversation.id,
            sender_user_id=users[sender_index].id,
            body=body,
            created_at=now - age,
        )
        db.session.add(message)
        db.session.flush()
        created_messages.append(message)

    if created_messages:
        conversation.last_message_at = created_messages[-1].created_at
        conversation.updated_at = created_messages[-1].created_at

    demo_participant = participants.get(users[0].id)
    if demo_participant is not None and len(created_messages) >= 2:
        demo_participant.last_read_message_id = created_messages[-2].id

    return conversation


def _seed_messages(*, now: datetime) -> int:
    demo = _user_for_employee(_employee("DEMO-001"))
    petrova = _user_for_employee(_employee("DEMO-002"))
    second_head = _user_for_employee(_employee("DEMO-009"))
    surgery_head = _user_for_employee(_employee("DEMO-015"))

    _new_conversation(
        users=[demo, petrova],
        now=now,
        messages=[
            (
                1,
                "Иван Иванович, данные по еженедельному отчёту обновила. "
                "По двум показателям добавила комментарии.",
                timedelta(hours=5, minutes=15),
            ),
            (
                0,
                "Спасибо. Вижу заполнение. Перед отправкой свода ещё раз "
                "проверьте фактические значения за вчера.",
                timedelta(hours=4, minutes=48),
            ),
            (
                1,
                "Проверила, всё актуально. Можно включать в свод.",
                timedelta(minutes=42),
            ),
        ],
    )

    _new_conversation(
        users=[demo, second_head],
        now=now,
        messages=[
            (
                1,
                "Добрый день! На следующую субботу у нас остаётся одно "
                "свободное место в графике дежурств.",
                timedelta(days=1, hours=2),
            ),
            (
                0,
                "Добрый день. Спасибо, посмотрю сотрудников и дам ответ "
                "сегодня до конца дня.",
                timedelta(days=1, hours=1, minutes=30),
            ),
            (
                1,
                "Хорошо, тогда пока оставляю место свободным.",
                timedelta(hours=3, minutes=5),
            ),
        ],
    )

    _new_conversation(
        users=[demo, second_head, surgery_head],
        title="Руководители подразделения №1",
        now=now,
        messages=[
            (
                0,
                "Коллеги, к четвергу прошу актуализировать оперативную "
                "информацию по отделениям.",
                timedelta(days=2, hours=1),
            ),
            (
                1,
                "По терапевтическому отделению №2 данные внесём сегодня.",
                timedelta(days=1, hours=23),
            ),
            (
                2,
                "По хирургическому отделению тоже подготовим.",
                timedelta(days=1, hours=22, minutes=40),
            ),
            (
                1,
                "Иван Иванович, свою часть уже заполнили.",
                timedelta(hours=1, minutes=10),
            ),
        ],
    )

    return 3


def _extend_duties(*, today: date, creator: User) -> int:
    duty_type = DutyType.query.filter_by(
        name="Дежурство выходного дня",
    ).first()
    if duty_type is None:
        raise RuntimeError("Demo showcase: duty type not found")

    department = db.session.get(
        Department,
        duty_type.owner_department_id,
    )
    if department is None:
        raise RuntimeError("Demo showcase: duty department not found")

    participant_sets = (
        ("DEMO-002", "DEMO-006", "DEMO-008"),
        ("DEMO-003", "DEMO-005", "DEMO-007"),
        ("DEMO-001", "DEMO-004", "DEMO-006"),
    )
    first_duty = _next_saturday(today)
    created = 0

    for extra_week, personnel_numbers in enumerate(
        participant_sets,
        start=3,
    ):
        duty_day = first_duty + timedelta(days=7 * extra_week)
        existing = DutyDate.query.filter_by(
            duty_type_id=duty_type.id,
            duty_date=duty_day,
        ).first()
        if existing is not None:
            continue

        duty_date = DutyDate(
            duty_type_id=duty_type.id,
            duty_date=duty_day,
            responsible_department_id=department.id,
            people_count=4,
            start_time=time(9, 0),
            end_time=time(15, 0),
            time_distribution_mode="shared",
            allow_self_signup=True,
            is_active=True,
            created_by_user_id=creator.id,
        )
        db.session.add(duty_date)
        db.session.flush()

        for order, personnel_number in enumerate(
            personnel_numbers,
            start=1,
        ):
            employee = _employee(personnel_number)
            assignment = _assignment_for_employee(employee)
            db.session.add(
                DutyAssignment(
                    duty_date_id=duty_date.id,
                    employee_id=employee.id,
                    employee_assignment_id=assignment.id,
                    sort_order=order * 10,
                    assignment_source="manager",
                    assigned_by_user_id=creator.id,
                )
            )
        created += 1

    return created


def _seed_work_schedule(
    *,
    today: date,
) -> tuple[WorkSchedule, list[EmployeeAssignment]]:
    department = Department.query.filter_by(
        name="Терапевтическое отделение №1",
    ).first()
    if department is None:
        raise RuntimeError("Demo showcase: department not found")

    schedule = WorkSchedule(
        name=SCHEDULE_NAME,
        weekly_hours=Decimal("39.00"),
        is_default=True,
        is_active=True,
        description=(
            "Демонстрационный базовый график для сотрудников "
            "терапевтического отделения."
        ),
    )
    db.session.add(schedule)
    db.session.flush()

    for weekday in range(7):
        is_working = weekday < 5
        db.session.add(
            WorkScheduleDay(
                schedule_id=schedule.id,
                weekday=weekday,
                is_working_day=is_working,
                planned_hours=(
                    Decimal("7.80")
                    if is_working
                    else Decimal("0.00")
                ),
            )
        )

    assignments = (
        EmployeeAssignment.query
        .filter_by(
            department_id=department.id,
            is_active=True,
        )
        .order_by(EmployeeAssignment.id.asc())
        .all()
    )

    period_start = date(today.year, 1, 1)
    for assignment in assignments:
        db.session.add(
            AssignmentSchedulePeriod(
                assignment_id=assignment.id,
                schedule_id=schedule.id,
                start_date=period_start,
                end_date=None,
            )
        )

    return schedule, assignments


def _absence_for_day(
    employee_id: int,
    work_date: date,
) -> EmployeeAbsence | None:
    return (
        EmployeeAbsence.query
        .filter(
            EmployeeAbsence.employee_id == employee_id,
            EmployeeAbsence.status == "confirmed",
            EmployeeAbsence.start_date <= work_date,
            EmployeeAbsence.end_date >= work_date,
        )
        .order_by(EmployeeAbsence.id.asc())
        .first()
    )


def _seed_timesheet_for_month(
    *,
    department: Department,
    assignments: list[EmployeeAssignment],
    creator: User,
    year: int,
    month: int,
    status: str,
    today: date,
    now: datetime,
) -> Timesheet:
    approved = status in {"approved", "closed"}
    timesheet = Timesheet(
        department_id=department.id,
        year=year,
        month=month,
        status=status,
        created_by_user_id=creator.id,
        updated_by_user_id=creator.id,
        approved_by_user_id=(creator.id if approved else None),
        approved_at=(now - timedelta(days=3) if approved else None),
    )
    db.session.add(timesheet)
    db.session.flush()

    month_start, month_end = _month_bounds(year, month)
    effective_end = month_end
    if (year, month) == (today.year, today.month):
        effective_end = min(today, month_end)

    for row_order, assignment in enumerate(assignments, start=1):
        employee = assignment.employee
        position = assignment.position
        row = TimesheetRow(
            timesheet_id=timesheet.id,
            assignment_id=assignment.id,
            employee_id=employee.id,
            employee_name_snapshot=employee.full_name,
            position_name_snapshot=position.name,
            department_name_snapshot=department.name,
            rate_snapshot=assignment.rate,
            employment_type_snapshot=assignment.employment_type,
            assignment_start_date_snapshot=assignment.start_date,
            assignment_end_date_snapshot=assignment.end_date,
            row_order=row_order * 10,
        )
        db.session.add(row)
        db.session.flush()

        current = month_start
        while current <= effective_end:
            absence = _absence_for_day(employee.id, current)
            if absence is not None and current.weekday() < 5:
                db.session.add(
                    TimesheetDayValue(
                        timesheet_row_id=row.id,
                        work_date=current,
                        code=(
                            absence.absence_type.code
                            if absence.absence_type
                            else "ОТ"
                        ),
                        hours=None,
                        source_type="absence",
                        source_absence_id=absence.id,
                        is_manual=False,
                        updated_by_user_id=creator.id,
                    )
                )
            elif current.weekday() < 5:
                db.session.add(
                    TimesheetDayValue(
                        timesheet_row_id=row.id,
                        work_date=current,
                        code="Я",
                        hours=Decimal("7.80"),
                        source_type="schedule",
                        is_manual=False,
                        updated_by_user_id=creator.id,
                    )
                )
            else:
                db.session.add(
                    TimesheetDayValue(
                        timesheet_row_id=row.id,
                        work_date=current,
                        code="В",
                        hours=Decimal("0.00"),
                        source_type="schedule",
                        is_manual=False,
                        updated_by_user_id=creator.id,
                    )
                )
            current += timedelta(days=1)

    return timesheet


def _seed_timesheets(
    *,
    today: date,
    now: datetime,
    creator: User,
    assignments: list[EmployeeAssignment],
) -> int:
    department = Department.query.filter_by(
        name="Терапевтическое отделение №1",
    ).first()
    if department is None:
        raise RuntimeError("Demo showcase: department not found")

    prev_year, prev_month = _previous_month(today)
    _seed_timesheet_for_month(
        department=department,
        assignments=assignments,
        creator=creator,
        year=prev_year,
        month=prev_month,
        status="approved",
        today=today,
        now=now,
    )
    _seed_timesheet_for_month(
        department=department,
        assignments=assignments,
        creator=creator,
        year=today.year,
        month=today.month,
        status="draft",
        today=today,
        now=now,
    )
    return 2


def _add_report_period(
    *,
    report: TableReportDefinition,
    rows: list[TableReportRowDefinition],
    columns: list[TableReportColumnDefinition],
    target_employees: list[Employee],
    creator: User,
    period_start: date,
    period_end: date,
    period_title: str,
    period_status: str,
    current: bool,
    now: datetime,
) -> None:
    period = TableReportPeriod(
        report_id=report.id,
        title=period_title,
        period_start=period_start,
        period_end=period_end,
        status=period_status,
        created_by_user_id=creator.id,
    )
    db.session.add(period)
    db.session.flush()

    current_statuses = (
        "accepted",
        "submitted",
        "returned",
        "draft",
        "accepted",
        "submitted",
    )

    fact_sets = (
        ((92, 88, "Плановая динамика"), (28, 31, ""), (24, 22, "")),
        ((86, 91, ""), (24, 25, ""), (20, 23, "Дополнительные направления")),
        ((90, 79, "Два дня обучения"), (26, 22, ""), (22, 18, "")),
        ((88, 63, "Заполнение продолжается"), (25, 17, ""), (21, 14, "")),
        ((84, 87, ""), (22, 24, ""), (18, 19, "")),
        ((91, 89, ""), (27, 28, ""), (23, 24, "")),
    )

    for index, (employee, row_values) in enumerate(
        zip(target_employees, fact_sets)
    ):
        status = current_statuses[index] if current else "accepted"
        target_user = _user_for_employee(employee)
        submission = TableReportSubmission(
            period_id=period.id,
            target_type="employee",
            target_id=employee.id,
            target_key=f"employee:{employee.id}",
            target_name=employee.full_name,
            status=status,
            submitted_at=(
                now - timedelta(hours=3)
                if status != "draft"
                else None
            ),
            submitted_by_user_id=(
                target_user.id
                if status != "draft"
                else None
            ),
            reviewed_by_user_id=(
                creator.id
                if status in {"accepted", "returned"}
                else None
            ),
            accepted_at=(
                now - timedelta(hours=1)
                if status == "accepted"
                else None
            ),
            returned_comment=(
                "Проверьте фактическое число посещений за последние два дня."
                if status == "returned"
                else None
            ),
        )
        db.session.add(submission)
        db.session.flush()

        for row, (plan, fact, comment) in zip(rows, row_values):
            if not current:
                fact = max(0, fact - 3 + index)
                comment = "" if index % 2 else "Принято без замечаний"
            percent = round((fact / plan) * 100) if plan else 0
            values = (str(plan), str(fact), str(percent), comment)

            for column, value in zip(columns, values):
                if current and status == "draft" and column.data_type == "text":
                    value = ""
                db.session.add(
                    TableReportCell(
                        submission_id=submission.id,
                        row_definition_id=row.id,
                        column_definition_id=column.id,
                        value=value,
                    )
                )


def _seed_table_report(*, today: date, now: datetime, creator: User) -> int:
    report = TableReportDefinition(
        title="Еженедельная оперативная информация по отделению",
        description=(
            "Демонстрационная форма для сбора нескольких показателей "
            "с сотрудников отделения без пересылки Excel-файлов."
        ),
        period_type="month",
        fill_scope="employee",
        layout_mode="simple",
        all_subdivisions=True,
        all_departments=True,
        all_positions=True,
        all_employees=False,
        is_active=True,
        created_by_user_id=creator.id,
    )
    db.session.add(report)
    db.session.flush()

    target_employees = [
        _employee(f"DEMO-{number:03d}")
        for number in range(2, 8)
    ]
    report.employees.extend(target_employees)
    if creator.employee is not None:
        report.responsible_employees.append(creator.employee)
        report.reviewer_employees.append(creator.employee)

    rows = [
        TableReportRowDefinition(
            report_id=report.id,
            title="Посещения пациентов",
            description="Все выполненные посещения за отчётный период.",
            sort_order=10,
            is_active=True,
        ),
        TableReportRowDefinition(
            report_id=report.id,
            title="Диспансерные приёмы",
            description=(
                "Выполненные приёмы в рамках диспансерного наблюдения."
            ),
            sort_order=20,
            is_active=True,
        ),
        TableReportRowDefinition(
            report_id=report.id,
            title="Направления на исследования",
            description=(
                "Выданные направления на диагностические исследования."
            ),
            sort_order=30,
            is_active=True,
        ),
    ]
    db.session.add_all(rows)

    columns = [
        TableReportColumnDefinition(
            report_id=report.id,
            title="План",
            short_title="План",
            data_type="integer",
            unit_name="случ.",
            is_required=True,
            sort_order=10,
            is_active=True,
        ),
        TableReportColumnDefinition(
            report_id=report.id,
            title="Факт",
            short_title="Факт",
            data_type="integer",
            unit_name="случ.",
            is_required=True,
            sort_order=20,
            is_active=True,
        ),
        TableReportColumnDefinition(
            report_id=report.id,
            title="Выполнение",
            short_title="%",
            data_type="percent",
            unit_name="%",
            is_required=True,
            sort_order=30,
            is_active=True,
        ),
        TableReportColumnDefinition(
            report_id=report.id,
            title="Комментарий",
            short_title="Комментарий",
            data_type="text",
            is_required=False,
            sort_order=40,
            is_active=True,
        ),
    ]
    db.session.add_all(columns)
    db.session.flush()

    previous_year, previous_month = _previous_month(today)
    previous_start, previous_end = _month_bounds(
        previous_year,
        previous_month,
    )
    _add_report_period(
        report=report,
        rows=rows,
        columns=columns,
        target_employees=target_employees,
        creator=creator,
        period_start=previous_start,
        period_end=previous_end,
        period_title=f"Оперативная информация — {previous_month:02d}.{previous_year}",
        period_status="closed",
        current=False,
        now=now - timedelta(days=14),
    )

    current_start, current_end = _month_bounds(today.year, today.month)
    _add_report_period(
        report=report,
        rows=rows,
        columns=columns,
        target_employees=target_employees,
        creator=creator,
        period_start=current_start,
        period_end=current_end,
        period_title=f"Оперативная информация — {today.month:02d}.{today.year}",
        period_status="open",
        current=True,
        now=now,
    )

    return 1


def _seed_notifications(*, user: User, now: datetime) -> int:
    rows = (
        (
            "Отчёт ожидает проверки",
            "Один из исполнителей отправил оперативную информацию.",
            "warning",
            "table_report",
            timedelta(minutes=36),
        ),
        (
            "Обновлён график дежурств",
            "В графике выходных дежурств появились новые даты.",
            "info",
            "duty",
            timedelta(hours=2, minutes=20),
        ),
        (
            "Новое сообщение",
            "В рабочем чате есть новое входящее сообщение.",
            "info",
            "message",
            timedelta(hours=4),
        ),
    )

    for title, message, category, source_type, age in rows:
        db.session.add(
            Notification(
                user_id=user.id,
                title=title,
                message=message,
                category=category,
                source_type=source_type,
                is_read=False,
                created_at=now - age,
            )
        )
    return len(rows)


def enrich() -> None:
    app = create_app()
    today = date.today()
    now = datetime.utcnow()

    with app.app_context():
        if Algorithm.query.filter_by(title=MARKER_TITLE).first() is not None:
            print("Demo showcase data already exists; nothing to do.")
            return

        creator = _user_for_employee(_employee("DEMO-001"))

        algorithms = _seed_algorithms(creator=creator, now=now)
        conversations = _seed_messages(now=now)
        duty_dates = _extend_duties(today=today, creator=creator)
        _, assignments = _seed_work_schedule(today=today)
        timesheets = _seed_timesheets(
            today=today,
            now=now,
            creator=creator,
            assignments=assignments,
        )
        reports = _seed_table_report(
            today=today,
            now=now,
            creator=creator,
        )
        notifications = _seed_notifications(user=creator, now=now)

        db.session.commit()

        print(
            "Demo showcase ready: "
            f"{algorithms} algorithms, "
            f"{conversations} conversations, "
            f"{duty_dates} extra duty dates, "
            f"{timesheets} timesheets, "
            f"{reports} table report, "
            f"{notifications} notifications."
        )


if __name__ == "__main__":
    enrich()
