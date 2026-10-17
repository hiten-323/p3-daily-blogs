"""IG must resolve the linked account from the Page and never publish to the Page ID."""
from content_generator.ops import meta_token_health as mth
from content_generator.publisher import instagram as ig


def _fake(routes):
    def fetch(url, headers, timeout=0):
        for frag, res in routes:
            if frag in url:
                if isinstance(res, Exception):
                    raise res
                return res
        return {"id": "x"}
    return fetch


def test_falls_back_to_me_accounts_with_second_token(monkeypatch):
    monkeypatch.setattr(mth, "_fetch", _fake([
        ("/me/accounts", {"data": [{"id": "PAGE", "instagram_business_account": {"id": "IG1", "username": "pp"}}]}),
        ("/PAGE?", {"id": "PAGE"}),
        ("/me?", {"id": "PAGE"}),
    ]))
    out = mth.resolve_linked_instagram(["PAGE"], ["t1", "t2"], attempts=1)
    assert out["id"] == "IG1"
    assert all("t1" not in d.split(":")[2] for d in out["diag"] if d.count(":") >= 2)


def test_connected_instagram_account_field_accepted(monkeypatch):
    monkeypatch.setattr(mth, "_fetch", _fake([("/PAGE?", {"id": "PAGE", "connected_instagram_account": {"id": "IG2"}})]))
    assert mth.resolve_linked_instagram(["PAGE"], ["t"], attempts=1)["id"] == "IG2"


def test_unresolved_reports_keys_only(monkeypatch):
    monkeypatch.setattr(mth, "_fetch", _fake([("/me/accounts", mth.TokenHttpError(400, "secret body"))]))
    out = mth.resolve_linked_instagram(["PAGE"], ["tok"], attempts=1)
    assert out["id"] == "" and "secret body" not in " ".join(out["diag"])


def test_publisher_never_uses_page_id(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "PAGE")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "PAGE")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(ig, "_IG_RESOLVE_TRIED", False)
    monkeypatch.setattr(mth, "resolve_linked_instagram", lambda *a, **k: {"id": "", "username": "", "diag": []})
    assert ig.is_configured() is False
    monkeypatch.setattr(ig, "_IG_RESOLVE_TRIED", False)
    monkeypatch.setattr(mth, "resolve_linked_instagram", lambda *a, **k: {"id": "IG9", "username": "", "diag": []})
    assert ig.is_configured() is True
    import os
    assert os.environ["INSTAGRAM_ACCOUNT_ID"] == "IG9"
