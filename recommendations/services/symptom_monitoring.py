from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import (
    BabySymptom,
    GeneratedSymptomChecklist,
    GeneratedSymptomChecklistItem,
    MommySymptom,
    RiskDefinition,
    RiskDefinitionBabySymptom,
    RiskDefinitionMommySymptom,
    SYMPTOM_CHECKLIST_BABY,
    SYMPTOM_CHECKLIST_MOMMY,
    SYMPTOM_STATUS_NOT_REPORTED,
    SYMPTOM_STATUS_REPORTED,
    SymptomChecklistResponse,
    SymptomChecklistResponseItem,
)


ALGORITHM_VERSION = "risk-priority-v1"
CHECKLIST_TYPES = {SYMPTOM_CHECKLIST_MOMMY, SYMPTOM_CHECKLIST_BABY}


class InvalidSymptomChecklist(ValueError):
    pass


def get_user_timezone(user) -> ZoneInfo:
    timezone_name = user.timezone or settings.TIME_ZONE
    try:
        return ZoneInfo(timezone_name)
    except (TypeError, ZoneInfoNotFoundError):
        return ZoneInfo(settings.TIME_ZONE)


def local_date_for_user(user, value=None):
    value = value or timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, get_user_timezone(user))
    return timezone.localtime(value, get_user_timezone(user)).date()


def local_day_bounds(user, local_date):
    user_timezone = get_user_timezone(user)
    start = timezone.make_aware(datetime.combine(local_date, time.min), user_timezone)
    end = timezone.make_aware(
        datetime.combine(local_date + timedelta(days=1), time.min),
        user_timezone,
    )
    return start, end


def _configuration(checklist_type):
    if checklist_type == SYMPTOM_CHECKLIST_MOMMY:
        return MommySymptom, RiskDefinitionMommySymptom
    if checklist_type == SYMPTOM_CHECKLIST_BABY:
        return BabySymptom, RiskDefinitionBabySymptom
    raise ValueError(f"Unsupported symptom checklist type: {checklist_type}")


def generate_symptoms(user, checklist_type):
    """Run the existing risk-priority algorithm and return up to five symptoms."""
    _symptom_model, link_model = _configuration(checklist_type)
    risks, _integrated_risk = user.calculate_risk_factors()
    risk_list = list(risks.items())
    risk_list.sort(key=lambda item: item[1]["risk_value"], reverse=True)
    risk_list.sort(key=lambda item: item[1]["priority"])

    symptoms = []
    seen_codes = set()
    for risk_name, _risk_data in risk_list:
        risk = RiskDefinition.objects.get(name=risk_name)
        links = (
            link_model.objects.select_related("symptom")
            .filter(risk_definition=risk)
            .order_by("pk")
        )
        for link in links:
            symptom = link.symptom
            if symptom.code in seen_codes:
                continue
            seen_codes.add(symptom.code)
            symptoms.append(symptom)
            if len(symptoms) == 5:
                return symptoms
    return symptoms


def get_or_create_daily_checklist(user, checklist_type, *, generated_at=None):
    generated_at = generated_at or timezone.now()
    local_date = local_date_for_user(user, generated_at)
    lookup = {
        "user": user,
        "checklist_type": checklist_type,
        "local_date": local_date,
    }

    existing = GeneratedSymptomChecklist.objects.filter(**lookup).first()
    if existing:
        return existing, False

    symptoms = generate_symptoms(user, checklist_type)
    try:
        with transaction.atomic():
            checklist = GeneratedSymptomChecklist.objects.create(
                **lookup,
                algorithm_version=ALGORITHM_VERSION,
            )
            GeneratedSymptomChecklistItem.objects.bulk_create(
                [
                    GeneratedSymptomChecklistItem(
                        checklist=checklist,
                        symptom_id_snapshot=symptom.pk,
                        symptom_code=symptom.code,
                        display_name=symptom.name,
                        position=position,
                    )
                    for position, symptom in enumerate(symptoms, start=1)
                ]
            )
    except IntegrityError:
        checklist = GeneratedSymptomChecklist.objects.get(**lookup)
        return checklist, False
    return checklist, True


def record_response(
    *,
    user,
    checklist_type,
    recorded_at,
    selected_symptoms,
    checklist_id=None,
):
    if checklist_type not in CHECKLIST_TYPES:
        raise ValueError(f"Unsupported symptom checklist type: {checklist_type}")

    local_date = local_date_for_user(user, recorded_at)
    checklist = None
    if checklist_id:
        checklist = GeneratedSymptomChecklist.objects.filter(
            pk=checklist_id,
            user=user,
            checklist_type=checklist_type,
        ).first()
        if checklist is None:
            raise InvalidSymptomChecklist(
                "Checklist does not exist or does not belong to this user and type."
            )
        if checklist.local_date != local_date:
            raise InvalidSymptomChecklist(
                "Checklist date does not match the submitted response date."
            )
    else:
        checklist = GeneratedSymptomChecklist.objects.filter(
            user=user,
            checklist_type=checklist_type,
            local_date=local_date,
        ).first()

    selected_symptoms = list(selected_symptoms)
    selected_codes = {symptom.code for symptom in selected_symptoms}
    response = SymptomChecklistResponse.objects.create(
        checklist=checklist,
        user=user,
        checklist_type=checklist_type,
        local_date=local_date,
        recorded_at=recorded_at,
        reported_symptom_ids=sorted(symptom.pk for symptom in selected_symptoms),
        reported_symptom_codes=sorted(selected_codes),
    )

    if checklist is None:
        return response

    checklist_items = list(checklist.items.all())
    response_items = []
    for item in checklist_items:
        item.status = (
            SYMPTOM_STATUS_REPORTED
            if item.symptom_code in selected_codes
            else SYMPTOM_STATUS_NOT_REPORTED
        )
        response_items.append(
            SymptomChecklistResponseItem(
                response=response,
                symptom_code=item.symptom_code,
                display_name=item.display_name,
                position=item.position,
                status=item.status,
            )
        )

    if checklist_items:
        GeneratedSymptomChecklistItem.objects.bulk_update(checklist_items, ["status"])
        SymptomChecklistResponseItem.objects.bulk_create(response_items)
    return response
