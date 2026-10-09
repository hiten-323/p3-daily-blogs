from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
POLICY = ROOT / "founder_policies.yaml"


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # NVIDIA is the primary LLM. A blank NVIDIA_MODEL secret must not be
    # required; the code default applies when the env value is empty.
    assert "NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}" in text
    assert "NVIDIA_MODEL: ${{ secrets.NVIDIA_MODEL }}" in text

    # Canonical production windows.
    assert "cron: '30 0 * * *'" in text
    assert "cron: '30 4 * * *'" in text
    assert "cron: '30 16 * * *'" in text

    # Manual execution must select a slot instead of inferring it from wall time.
    assert "Manual slot to execute — never infer from wall-clock time" in text
    assert "required: true" in text
    assert "- generate" in text and "- morning" in text and "- evening" in text

    # Generate is not a publication slot.
    assert "no publication expected at 06:00 IST" in text
    assert "GENERATE verified" in text

    # Publishing slots have an actual Meta preflight, before the pipeline runs.
    # The scope check lives in meta_token_health so generate and publish share it.
    assert "Verify Meta publishing access" in text
    assert "python -m content_generator.ops.meta_token_health" in text
    assert "env.FORCE_SLOT != 'generate'" in text
    health = (ROOT / "content_generator" / "ops" / "meta_token_health.py").read_text(encoding="utf-8")
    assert "instagram_basic" in health and "instagram_content_publish" in health
    assert "debug_token" in health and "id,username" in health
    from config.api_versions import META_GRAPH_BASE
    assert META_GRAPH_BASE == "https://graph.facebook.com/v24.0"
    assert "META_GRAPH_BASE" in health

    # Soft Meta notice on generate (does not fail the generate slot).
    assert "Soft Meta token notice" in text or "Meta token soft-check" in text

    # Repository synchronization failures must never be swallowed.
    assert "git pull --rebase --autostash || true" not in text
    assert re.search(r"git pull --rebase --autostash\s*$", text, re.M)

    # No stale production-window references.
    assert "08:00 / 20:00" not in text
    assert "08:00/20:00" not in text

    # Extended content is a founder-policy decision, not a workflow hardcode.
    # Emergency env override is still allowed in the run step if present, but
    # the workflow must not force ENABLE_EXTENDED_CONTENT: "true".
    assert 'ENABLE_EXTENDED_CONTENT: "true"' not in text
    policy = POLICY.read_text(encoding="utf-8")
    assert "enable_extended_content:" in policy

    # Persist step must force-add learning + daily content so Git alone can
    # reconstruct state if the Actions cache disappears.
    assert "git add -f output/learning/" in text
    assert "output/content_" in text

    # EVERY TEST THE GATE INVOKES MUST EXIST.
    #
    # The gate runs before the pipeline, so a missing file fails every run
    # before anything generates or publishes — a total outage wearing the
    # costume of a safety check. This shipped once: the workflow called
    # test_workflow_contract.py and test_persistence_invariant.py while neither
    # had been written yet.
    runs_pytest = re.search(r"pytest\s[^\n]*\btests/", text)
    invoked = re.findall(r"python (tests/\w+\.py)", text)

    missing = [t for t in invoked if not (ROOT / t).is_file()]
    assert not missing, f"the gate invokes tests that do not exist: {missing}"

    # A suite nobody runs protects nothing. `pytest tests/` collects the whole
    # directory, so it satisfies this; naming files individually does not,
    # unless every file is named.
    if not runs_pytest:
        on_disk = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py")}
        unwired = sorted(on_disk - set(invoked))
        assert not unwired, f"test suites exist but are never run: {unwired}"

    # Whichever runner is used, every suite must actually EXECUTE something.
    # Ten suites were pytest-style (test_* functions, no main()); running those
    # as `python tests/x.py` merely imports them and exits 0, so they passed
    # while asserting nothing. Script-style suites therefore expose test_main()
    # and the gate uses pytest, which collects both shapes.
    for path in (ROOT / "tests").glob("test_*.py"):
        body = path.read_text(encoding="utf-8")
        collectable = ("def test_" in body)
        assert collectable, (
            f"{path.name} defines no test_* function, so pytest collects nothing "
            "from it — add test_main() if it is script-style"
        )

    print("workflow contract: PASS")


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


_PUBLISHING_STEPS = (
    "Clear run lock (if force_run)",
    "Meta token soft-check (generate)",
    "Verify Meta publishing access",
    "Run autonomous pipeline",
    "Verify slot result",
    "Persist validated state to Git",
    "Alert on failure",
)

_LLM_PROBE_ENV = {
    "NVIDIA_API_KEY": "${{ secrets.NVIDIA_API_KEY }}",
    "NVIDIA_MODEL": "${{ secrets.NVIDIA_MODEL }}",
    "GEMINI_API_KEY": "${{ secrets.GEMINI_API_KEY }}",
    "GROQ_API_KEY": "${{ secrets.GROQ_API_KEY }}",
    "OPENROUTER_API_KEY": "${{ secrets.OPENROUTER_API_TOKEN }}",
    "DEEPSEEK_API_KEY": "${{ secrets.DEEPSEEK_API_KEY }}",
    "CEREBRAS_API_KEY": "${{ secrets.CEREBRAS_API_KEY }}",
}


def _workflow_document() -> dict:
    import yaml

    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 treats the bare key `on` as boolean true.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def test_dry_run_gates_publishing_steps():
    """Scheduled runs keep their conditions. Dry-run skips publish and commit."""
    data = _workflow_document()
    dry = data["on"]["workflow_dispatch"]["inputs"]["dry_run"]
    assert dry["type"] == "boolean"
    assert dry["required"] is False
    assert dry["default"] is False

    steps = data["jobs"]["run-pipeline"]["steps"]
    by_name = {step["name"]: step for step in steps}

    for name in _PUBLISHING_STEPS:
        condition = str(by_name[name].get("if") or "")
        assert "github.event.inputs.dry_run != 'true'" in condition, name

    assert "success()" in by_name["Run autonomous pipeline"]["if"]
    assert "success()" in by_name["Verify slot result"]["if"]
    assert "always()" in by_name["Persist validated state to Git"]["if"]
    assert "github.event.inputs.dry_run != 'true'" in by_name["Persist validated state to Git"]["if"]
    assert "failure()" in by_name["Alert on failure"]["if"]
    assert "github.event.inputs.force_run == 'true'" in by_name["Clear run lock (if force_run)"]["if"]
    assert "env.FORCE_SLOT == 'generate'" in by_name["Meta token soft-check (generate)"]["if"]
    assert "env.FORCE_SLOT != 'generate'" in by_name["Verify Meta publishing access"]["if"]

    probe = by_name["Probe LLM providers"]
    assert "github.event.inputs.dry_run == 'true'" in probe["if"]
    assert probe["env"] == _LLM_PROBE_ENV
    assert "python -m content_generator.providers.llm_probe" in probe["run"]
    assert "/models" not in probe["run"]

    pytest_steps = [step for step in steps if "pytest -q tests/" in str(step.get("run") or "")]
    assert pytest_steps
    for step in pytest_steps:
        assert "dry_run" not in str(step.get("if") or "")


def test_llm_probe_is_one_chat_call_per_provider(monkeypatch, capsys):
    from content_generator.providers import llm_probe

    keys = {
        "NVIDIA_API_KEY": "nvapi-secretvalue",
        "NVIDIA_MODEL": "meta/llama-3.3-70b-instruct",
        "GROQ_API_KEY": "gsk_testkeyvalue",
        "GEMINI_API_KEY": "AIza-secretvalue",
        "CEREBRAS_API_KEY": "csk-secretvalue",
        "DEEPSEEK_API_KEY": "sk-secretvalue",
        "OPENROUTER_API_KEY": "sk-or-secretvalue",
    }
    for name, value in keys.items():
        monkeypatch.setenv(name, value)

    calls = []

    class _Resp:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def post(url, headers=None, json=None, params=None, timeout=None):
        calls.append({
            "url": url,
            "json": json,
            "params": params,
            "timeout": timeout,
            "auth": (headers or {}).get("Authorization", ""),
        })
        if "api.groq.com" in url:
            return _Resp(429, "slow down gsk_testkeyvalue")
        return _Resp(200, '{"choices":[{"message":{"content":"OK"}}]}')

    monkeypatch.setattr(llm_probe.requests, "post", post)
    assert llm_probe.main() == 0

    urls = [call["url"] for call in calls]
    assert urls[0] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert calls[0]["json"]["model"] == "meta/llama-3.3-70b-instruct"
    assert calls[0]["json"]["max_tokens"] == 16
    assert calls[0]["auth"] == "Bearer nvapi-secretvalue"
    assert all(not url.rstrip("/").endswith("/models") for url in urls)
    assert any(url.endswith(":generateContent") for url in urls)
    assert len(calls) == 6
    for call in calls:
        assert call["timeout"] == 20
        body = call["json"]
        if "generationConfig" in body:
            assert body["generationConfig"]["maxOutputTokens"] == 16
        else:
            assert body["max_tokens"] == 16
        assert "nvapi-secretvalue" not in call["url"]

    out = capsys.readouterr().out
    assert "providers with keys: nvidia, groq, gemini, cerebras, deepseek, openrouter" in out
    assert "nvidia: OK" in out
    assert "groq: HTTP 429" in out
    assert "gsk_testkeyvalue" not in out
    for secret in keys.values():
        assert secret not in out

    monkeypatch.delenv("NVIDIA_API_KEY")
    calls.clear()
    skipped = dict(llm_probe.probe_results())
    assert skipped["nvidia"] == "skipped"
    assert all("api.nvidia.com" not in call["url"] for call in calls)


def test_llm_probe_fails_nvidia_on_empty_content(monkeypatch, capsys):
    from content_generator.providers import llm_probe

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "google/gemma-4-31b-it")
    for name in (
        "GROQ_API_KEY", "GEMINI_API_KEY", "CEREBRAS_API_KEY",
        "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    class _Resp:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def post(url, headers=None, json=None, params=None, timeout=None):
        assert "nvapi-secretvalue" not in url
        return _Resp(200, '{"choices":[{"message":{"content":"  \\n"}}]}')

    monkeypatch.setattr(llm_probe.requests, "post", post)
    assert llm_probe.main() == 1
    out = capsys.readouterr().out
    assert "nvidia: empty content" in out
    assert "nvidia: OK" not in out
    assert "nvapi-secretvalue" not in out


def test_meta_preflight_checks_instagram_publish_scopes():
    data = _workflow_document()
    steps = {step["name"]: step for step in data["jobs"]["run-pipeline"]["steps"]}
    soft = steps["Meta token soft-check (generate)"]
    hard = steps["Verify Meta publishing access"]
    assert "content_generator.ops.meta_token_health" in soft["run"]
    assert "content_generator.ops.meta_token_health" in hard["run"]
    assert soft["env"]["META_TOKEN_MODE"] == "soft"
    assert hard["env"]["META_TOKEN_MODE"] == "strict"
    assert "INSTAGRAM_ACCESS_TOKEN" in soft["env"]
    assert "INSTAGRAM_ACCESS_TOKEN" in hard["env"]
    verify = steps["Verify slot result"]["run"]
    assert 'verdict.get("warnings")' in verify


if __name__ == "__main__":
    main()
