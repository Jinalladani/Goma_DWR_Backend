import math

from flask import request


DEFAULT_LIMIT = 10
MAX_LIMIT = 100


def get_search():
    return (request.args.get("search") or "").strip()


def apply_sort(query, allowed_columns, default_column, default_order="desc"):
    sort_by = request.args.get("sort_by", default_column)
    order = (request.args.get("order", default_order) or default_order).lower()
    column = allowed_columns.get(sort_by, allowed_columns[default_column])

    if order == "asc":
        return query.order_by(column.asc())

    return query.order_by(column.desc())


def paginate_query(query):
    should_paginate = "page" in request.args or "limit" in request.args
    total_items = query.order_by(None).count()

    if not should_paginate:
        return query.all(), {
            "page": 1,
            "limit": total_items,
            "total_items": total_items,
            "total_pages": 1 if total_items else 0,
            "paginated": False
        }

    page = _positive_int(request.args.get("page"), 1)
    limit = min(_positive_int(request.args.get("limit"), DEFAULT_LIMIT), MAX_LIMIT)
    total_pages = math.ceil(total_items / limit) if total_items else 0
    items = query.limit(limit).offset((page - 1) * limit).all()

    return items, {
        "page": page,
        "limit": limit,
        "total_items": total_items,
        "total_pages": total_pages,
        "paginated": True
    }


def paginate_list(items):
    should_paginate = "page" in request.args or "limit" in request.args
    total_items = len(items)

    if not should_paginate:
        return items, {
            "page": 1,
            "limit": total_items,
            "total_items": total_items,
            "total_pages": 1 if total_items else 0,
            "paginated": False
        }

    page = _positive_int(request.args.get("page"), 1)
    limit = min(_positive_int(request.args.get("limit"), DEFAULT_LIMIT), MAX_LIMIT)
    total_pages = math.ceil(total_items / limit) if total_items else 0
    start = (page - 1) * limit

    return items[start:start + limit], {
        "page": page,
        "limit": limit,
        "total_items": total_items,
        "total_pages": total_pages,
        "paginated": True
    }


def _positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed > 0 else default
