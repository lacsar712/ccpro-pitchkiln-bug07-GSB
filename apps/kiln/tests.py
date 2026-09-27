from datetime import datetime, timezone as dt_utc

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone

from apps.kiln.forms import OpenCookRunForm
from apps.kiln.models import CookRun, FireHearth, ResinLot
from apps.kiln.templatetags.kiln_time import wall_clock


class TimeZoneRoundTripTests(TestCase):
    """四条链路（写入归一 / 排序键 / 展示读出 / 看板最近时刻）须同一时区口径。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("tester", password="x")
        cls.lot = ResinLot.objects.create(
            lotCode="L-1",
            originPlace="沟里",
            arrivalKg=100,
            receivedAt=timezone.now(),
        )
        cls.hearth = FireHearth.objects.create(
            lane=1, tag="灶-试", resinGrade="特级", phase=FireHearth.PHASE_COLD
        )

    def test_form_wall_time_stored_as_shanghai_instant(self):
        # 链路1：datetime-local 里的 20:30 是上海墙钟，存库绝对时刻须为 12:30 UTC。
        wall = "2026-09-27T20:30"
        form = OpenCookRunForm(
            {"resinLot": self.lot.pk, "openedAt": wall, "targetSoftPointC": "88"},
            hearth=self.hearth,
        )
        self.assertTrue(form.is_valid(), form.errors)
        run = form.save(commit=False)
        run.hearth = self.hearth
        run.save()

        stored = CookRun.objects.get(pk=run.pk).openedAt
        self.assertTrue(timezone.is_aware(stored))
        self.assertEqual(
            stored.astimezone(dt_utc.utc),
            datetime(2026, 9, 27, 12, 30, tzinfo=dt_utc.utc),
        )

    def test_wall_clock_reads_back_entered_wall_time(self):
        # 链路3：读出必须把存库 UTC 还原成录入时的上海墙钟（不漂小时）。
        run = CookRun.objects.create(
            hearth=self.hearth,
            resinLot=self.lot,
            openedAt=timezone.make_aware(
                datetime(2026, 9, 27, 20, 30), timezone.get_current_timezone()
            ),
            targetSoftPointC=88,
        )
        self.assertEqual(wall_clock(run.openedAt), "2026-09-27 20:30")

    def test_board_order_first_matches_latest_open(self):
        # 链路2+4：排序第一灶必须能与看板 latest_opened 对账（含同分钟 id 兜底）。
        from apps.kiln.views import _board_context

        h2 = FireHearth.objects.create(
            lane=1, tag="灶-乙", resinGrade="一级", phase=FireHearth.PHASE_RAMPING
        )
        tie = timezone.make_aware(datetime(2026, 9, 27, 8, 0), dt_utc.utc)
        CookRun.objects.create(
            hearth=self.hearth, resinLot=self.lot, openedAt=tie, targetSoftPointC=88
        )
        newest = CookRun.objects.create(
            hearth=h2, resinLot=self.lot, openedAt=tie, targetSoftPointC=88
        )

        ctx = _board_context()
        # 同分钟时 id 大者排第一；第一灶的 openedAt 必须就是“最近开灶”。
        first = ctx["hearths"][0].open_runs_cache[0]
        self.assertEqual(first.pk, newest.pk)
        self.assertEqual(ctx["latest_opened_at"], newest.openedAt)
        self.assertEqual(ctx["latest_opened_tag"], h2.tag)

    def test_latest_open_partial_refreshes_after_open_run_post(self):
        # 链路4：开灶 POST 后，最近开灶片段读到的就是新灶的上海墙钟。
        client = Client()
        client.force_login(self.user)
        wall = "2026-09-27T06:05"
        resp = client.post(
            f"/hearth/{self.hearth.pk}/open-run/",
            {"resinLot": self.lot.pk, "openedAt": wall, "targetSoftPointC": "88"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)

        partial = client.get("/floor/latest-open/")
        body = partial.content.decode()
        self.assertIn(self.hearth.tag, body)
        self.assertIn("2026-09-27 06:05", body)
