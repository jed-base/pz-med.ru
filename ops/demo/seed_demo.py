#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    Announcement,
    AbsenceType,
    ClinicSettings,
    Department,
    DepartmentPositionStaffing,
    DutyAssignment,
    DutyDate,
    DutyType,
    Employee,
    EmployeeAbsence,
    EmployeeAssignment,
    Position,
    Subdivision,
    Task,
    User,
    UserAccessScope,
    VacationPeriod,
    VacationPlan,
)


EMPLOYEES = [
    ("Иванов Иван Иванович", "Заведующий терапевтическим отделением", 0),
    ("Петрова Анна Алексеевна", "Врач-терапевт участковый", 0),
    ("Сидоров Николай Николаевич", "Врач-терапевт участковый", 0),
    ("Кузнецова Мария Сергеевна", "Врач-терапевт участковый", 0),
    ("Смирнова Елена Викторовна", "Медицинская сестра участковая", 0),
    ("Васильев Андрей Павлович", "Врач-терапевт участковый", 0),
    ("Попова Ольга Дмитриевна", "Старшая медицинская сестра", 0),
    ("Михайлов Сергей Александрович", "Медицинский брат участковый", 0),
    ("Новикова Ирина Михайловна", "Заведующий терапевтическим отделением", 1),
    ("Федоров Алексей Олегович", "Врач-терапевт участковый", 1),
    ("Морозова Наталья Игоревна", "Врач-терапевт участковый", 1),
    ("Волков Дмитрий Сергеевич", "Врач-терапевт участковый", 1),
    ("Алексеева Татьяна Романовна", "Медицинская сестра участковая", 1),
    ("Лебедева Екатерина Андреевна", "Медицинская сестра участковая", 1),
    ("Семенов Роман Ильич", "Заведующий хирургическим отделением", 2),
    ("Егорова Полина Максимовна", "Врач-хирург", 2),
    ("Павлов Артем Денисович", "Врач-хирург", 2),
    ("Козлова Юлия Владимировна", "Медицинская сестра", 2),
    ("Степанов Максим Андреевич", "Врач-травматолог-ортопед", 2),
    ("Николаева Светлана Евгеньевна", "Старшая медицинская сестра", 2),
    ("Орлов Павел Михайлович", "Заведующий отделением", 3),
    ("Андреева Виктория Ильинична", "Врач по медицинской профилактике", 3),
    ("Макаров Евгений Олегович", "Врач по медицинской профилактике", 3),
    ("Захарова Дарья Романовна", "Медицинская сестра", 3),
    ("Зайцев Антон Сергеевич", "Фельдшер", 3),
    ("Соловьева Марина Павловна", "Заведующая женской консультацией", 4),
    ("Борисова Кирилла Александровна", "Врач-акушер-гинеколог", 4),
    ("Яковлева Алина Игоревна", "Врач-акушер-гинеколог", 4),
    ("Григорьева Ирина Денисовна", "Акушерка", 4),
    ("Романова Ксения Андреевна", "Акушерка", 4),
    ("Воробьев Олег Николаевич", "Заведующий отделением", 5),
    ("Сергеева Надежда Петровна", "Врач функциональной диагностики", 5),
    ("Ковалев Владислав Игоревич", "Врач функциональной диагностики", 5),
    ("Белова Анастасия Сергеевна", "Медицинская сестра", 5),
    ("Комаров Денис Викторович", "Медицинский брат", 5),
    ("Тарасова Любовь Андреевна", "Заведующая отделением", 6),
    ("Белов Михаил Юрьевич", "Врач-рентгенолог", 6),
    ("Гусева Вера Александровна", "Врач ультразвуковой диагностики", 6),
    ("Киселев Артур Романович", "Рентгенолаборант", 6),
    ("Миронова Инна Олеговна", "Рентгенолаборант", 6),
]

DEPARTMENTS = [
    ("Терапевтическое отделение №1", 0),
    ("Терапевтическое отделение №2", 0),
    ("Хирургическое отделение", 0),
    ("Отделение медицинской профилактики", 1),
    ("Женская консультация", 1),
    ("Отделение функциональной диагностики", 2),
    ("Отделение лучевой диагностики", 2),
]

SUBDIVISIONS = [
    "Поликлиническое подразделение №1",
    "Поликлиническое подразделение №2",
    "Диагностическое подразделение",
]

HEAD_EMPLOYEE_INDEXES = [0, 8, 14, 20, 25, 30, 35]


def category_for_position(name: str) -> str:
    lower = name.casefold()
    if "сестр" in lower or "брат" in lower or "акушерк" in lower or "рентгенолаборант" in lower:
        return "nurse"
    if "врач" in lower or "фельдшер" in lower or "завед" in lower:
        return "doctor"
    return "other"


def birth_date_for(today: date, offset: int, index: int) -> date:
    target = today + timedelta(days=offset)
    year = 1972 + (index * 3) % 27
    if target.month == 2 and target.day == 29:
        year = 1988
    return date(year, target.month, target.day)


def next_saturday(today: date) -> date:
    delta = (5 - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def seed() -> None:
    app = create_app()
    today = date.today()
    now = datetime.now()

    with app.app_context():
        if User.query.filter_by(username="demo_ivanov").first():
            print("Demo data already exists; nothing to do.")
            return

        clinic = ClinicSettings(
            full_name="Демонстрационная городская поликлиника PZ-Med",
            short_name="Демо-поликлиника PZ-Med",
            address="Демонстрационный адрес",
            application_name="PZ-Med",
            theme="green",
            timezone_name="Europe/Moscow",
            messenger_attachments_enabled=False,
            algorithm_attachments_enabled=False,
        )
        db.session.add(clinic)

        subdivisions = [
            Subdivision(name=name, short_name=name.replace("Поликлиническое ", ""))
            for name in SUBDIVISIONS
        ]
        db.session.add_all(subdivisions)
        db.session.flush()

        departments = []
        for name, subdivision_index in DEPARTMENTS:
            department = Department(
                name=name,
                short_name=name,
                subdivision_id=subdivisions[subdivision_index].id,
                unit_type="department",
                is_active=True,
            )
            departments.append(department)
        db.session.add_all(departments)
        db.session.flush()

        position_names = sorted({row[1] for row in EMPLOYEES})
        positions = {
            name: Position(name=name, category=category_for_position(name), is_active=True)
            for name in position_names
        }
        db.session.add_all(positions.values())
        db.session.flush()

        employees = []
        assignments = []
        birthday_offsets = [19 + (i * 17) % 300 for i in range(len(EMPLOYEES))]
        birthday_offsets[1] = 7  # Петрова А.А. всегда через 7 дней от текущей даты.
        birthday_offsets[2] = 12
        birthday_offsets[4] = 21
        birthday_offsets[6] = 34

        for index, (full_name, position_name, department_index) in enumerate(EMPLOYEES):
            employee = Employee(
                full_name=full_name,
                birth_date=birth_date_for(today, birthday_offsets[index], index),
                personnel_number=f"DEMO-{index + 1:03d}",
                email=f"employee{index + 1:02d}@demo.pz-med.local",
                is_active=True,
            )
            employees.append(employee)
            db.session.add(employee)
            db.session.flush()

            department = departments[department_index]
            position = positions[position_name]
            if position not in department.positions:
                department.positions.append(position)

            assignment = EmployeeAssignment(
                employee_id=employee.id,
                scope_type="department",
                subdivision_id=department.subdivision_id,
                department_id=department.id,
                position_id=position.id,
                rate=Decimal("1.00"),
                employment_type="primary",
                is_primary=True,
                start_date=today - timedelta(days=900),
                is_active=True,
            )
            assignments.append(assignment)
            db.session.add(assignment)

        db.session.flush()

        users = []
        for index, employee in enumerate(employees):
            user = User(
                employee_id=employee.id,
                username="demo_ivanov" if index == 0 else f"demo_user_{index + 1:02d}",
                password_hash="!",
                role="department_manager" if index == 0 else "employee",
                is_active=True,
                must_change_password=False,
                login_count=4 + (index % 9),
                last_login_at=now - timedelta(hours=index % 18),
            )
            users.append(user)
            db.session.add(user)

        system_user = User(
            username="demo_system_internal",
            password_hash="!",
            role="system_admin",
            is_active=True,
            must_change_password=False,
        )
        db.session.add(system_user)
        db.session.flush()

        for department_index, employee_index in enumerate(HEAD_EMPLOYEE_INDEXES):
            department = departments[department_index]
            employee = employees[employee_index]
            department.head_employee_id = employee.id
            department.head_rights_position_id = assignments[employee_index].position_id

        db.session.add(
            UserAccessScope(
                user_id=users[0].id,
                scope_type="department",
                department_id=departments[0].id,
                is_active=True,
            )
        )

        # Плановая численность по каждой должности чуть выше фактически занятой.
        for department in departments:
            counts = Counter(
                assignment.position_id
                for assignment in assignments
                if assignment.department_id == department.id
            )
            for position_id, count in counts.items():
                db.session.add(
                    DepartmentPositionStaffing(
                        department_id=department.id,
                        position_id=position_id,
                        planned_rate=Decimal(str(count + 0.5)),
                    )
                )

        # У каждого сотрудника: три согласованных периода по 14 календарных дней.
        for index, employee in enumerate(employees):
            plan = VacationPlan(
                employee_id=employee.id,
                year=today.year,
                status="approved",
                approved_at=now - timedelta(days=20),
                approved_by_user_id=system_user.id,
            )
            db.session.add(plan)
            db.session.flush()
            for sort_order, month in enumerate((2, 6, 10), start=1):
                start = date(today.year, month, 2 + (index % 10))
                db.session.add(
                    VacationPeriod(
                        plan_id=plan.id,
                        period_type="approved",
                        start_date=start,
                        days_count=14,
                        end_date=start + timedelta(days=13),
                        sort_order=sort_order,
                    )
                )

        absence_types = {
            "Отпуск": AbsenceType(name="Отпуск", code="О", color="#4f8fe8", include_in_timesheet=True),
            "Больничный": AbsenceType(name="Больничный", code="Б", color="#d86b6b", include_in_timesheet=True),
            "Обучение": AbsenceType(name="Обучение", code="ПК", color="#8f7bd8", include_in_timesheet=True),
        }
        db.session.add_all(absence_types.values())
        db.session.flush()

        current_absences = [
            (3, "Больничный", -2, 4, "Временная нетрудоспособность"),
            (4, "Отпуск", -3, 10, "Ежегодный оплачиваемый отпуск"),
            (7, "Обучение", 0, 2, "Повышение квалификации"),
            (18, "Отпуск", 0, 13, "Ежегодный оплачиваемый отпуск"),
        ]
        for employee_number, type_name, start_offset, end_offset, notes in current_absences:
            db.session.add(
                EmployeeAbsence(
                    employee_id=employees[employee_number - 1].id,
                    absence_type_id=absence_types[type_name].id,
                    start_date=today + timedelta(days=start_offset),
                    end_date=today + timedelta(days=end_offset),
                    status="confirmed",
                    notes=notes,
                    created_by_user_id=system_user.id,
                )
            )

        announcements = [
            ("Совещание заведующих отделениями", "В четверг в 14:30 состоится организационное совещание. Просьба подготовить краткую информацию по текущим задачам.", 1),
            ("Обновлены внутренние алгоритмы", "В разделе «Алгоритмы» опубликована новая версия порядка маршрутизации пациентов на диагностические исследования.", 3),
            ("График дежурств", "Открыта запись на дежурства следующего месяца. Руководителям необходимо проверить свободные даты.", 5),
        ]
        for title, text_value, age_days in announcements:
            db.session.add(
                Announcement(
                    title=title,
                    text=text_value,
                    is_active=True,
                    expires_on=today + timedelta(days=30),
                    show_to_all=True,
                    source_type="clinic",
                    source_name="Демо-поликлиника PZ-Med",
                    author_name="Администрация",
                    created_at=now - timedelta(days=age_days),
                )
            )

        task_rows = [
            ("Проверить сведения по отчёту за неделю", 1, 2, 0, "in_progress", "high"),
            ("Согласовать график дежурств отделения", 1, 7, 1, "new", "normal"),
            ("Подготовить информацию к совещанию заведующих", 9, 1, 2, "in_progress", "normal"),
            ("Проверить актуальность локального алгоритма", 1, 1, 5, "new", "normal"),
            ("Уточнить список сотрудников на обучение", 1, 5, 7, "new", "low"),
        ]
        for title, author_no, assignee_no, due_offset, status, priority in task_rows:
            db.session.add(
                Task(
                    title=title,
                    description="Демонстрационная задача PZ-Med.",
                    author_user_id=users[author_no - 1].id,
                    assignee_user_id=users[assignee_no - 1].id,
                    assignee_employee_id=employees[assignee_no - 1].id,
                    status=status,
                    priority=priority,
                    due_at=datetime.combine(today + timedelta(days=due_offset), time(17, 0)),
                    created_at=now - timedelta(days=2),
                )
            )

        duty_type = DutyType(
            name="Дежурство выходного дня",
            description="Демонстрационный график дежурств",
            scope_level="department",
            owner_subdivision_id=subdivisions[0].id,
            owner_department_id=departments[0].id,
            all_positions=True,
            default_people_count=3,
            default_start_time=time(9, 0),
            default_end_time=time(15, 0),
            default_time_distribution_mode="shared",
            allow_self_signup=True,
            allow_self_cancel=True,
            allow_manager_assignment=True,
            created_by_user_id=users[0].id,
            is_active=True,
        )
        db.session.add(duty_type)
        db.session.flush()

        first_duty = next_saturday(today)
        participant_sets = ((1, 2, 5), (3, 6, 7), (1, 4, 8))
        for week, participant_numbers in enumerate(participant_sets):
            duty_date = DutyDate(
                duty_type_id=duty_type.id,
                duty_date=first_duty + timedelta(days=7 * week),
                responsible_department_id=departments[0].id,
                people_count=4,
                start_time=time(9, 0),
                end_time=time(15, 0),
                time_distribution_mode="shared",
                allow_self_signup=True,
                is_active=True,
                created_by_user_id=users[0].id,
            )
            db.session.add(duty_date)
            db.session.flush()
            for order, employee_number in enumerate(participant_numbers, start=1):
                idx = employee_number - 1
                db.session.add(
                    DutyAssignment(
                        duty_date_id=duty_date.id,
                        employee_id=employees[idx].id,
                        employee_assignment_id=assignments[idx].id,
                        sort_order=order * 10,
                        assignment_source="manager",
                        assigned_by_user_id=users[0].id,
                    )
                )

        db.session.commit()
        print("Demo database seeded successfully")
        print(f"Employees: {len(employees)}")
        print(f"Vacation periods: {len(employees) * 3}")
        print("Auto-login user: demo_ivanov / Иванов И.И.")
        print(f"Petrova birthday: {today + timedelta(days=7)}")


if __name__ == "__main__":
    seed()
