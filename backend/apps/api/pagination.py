from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination for every list (doc 04 CMP-02): stable under inserts and
    no COUNT(*) on large tables. Views with a natural order override ``ordering``."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-pk"


def page_size_of(params, default=50) -> int:
    """Rows per page asked for by ``?page_size=``; anything unusable falls back to the default."""
    try:
        n = int(params.get("page_size", default))
    except (TypeError, ValueError):
        return default
    return n if 1 <= n <= 200 else default
