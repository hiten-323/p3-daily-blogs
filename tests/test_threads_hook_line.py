"""One-paragraph Threads copy must not be read as all-hook / no-body."""
from content_generator.core import scroller_psychology as sp
from content_generator.core.piece_integrity import ensure_structural_fields

PAYING = ("That exact moment when hot milk swallows your morning coffee? "
          "Ultra Blend is 70% coffee and 30% chicory, so check the label: the ingredient "
          "list tells you why it holds up in milk. How do you take yours?")
BAIT = ("Most people have no idea what is really inside their coffee jar every morning. "
        "You would be shocked honestly, it is wild. Follow us for more.")


def test_hook_moves_to_its_own_line_words_unchanged():
    p = ensure_structural_fields({"text": PAYING}, "threads_post")
    assert p["text"].split("\n\n")[0].endswith("?")
    assert " ".join(p["text"].split()) == " ".join(PAYING.split())


def test_paying_post_passes_payoff_gate_after_layout():
    assert not sp.payoff_strength({"text": PAYING})["passes"]  # old one-paragraph read
    assert sp.payoff_strength(ensure_structural_fields({"text": PAYING}, "threads_post"))["passes"]


def test_bait_still_fails_gate_unchanged():
    p = ensure_structural_fields({"text": BAIT}, "threads_post")
    assert not sp.payoff_strength(p)["passes"]


def test_existing_line_breaks_and_other_labels_untouched():
    multi = "Hook line here, quite long.\n\nBody stays exactly as written by the model."
    assert ensure_structural_fields({"text": multi}, "threads_post")["text"] == multi
    fb = {"text": PAYING}
    ensure_structural_fields(fb, "facebook_post")
    assert fb["text"] == PAYING
