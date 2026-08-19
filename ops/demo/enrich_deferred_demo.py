#!/usr/bin/env python3
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    DeferredEntry,
    DeferredEntryHistory,
    DeferredService,
    Subdivision,
    User,
)
from app.modules.deferred.service import get_origin_for_user


DEMO_ENTRIES = (
    {
        "service_name": "Консультация эндокринолога",
        "short_name": "Консультация эндокринолога",
        "responsible_subdivision": "Поликлиническое подразделение №1",
        "indications": (
            "Консультация эндокринолога при необходимости уточнения "
            "тактики обследования и лечения."
        ),
        "attention_days": 5,
        "department_escalation_days": 10,
        "subdivision_escalation_days": 20,
        "clinic_escalation_days": 30,
        "card_number": "563214",
        "phone": "+7 (900) 000-18-42",
        "comment": (
            "Повышение HbA1c по последнему анализу. Нужна плановая "
            "консультация эндокринолога для коррекции терапии."
        ),
        "desired_offset_days": 7,
        "priority": "normal",
        "status": "waiting",
        "waiting_days": 2,
        "created_time": time(10, 15),
        "history": (
            ("created", "Создана запись ожидания на консультацию эндокринолога."),
        ),
    },
    {
        "service_name": "ФГДС",
        "short_name": "ФГДС",
        "responsible_subdivision": "Диагностическое подразделение",
        "indications": (
            "Эзофагогастродуоденоскопия по клиническим показаниям "
            "и при плановом обследовании."
        ),
        "attention_days": 3,
        "department_escalation_days": 7,
        "subdivision_escalation_days": 14,
        "clinic_escalation_days": 30,
        "card_number": "771305",
        "phone": "+7 (900) 000-22-14",
        "comment": (
            "Плановая ФГДС по направлению терапевта. Свободных слотов "
            "на ближайшие даты пока нет."
        ),
        "desired_offset_days": -1,
        "priority": "priority",
        "status": "action_required",
        "waiting_days": 12,
        "created_time": time(9, 40),
        "history": (
            ("created", "Создана запись ожидания на ФГДС."),
            (
                "no_slots",
                "Слотов нет: на ближайшие доступные даты свободных мест нет.",
            ),
            (
                "status_changed",
                "Статус изменён на «Требует действия».",
            ),
        ),
    },
    {
        "service_name": "УЗИ сосудов шеи",
        "short_name": "УЗИ сосудов шеи",
        "responsible_subdivision": "Диагностическое подразделение",
        "indications": (
            "Ультразвуковое исследование брахиоцефальных сосудов "
            "по направлению лечащего врача."
        ),
        "attention_days": 5,
        "department_escalation_days": 10,
        "subdivision_escalation_days": 20,
        "clinic_escalation_days": 30,
        "card_number": "884126",
        "phone": "+7 (900) 000-31-67",
        "comment": (
            "УЗИ сосудов шеи по направлению невролога. Первый звонок "
            "пациенту без ответа, требуется повторный контакт."
        ),
        "desired_offset_days": 3,
        "priority": "normal",
        "status": "contacting",
        "waiting_days": 6,
        "created_time": time(14, 20),
        "history": (
            ("created", "Создана запись ожидания на УЗИ сосудов шеи."),
            (
                "no_answer",
                "Не дозвонились: первый звонок без ответа, запланирован повторный контакт.",
            ),
            (
                "status_changed",
                "Статус изменён на «Связываемся с пациентом».",
            ),
        ),
    },
)


def _ensure_service(spec: dict) -> DeferredService:
    service = DeferredService.query.filter_by(name=spec["service_name"]).first()
    if service is None:
        service = DeferredService(name=spec["service_name"])
        db.session.add(service)

    subdivision = (
        Subdivision.query
        .filter_by(name=spec["responsible_subdivision"])
        .first()
    )

    service.short_name = spec["short_name"]
    service.responsible_subdivision_id = subdivision.id if subdivision else None
    service.indications = spec["indications"]
    service.attention_days = spec["attention_days"]
    service.department_escalation_days = spec["department_escalation_days"]
    service.subdivision_escalation_days = spec["subdivision_escalation_days"]
    service.clinic_escalation_days = spec["clinic_escalation_days"]
    service.is_active = True
    db.session.flush()
    return service


def _ensure_history(
    *,
    entry: DeferredEntry,
    owner: User,
    event_type: str,
    message: str,
    created_at: datetime,
) -> None:
    row = (
        DeferredEntryHistory.query
        .filter_by(
            entry_id=entry.id,
            event_type=event_type,
            message=message,
        )
        .first()
    )
    if row is None:
        row = DeferredEntryHistory(
            entry_id=entry.id,
            actor_user_id=owner.id,
            event_type=event_type,
            message=message,
        )
        db.session.add(row)
    row.created_at = created_at


def _ensure_entry(
    *,
    owner: User,
    service: DeferredService,
    spec: dict,
    today: date,
) -> bool:
    entry = (
        DeferredEntry.query
        .filter_by(
            card_number=spec["card_number"],
            service_id=service.id,
            initiator_user_id=owner.id,
        )
        .first()
    )
    created = entry is None

    subdivision_id, department_id = get_origin_for_user(owner)
    created_at = datetime.combine(
        today - timedelta(days=spec["waiting_days"]),
        spec["created_time"],
    )

    if entry is None:
        entry = DeferredEntry(
            card_number=spec["card_number"],
            service_id=service.id,
            initiator_user_id=owner.id,
        )
        db.session.add(entry)
        db.session.flush()

    entry.phone = spec["phone"]
    entry.comment = spec["comment"]
    entry.responsible_user_id = owner.id
    entry.source_subdivision_id = subdivision_id
    entry.source_department_id = department_id
    entry.desired_date = today + timedelta(days=spec["desired_offset_days"])
    entry.priority = spec["priority"]
    entry.status = spec["status"]
    entry.booked_date = None
    entry.completion_comment = None
    entry.completed_at = None
    entry.created_at = created_at

    db.session.flush()

    for index, (event_type, message) in enumerate(spec["history"]):
        _ensure_history(
            entry=entry,
            owner=owner,
            event_type=event_type,
            message=message,
            created_at=created_at + timedelta(hours=index * 2),
        )

    return created


def enrich() -> None:
    app = create_app()
    today = date.today()

    with app.app_context():
        owner = User.query.filter_by(username="demo_ivanov").first()
        if owner is None:
            raise RuntimeError("Deferred demo: demo_ivanov not found")

        created_entries = 0
        for spec in DEMO_ENTRIES:
            service = _ensure_service(spec)
            created_entries += int(
                _ensure_entry(
                    owner=owner,
                    service=service,
                    spec=spec,
                    today=today,
                )
            )

        db.session.commit()

        print(
            "Demo deferred entries ready: "
            "3 services, 3 active records in different statuses "
            f"({created_entries} newly created)"
        )


if __name__ == "__main__":
    enrich()
