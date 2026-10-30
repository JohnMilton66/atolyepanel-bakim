# Security and deployment checklist

This repository is for **fictional/demo data only** until security and organizational approvals are completed.

- This is a *private* source repository. Do not commit `.env`, any `data/`, `session.key`, passwords, database URIs, personal tokens, actual aircraft registrations, technician data or customer records. `.gitignore` excludes these paths.
- Vercel requires externally managed persistent PostgreSQL via `DATABASE_URL`; do not use local SQLite on Vercel. Never paste your real connection URI into a chat or GitHub code.
- Vercel Environment Variables must contain `DATABASE_URL`, `TRACKER_SESSION_SECRET` (random >=32 chars) and `SECURE_COOKIES=1`.
- Demo users are ONLY seeded by explicit `python app.py demo` on local SQLite and cannot be seeded on Vercel/PostgreSQL. `init-admin` is an explicit trusted-operator operation.
- Security gaps **not yet resolved**: in-memory login throttling is unsuitable for multiple serverless instances; no MFA/SSO, no distributed rate limits, no dedicated security audit, no Postgres integration test, no backup/restore drill. Do not treat this app as production-grade.
- Keep Vercel preview and project access restricted until security controls and tests are complete.
- Do not share passwords or tokens in ChatGPT. Authorize GitHub and Vercel through their own OAuth flows.
