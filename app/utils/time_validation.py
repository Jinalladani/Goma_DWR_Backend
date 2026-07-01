from datetime import date, datetime, time, timezone


def _ensure_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def combine_date_time(work_date, time_value):
    if isinstance(time_value, datetime):
        return _ensure_utc(time_value)

    if isinstance(work_date, str):
        work_date = date.fromisoformat(work_date)

    if isinstance(time_value, time):
        return datetime.combine(work_date, time_value, tzinfo=timezone.utc)

    if isinstance(time_value, str):
        if "T" in time_value:
            return _ensure_utc(datetime.fromisoformat(time_value))

        hour, minute = map(int, time_value.split(":"))
        return datetime.combine(work_date, time(hour=hour, minute=minute), tzinfo=timezone.utc)

    return None


def validate_not_future_datetime(work_date, start_time, end_time):
    today = date.today()
    now = datetime.now(timezone.utc)

    # Ensure start_time and end_time are UTC timezone-aware for comparison
    start_time = _ensure_utc(start_time)
    end_time = _ensure_utc(end_time)

    if work_date > today:
        return "Future date is not allowed"

    if end_time <= start_time:
        return "End time must be greater than start time"

    if work_date == today and (start_time > now or end_time > now):
        return "Future time is not allowed"

    return None


def has_overlap(entries, new_start, new_end, start_attr, end_attr, exclude_id=None):
    for entry in entries:
        if exclude_id and entry.id == exclude_id:
            continue

        existing_start = getattr(entry, start_attr)
        existing_end = getattr(entry, end_attr)

        if not existing_start or not existing_end:
            continue

        if new_start < existing_end and new_end > existing_start:
            return True

    return False
