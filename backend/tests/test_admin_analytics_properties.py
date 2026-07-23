"""Property-based tests for admin analytics aggregation logic.

Uses Hypothesis to verify universal properties of usage aggregation,
date range filtering, top users ranking, and tier distribution consistency.

# Feature: admin-panel
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
import pytest

from app.services.admin_analytics import (
    get_monthly_usage,
    get_top_users,
    get_tier_distribution,
    MonthlyUsageData,
    TierDistribution,
    TopUserRow,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate a valid month string within a window amenable to the 90-day lookback
# We use a narrow window around "now" to ensure items pass the date clamp.
def _current_month() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def _recent_months(max_back: int = 2) -> list[str]:
    """Return list of recent months (current and up to max_back previous)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    months = []
    for i in range(max_back + 1):
        dt = now - datetime.timedelta(days=30 * i)
        months.append(dt.strftime("%Y-%m"))
    return sorted(set(months))


RECENT_MONTHS = _recent_months(2)

# Strategy for a valid tier
tier_strategy = st.sampled_from(["free", "pro", "business"])

# Strategy for a user ID (short, alphanumeric)
user_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=3,
    max_size=10,
)

# Strategy for sessions/minutes (non-negative integers)
usage_int_strategy = st.integers(min_value=0, max_value=10000)


@st.composite
def dynamo_items_strategy(draw):
    """Generate a list of DynamoDB items representing PROFILE and MONTH records.

    Returns (items, user_profiles, user_month_records) for verification.
    """
    # Generate 1-10 users
    num_users = draw(st.integers(min_value=0, max_value=8))
    user_ids = [f"user{i}" for i in range(num_users)]

    items = []
    user_profiles = {}  # {user_id: {"tier": ..., "email": ...}}
    user_month_records = {}  # {user_id: {month: {"sessions": N, "minutes": N}}}

    for uid in user_ids:
        tier = draw(tier_strategy)
        email = f"{uid}@test.com"
        # PROFILE item
        items.append({
            "pk": f"USER#{uid}",
            "sk": "PROFILE",
            "tier": tier,
            "email": email,
        })
        user_profiles[uid] = {"tier": tier, "email": email}
        user_month_records[uid] = {}

        # Generate 0-3 MONTH items for recent months
        num_months = draw(st.integers(min_value=0, max_value=min(3, len(RECENT_MONTHS))))
        chosen_months = draw(
            st.lists(
                st.sampled_from(RECENT_MONTHS),
                min_size=num_months,
                max_size=num_months,
                unique=True,
            )
        )
        for month in chosen_months:
            sessions = draw(usage_int_strategy)
            minutes = draw(usage_int_strategy)
            items.append({
                "pk": f"USER#{uid}",
                "sk": f"MONTH#{month}",
                "sessions_used": sessions,
                "minutes_used": minutes,
            })
            user_month_records[uid][month] = {
                "sessions": sessions,
                "minutes": minutes,
            }

    return items, user_profiles, user_month_records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings():
    """Return a mock settings object."""
    s = MagicMock()
    s.aws_region = "us-east-1"
    return s


def _mock_table_with_items(items: list[dict]):
    """Create a mock DynamoDB table that returns the given items on scan."""
    table = MagicMock()
    table.scan.return_value = {"Items": items}
    return table


def _mock_get_table(table):
    """Patch _get_table to return our mock table."""
    return patch("app.services.admin_analytics._get_table", return_value=table)


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 9: Usage aggregation correctness
# ---------------------------------------------------------------------------


class TestUsageAggregationCorrectness:
    """Property 9: Usage aggregation correctness.

    For any set of per-user usage records, total_sessions equals sum of
    individual sessions, total_minutes equals sum of individual minutes,
    unique_active_users equals count of distinct users with sessions > 0.

    **Validates: Requirements 10.1, 10.2**
    """

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_totals_equal_sum_of_individual_records(self, data):
        """Aggregated totals match the sum of individual usage records."""
        # Feature: admin-panel, Property 9: Usage aggregation correctness
        items, user_profiles, user_month_records = data

        table = _mock_table_with_items(items)
        current_month = _current_month()

        with _mock_get_table(table):
            result = get_monthly_usage(start_month=RECENT_MONTHS[0], end_month=RECENT_MONTHS[-1])

        # Compute expected aggregates manually
        expected_sessions = 0
        expected_minutes = 0
        active_users = set()

        for uid, months in user_month_records.items():
            for month, usage in months.items():
                if month >= RECENT_MONTHS[0] and month <= RECENT_MONTHS[-1]:
                    expected_sessions += usage["sessions"]
                    expected_minutes += usage["minutes"]
                    if usage["sessions"] > 0:
                        active_users.add(uid)

        assert result.totals.total_sessions == expected_sessions
        assert result.totals.total_minutes == expected_minutes
        assert result.totals.unique_active_users == len(active_users)

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_per_month_summaries_sum_to_totals(self, data):
        """Sum of per-month summaries equals the grand totals."""
        # Feature: admin-panel, Property 9: Usage aggregation correctness
        items, _, _ = data

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_monthly_usage(start_month=RECENT_MONTHS[0], end_month=RECENT_MONTHS[-1])

        sum_sessions = sum(m.total_sessions for m in result.months)
        sum_minutes = sum(m.total_minutes for m in result.months)

        assert result.totals.total_sessions == sum_sessions
        assert result.totals.total_minutes == sum_minutes


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 10: Date range filtering
# ---------------------------------------------------------------------------


class TestDateRangeFiltering:
    """Property 10: Date range filtering.

    For any valid date range, all returned months fall within range,
    no months outside range included.

    **Validates: Requirements 10.4**
    """

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_returned_months_within_range(self, data):
        """All months in the response fall within [start_month, end_month]."""
        # Feature: admin-panel, Property 10: Date range filtering
        items, _, user_month_records = data

        # Use the full recent window as the query range
        start_month = RECENT_MONTHS[0]
        end_month = RECENT_MONTHS[-1]

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_monthly_usage(start_month=start_month, end_month=end_month)

        for month_summary in result.months:
            assert month_summary.month >= start_month
            assert month_summary.month <= end_month

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_no_months_outside_range_included(self, data):
        """Months with data outside the range are excluded from results."""
        # Feature: admin-panel, Property 10: Date range filtering
        items, _, user_month_records = data

        # Query only the current month
        current = _current_month()

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_monthly_usage(start_month=current, end_month=current)

        # All returned months must be exactly the current month
        for month_summary in result.months:
            assert month_summary.month == current

    @given(
        data=dynamo_items_strategy(),
        start_idx=st.integers(min_value=0, max_value=len(RECENT_MONTHS) - 1),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_subset_range_only_includes_matching_months(self, data, start_idx):
        """When a subset range is requested, only months in that range appear."""
        # Feature: admin-panel, Property 10: Date range filtering
        items, _, _ = data

        start_month = RECENT_MONTHS[start_idx]
        end_month = RECENT_MONTHS[-1]

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_monthly_usage(start_month=start_month, end_month=end_month)

        for month_summary in result.months:
            assert month_summary.month >= start_month
            assert month_summary.month <= end_month


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 11: Top users ranking
# ---------------------------------------------------------------------------


class TestTopUsersRanking:
    """Property 11: Top users ranking.

    Top users sorted descending by minutes_used, at most 10 entries,
    each includes email/tier/sessions/minutes.

    **Validates: Requirements 11.1, 11.2**
    """

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_top_users_sorted_descending_by_minutes(self, data):
        """Top users list is sorted in descending order by minutes_used."""
        # Feature: admin-panel, Property 11: Top users ranking
        items, _, _ = data

        table = _mock_table_with_items(items)
        current = _current_month()

        with _mock_get_table(table):
            result = get_top_users(month=current, limit=10)

        # Verify descending order by minutes_used
        for i in range(len(result) - 1):
            assert result[i].minutes_used >= result[i + 1].minutes_used

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_top_users_at_most_10_entries(self, data):
        """Top users list contains at most 10 entries."""
        # Feature: admin-panel, Property 11: Top users ranking
        items, _, _ = data

        table = _mock_table_with_items(items)
        current = _current_month()

        with _mock_get_table(table):
            result = get_top_users(month=current, limit=10)

        assert len(result) <= 10

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_top_users_include_required_fields(self, data):
        """Each top user entry includes email, tier, sessions_used, minutes_used."""
        # Feature: admin-panel, Property 11: Top users ranking
        items, _, _ = data

        table = _mock_table_with_items(items)
        current = _current_month()

        with _mock_get_table(table):
            result = get_top_users(month=current, limit=10)

        for user_row in result:
            # Verify all required fields are present (not None)
            assert user_row.email is not None
            assert user_row.tier is not None
            assert user_row.sessions_used is not None
            assert user_row.minutes_used is not None
            # Tier must be a valid value
            assert user_row.tier in {"free", "pro", "business", ""}


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 12: Tier distribution consistency
# ---------------------------------------------------------------------------


class TestTierDistributionConsistency:
    """Property 12: Tier distribution consistency.

    Tier counts sum to total users, percentages equal (count/total)*100,
    zero users means zero percentages.

    **Validates: Requirements 11.3**
    """

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_tier_counts_sum_to_total_users(self, data):
        """The sum of tier counts equals the total number of users."""
        # Feature: admin-panel, Property 12: Tier distribution consistency
        items, user_profiles, _ = data

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_tier_distribution()

        total_count = result.free.count + result.pro.count + result.business.count
        # Total should equal the number of PROFILE items (users)
        assert total_count == len(user_profiles)

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_percentages_equal_count_over_total_times_100(self, data):
        """Each tier's percentage equals (count/total)*100."""
        # Feature: admin-panel, Property 12: Tier distribution consistency
        items, user_profiles, _ = data

        table = _mock_table_with_items(items)

        with _mock_get_table(table):
            result = get_tier_distribution()

        total = result.free.count + result.pro.count + result.business.count

        if total == 0:
            assert result.free.percentage == 0.0
            assert result.pro.percentage == 0.0
            assert result.business.percentage == 0.0
        else:
            assert result.free.percentage == round((result.free.count / total) * 100, 2)
            assert result.pro.percentage == round((result.pro.count / total) * 100, 2)
            assert result.business.percentage == round((result.business.count / total) * 100, 2)

    @given(data=dynamo_items_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_users_means_zero_percentages(self, data):
        """When no users exist, all percentages are zero."""
        # Feature: admin-panel, Property 12: Tier distribution consistency
        # Use empty items to represent zero users
        table = _mock_table_with_items([])

        with _mock_get_table(table):
            result = get_tier_distribution()

        assert result.free.count == 0
        assert result.pro.count == 0
        assert result.business.count == 0
        assert result.free.percentage == 0.0
        assert result.pro.percentage == 0.0
        assert result.business.percentage == 0.0
