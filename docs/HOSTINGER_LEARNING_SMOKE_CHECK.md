# Hostinger deployment checks: post-publication learning

This runbook is for validating the deployed learning loop without publishing content or exposing credentials.

## Important: one scheduler must own publishing

GitHub Actions has recently executed the daily and recovery workflows. If Hostinger is also running the publishing scheduler, there may be two independent schedulers. Before enabling Hostinger publishing, confirm which scheduler is authoritative. Do not run both against the same social accounts unless duplicate suppression and shared-state locking have been verified. Do not disable either scheduler until the intended owner is confirmed.

## State directory

Both the learning engine and platform measurement tracker now resolve a relative `LEARNING_DIR` from the repository root, not from the process working directory. For production, prefer an explicit absolute path shared by every process that reads/writes the learning state, for example:

```bash
LEARNING_DIR=/home/ACCOUNT/app/output/learning
```

Replace the example path with the actual Hostinger deployment path. The service user must be able to read and write the directory. Do not copy live tokens into this file or commit them to Git.

## Safe post-deploy smoke checks

Run as the same Linux user and Python environment that the scheduler uses:

```bash
cd /absolute/path/to/p3-daily-blogs
. .venv/bin/activate
export PYTHONPATH=.
python -m pytest tests/test_platform_learning.py -q
python -m compileall -q content_generator/core/learning_engine.py content_generator/analytics/platform_learning.py content_generator/scheduler/daily.py
python - <<'PY'
from content_generator.core import learning_engine
from content_generator.analytics import platform_learning
print("performance log:", learning_engine._LOG_PATH)
print("published posts:", platform_learning.POSTS_PATH)
print("publishing ledger:", platform_learning.LEDGER_PATH)
assert str(learning_engine._resolve_learning_dir()) == str(platform_learning._resolve_learning_dir())
PY
```

The three printed files must resolve to the same persistent learning directory used by the live scheduler. This smoke check does not trigger publishing.

## Scheduler configuration review

For cron, use absolute paths and explicitly load the same environment file used by the application. For systemd, set `WorkingDirectory=` to the repository root, use the production virtualenv in `ExecStart=`, and load secrets with `EnvironmentFile=` (file permissions restricted to the service user). Never put API tokens directly into a committed unit file or crontab.

## First-day verification

1. Record the current Git commit deployed on Hostinger.
2. Run the safe smoke checks above.
3. Confirm the scheduler runs once at the intended time and that the output log points to the same persistent directory.
4. Confirm ledger reconciliation only imports `VERIFIED_LIVE` posts.
5. Check that the native platform API credentials/permissions exist for each platform. Missing permissions must remain explicitly unmeasured; they must not be converted into zero metrics.
6. After a scheduled run, inspect measurement status/snapshots and `performance_log.json`; do not declare the learning loop operational until actual measurements are recorded and the next generation's platform prompt includes the measured/provisional lesson.
