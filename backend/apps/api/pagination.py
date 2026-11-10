from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination for every list (doc 04 CMP-02): stable under inserts and
    no COUNT(*) on large tables. Views with a natural order override ``ordering``."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-pk"
