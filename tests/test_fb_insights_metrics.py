import os
import pytest
from unittest.mock import patch, MagicMock
from content_generator.analytics import insights_fetcher, post_outcomes


def test_fetch_account_insights_resilient_to_metric_400():
    """Graph API 400 for deprecated metrics must not crash or drop valid metrics."""
    def fake_graph_get(path, params, bypass_circuit=False):
        metric = params.get("metric")
        if metric == "profile_views":
            # Simulate 400 error return
            return None
        if metric == "reach":
            return {"data": [{"name": "reach", "values": [{"value": 142}]}]}
        return None

    with patch.dict(os.environ, {"INSTAGRAM_ACCOUNT_ID": "17841400000000"}):
        with patch.object(insights_fetcher, "_graph_get", side_effect=fake_graph_get):
            res = insights_fetcher._fetch_account_insights()
            assert res == {"reach": 142}
            assert "profile_views" not in res


def test_audience_value_excludes_zero_engagement_snapshots():
    """Posts with only zero likes/comments and no reach must not produce engagement value."""
    # Zero likes and comments, no reach
    zero_metrics = {"likes": 0, "comments": 0}
    assert post_outcomes.audience_value(zero_metrics) is None

    # Zero likes but has reach -> valid
    reach_metrics = {"likes": 0, "comments": 0, "reach": 120}
    val = post_outcomes.audience_value(reach_metrics)
    assert val is not None
    assert val[0] == "reach"
    assert val[1] == 120.0

    # Non-zero engagement without reach -> valid
    engaged_metrics = {"likes": 3, "comments": 1}
    val2 = post_outcomes.audience_value(engaged_metrics)
    assert val2 is not None
    assert val2[0] == "engagement"
    assert val2[1] == 6.0  # 3*1 + 1*3 = 6
