"""account 칸 이메일 표시, 상태 필터, LAIDD 색 구분(11-11).

컨트롤러가 job 에 `email` 을 붙여 준다. 없으면(LAIDD·조회 실패·옛 컨트롤러) 지금처럼 Slurm account 번호를 보여 준다.
"""
import pytest

from ui.job_utils import (
    ALL_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_OTHER,
    ALL_ACCOUNTS,
    ALL_EMAILS,
    account_display,
    account_email,
    account_filter_values,
    account_id,
    aggregate_jobs_by_account,
    aggregate_model_accounts,
    email_filter_values,
    history_line_tag,
    matches_account,
    matches_email,
    matches_status,
    status_category,
)


@pytest.mark.parametrize(("job", "expected"), [
    ({"account": "481", "email": "a@x.com"}, "a@x.com"),
    ({"account": "3_admin", "email": "b@x.com"}, "b@x.com (admin)"),
    ({"account": "tools_481", "email": "a@x.com"}, "a@x.com (tools)"),
    ({"account": "481"}, "481"),
    ({"account": "77", "qos": "laidd"}, "77"),
    ({"account": "481", "email": ""}, "481"),
    ({}, "unknown"),
])
def test_account_display(job, expected):
    assert account_display(job) == expected


@pytest.mark.parametrize(("state", "expected"), [
    ("COMPLETED", STATUS_COMPLETED), ("CD", STATUS_COMPLETED),
    ("FAILED", STATUS_FAILED), ("F", STATUS_FAILED),
    ("CANCELLED by 0", STATUS_CANCELLED), ("CA", STATUS_CANCELLED),
    ("RUNNING", STATUS_OTHER), ("NODE_FAIL", STATUS_OTHER), ("TIMEOUT", STATUS_OTHER), (None, STATUS_OTHER),
])
def test_status_category(state, expected):
    assert status_category(state) == expected


def test_status_filter():
    jobs = [{"state": "COMPLETED"}, {"state": "FAILED"}, {"state": "CANCELLED by 0"}, {"state": "RUNNING"}]
    assert [matches_status(j, ALL_STATUSES) for j in jobs] == [True, True, True, True]
    assert [matches_status(j, STATUS_FAILED) for j in jobs] == [False, True, False, False]
    assert [matches_status(j, STATUS_CANCELLED) for j in jobs] == [False, False, True, False]
    assert [matches_status(j, STATUS_OTHER) for j in jobs] == [False, False, False, True]


@pytest.mark.parametrize(("job", "expected"), [
    ({"state": "COMPLETED", "qos": "laidd"}, "laidd_completed"),
    ({"state": "FAILED", "qos": "laidd"}, "laidd_failed"),
    ({"state": "CANCELLED", "qos": "laidd"}, "laidd_cancelled"),
    ({"state": "RUNNING", "qos": "laidd"}, "laidd_default"),
    ({"state": "COMPLETED", "source": "vessl"}, "vessl_completed"),
    ({"state": "FAILED", "source": "vessl"}, "vessl_failed"),
    ({"state": "CANCELLED", "source": "vessl"}, "vessl_default"),
    ({"state": "COMPLETED"}, "completed"),
    ({"state": "FAILED"}, "failed"),
    ({"state": "CANCELLED by 0"}, "cancelled"),
    ({"state": "PENDING"}, "default"),
])
def test_history_line_tag_keeps_old_colors_and_adds_laidd(job, expected):
    assert history_line_tag(job) == expected


@pytest.mark.parametrize(("job", "expected_id", "expected_email"), [
    ({"account": "481", "email": "a@x.com"}, "481", "a@x.com"),
    ({"account": "3_admin", "email": "b@x.com"}, "3_admin", "b@x.com"),
    ({"account": "tools_481", "email": "a@x.com"}, "tools_481", "a@x.com"),
    ({"account": "77", "qos": "laidd"}, "77", "-"),
    ({}, "unknown", "-"),
])
def test_number_is_shown_next_to_the_email(job, expected_id, expected_email):
    """이메일만 보이면 번호로 찾기 불편해서(11-17) 번호 칸을 따로 보여 준다."""
    assert (account_id(job), account_email(job)) == (expected_id, expected_email)


HISTORY_JOBS = [
    {"account": "481", "email": "a@x.com"},
    {"account": "3_admin", "email": "b@x.com"},
    {"account": "tools_481", "email": "a@x.com"},
    {"account": "10", "email": "c@x.com"},
    {"account": "77", "qos": "laidd"},
    {"account": "481", "email": "a@x.com"},
]


def test_account_and_email_filters_are_separate_lists():
    """계정 필터는 번호(숫자는 숫자 순), 이메일 필터는 이메일만. 이메일 없는 job 은 이메일 항목을 만들지 않는다."""
    assert account_filter_values(HISTORY_JOBS) == [ALL_ACCOUNTS, "10", "77", "481", "3_admin", "tools_481"]
    assert email_filter_values(HISTORY_JOBS) == [ALL_EMAILS, "a@x.com", "b@x.com", "c@x.com"]


def test_account_and_email_filters_match_independently():
    by_account = [job for job in HISTORY_JOBS if matches_account(job, "481")]
    by_email = [job for job in HISTORY_JOBS if matches_email(job, "a@x.com")]
    both = [job for job in HISTORY_JOBS if matches_account(job, "tools_481") and matches_email(job, "a@x.com")]
    assert (len(by_account), len(by_email), len(both)) == (2, 3, 1)
    assert all(matches_account(job, ALL_ACCOUNTS) and matches_email(job, ALL_EMAILS) for job in HISTORY_JOBS)
    assert not matches_email({"account": "77"}, "-")


def test_account_stats_rows_carry_the_number():
    jobs = [
        {"account": "481", "email": "a@x.com", "state": "COMPLETED", "job_name": "boltz_1"},
        {"account": "481_admin", "email": "a@x.com", "state": "COMPLETED", "job_name": "boltz_2"},
        {"account": "77", "qos": "laidd", "state": "FAILED", "job_name": "boltz_3"},
    ]
    by_account = {row["account"]: row["account_id"] for row in aggregate_jobs_by_account(jobs)}
    assert by_account == {"a@x.com": "481", "a@x.com (admin)": "481_admin", "77": "77"}
    model_rows = {row["account"]: row["account_id"] for row in aggregate_model_accounts(jobs, "boltz")}
    assert model_rows == by_account


def test_account_stats_group_by_email_and_keep_admin_separate():
    jobs = [
        {"account": "481", "email": "a@x.com", "state": "COMPLETED", "job_name": "boltz_1"},
        {"account": "481", "email": "a@x.com", "state": "FAILED", "job_name": "boltz_2"},
        {"account": "481_admin", "email": "a@x.com", "state": "COMPLETED", "job_name": "boltz_3"},
        {"account": "77", "qos": "laidd", "state": "COMPLETED", "job_name": "boltz_4"},
    ]
    by_account = {row["account"]: row for row in aggregate_jobs_by_account(jobs)}
    assert set(by_account) == {"a@x.com", "a@x.com (admin)", "77"}
    assert (by_account["a@x.com"]["total"], by_account["a@x.com"]["failed"]) == (2, 1)

    model_rows = {row["account"]: row for row in aggregate_model_accounts(jobs, "boltz")}
    assert set(model_rows) == {"a@x.com", "a@x.com (admin)", "77"}
