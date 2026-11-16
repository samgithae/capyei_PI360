"""The skills pick-list for a youth's profile: search, categories, popular and add.

Staff (editing a profile, or adding a youth) and the youth themselves (self-service CV) use the
same list, so the four views are built once by ``catalogue`` and mounted twice with a different
permission code each. The harness in ``tests/test_authz_matrix.py`` wants exactly one code per
method, which is why this is a pair of thin route sets and not one view with an "either" rule."""

from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.access import HasPermission
from apps.configuration import services as configuration

from .models import ParticipantSkill

POPULAR = 8


class ProfileSkillAddSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    category = serializers.CharField(max_length=80, required=False, allow_blank=True)
    confirm_similar = serializers.BooleanField(required=False, default=False)


def popular_skills(*, limit=POPULAR):
    """Skills held by the most youth, with how many hold each. When fewer than ``limit`` skills are
    held yet the list is topped up from the skills list itself (those carry ``used`` 0)."""
    rows = (
        ParticipantSkill.objects.filter(skill__active=True, participant__archived_at__isnull=True)
        .values("skill")
        .annotate(n=Count("participant", distinct=True))
        .order_by("-n", "skill__name")[:limit]
    )
    used = {str(r["skill"]): r["n"] for r in rows}
    found = configuration.skills_by_ids(used)
    out = [{**found[k], "used": n} for k, n in used.items() if k in found]
    if len(out) < limit:
        _, more = configuration.search_skills(limit=limit + len(out))
        out += [{**m, "used": 0} for m in more if m["id"] not in used][: limit - len(out)]
    return out


def catalogue(*, view, add, prefix):
    """Four views gated by one permission code each: ``view`` to read, ``add`` to create a skill.
    ``prefix`` only keeps the generated class names (and so the API schema) distinct."""

    class Search(APIView):
        """Partial, any-case, paged search; ``category`` narrows to one group."""

        permission_classes = [HasPermission]
        required_permission = {"GET": view}

        @extend_schema(
            operation_id=f"{prefix}_skills_search",
            parameters=[
                OpenApiParameter("q", str),
                OpenApiParameter("category", str),
                OpenApiParameter("limit", int),
                OpenApiParameter("offset", int),
            ],
            responses={200: dict},
        )
        def get(self, request):
            p = request.query_params

            def num(key, default):
                try:
                    return int(p.get(key, default))
                except ValueError:
                    return default

            total, rows = configuration.search_skills(
                q=p.get("q", ""), category=p.get("category", ""),
                limit=num("limit", 20), offset=num("offset", 0),
            )  # fmt: skip
            return Response({"total": total, "results": rows})

    class Categories(APIView):
        permission_classes = [HasPermission]
        required_permission = {"GET": view}

        @extend_schema(operation_id=f"{prefix}_skills_categories", responses={200: dict})
        def get(self, request):
            return Response({"results": configuration.skill_categories()})

    class Popular(APIView):
        permission_classes = [HasPermission]
        required_permission = {"GET": view}

        @extend_schema(operation_id=f"{prefix}_skills_popular", responses={200: dict})
        def get(self, request):
            return Response({"results": popular_skills()})

    class Add(APIView):
        """Add a missing skill to the central list (409 when it exists or looks like one)."""

        permission_classes = [HasPermission]
        required_permission = {"POST": add}

        @extend_schema(
            operation_id=f"{prefix}_skills_add",
            request=ProfileSkillAddSerializer,
            responses={201: dict, 409: dict},
        )
        def post(self, request):
            s = ProfileSkillAddSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            try:
                row = configuration.add_skill(actor=request.user, **s.validated_data)
            except configuration.SkillConflict as exc:
                return Response(
                    {
                        "errors": [{"field": "name", "message": exc.message, "code": exc.code}],
                        "existing": exc.existing,
                        "similar": exc.similar,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            except configuration.ConfigError as exc:
                return Response(
                    {"errors": [{"field": exc.field, "message": exc.message, "code": "invalid"}]},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(row, status=status.HTTP_201_CREATED)

    for cls, name in (
        (Search, "Search"),
        (Categories, "Categories"),
        (Popular, "Popular"),
        (Add, "Add"),
    ):
        cls.__name__ = cls.__qualname__ = f"{prefix.title()}Skill{name}View"
    return Search, Categories, Popular, Add


StaffSearch, StaffCategories, StaffPopular, StaffAdd = catalogue(
    view="participants.view_profile", add="participants.edit", prefix="staff"
)
