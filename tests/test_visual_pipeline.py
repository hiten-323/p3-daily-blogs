"""A blocked visual surface is not publishable."""
from __future__ import annotations

from content_generator.publisher.prepublish_gate import authorize_publish


def test_visual_block_stops_publish():
    content = {
        "facebook_post": {"hook": "Turn the jar around", "body": "Read the label."},
        "visual_gate": {"blocked_platforms": ["facebook"], "surfaces": []},
    }
    decision = authorize_publish(content, "facebook")
    assert decision["allowed"] is False
    assert decision["reason"] == "visual_qa_blocked"
