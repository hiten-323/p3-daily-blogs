# Security Policy

## Supported Versions

Security fixes are applied to the default branch. Deployments should use a reviewed,
green commit from `main`; do not deploy from an unreviewed feature branch.

## Reporting a Vulnerability

Please do not publish credentials, access tokens, customer data, or exploitable details
in a public issue. Use GitHub's private vulnerability reporting for this repository
when available. If private reporting is unavailable, contact the repository owner
through a private channel and include a minimal reproduction.

## Secret Handling

- Store provider and platform credentials only in GitHub Actions secrets or an
  approved secret manager.
- Never commit `.env`, token files, OAuth refresh tokens, service-account files,
  or raw API responses containing credentials.
- Rotate any credential that may have been exposed; removing it from Git history
  does not invalidate it.
- Workflows must use least-privilege permissions and must not print secret values.

## Production Changes

- Require CI and security checks before merging application code.
- Keep autonomous publishing disabled until platform permissions, media quality,
  attribution, alert delivery, and a controlled publication/read-back are verified.
