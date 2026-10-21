# Roadmap

None of these stages are implemented. The current code is the foundation they can sit on: one process, explicit modules, PostgreSQL migrations, and a Redis service that the API does not use yet.

## 1. Python fundamentals and testing

Learn the language by reading and changing this codebase. Follow `docs/LEARNING_GUIDE.md`, run the unit tests, and make a small behavior change that turns a test red before it turns green. Stay inside the users service and its tests. Do not add a feature from a later stage in order to have something to practice on.

## 2. Backend architecture and PostgreSQL

This stage is the work already sketched by the layout: FastAPI, async SQLAlchemy, Alembic, and a real users slice. Deepen it by reading a request from `app/main.py` through commit, applying the initial migration yourself, and inspecting `users` in `psql`. The next practice step is a reviewed migration for a column you can justify, not a new bounded context.

## 3. Appointments, scheduling rules, and waitlist

Add `app/modules/appointments/` as real Python only when the scheduling rules are specified. The README there is a placeholder so the package is not mistaken for a working feature. This stage covers appointment records, conflict rules, and a waitlist. It depends on a real authentication stage before it stores clinic data. It should follow the same router, service, repository, and migration path as users.

## 4. Authentication, roles, and audit logging

Replace the anonymous users example with an account model: credentials stored with a password hash, sessions or tokens, roles, and an audit trail for writes. Until this exists, the service must not be deployed with personal data. Authorization checks belong in services or dedicated dependencies, not in copied `if` statements across routers. Audit logging must follow the same rule as the current logger: no passwords, tokens, or raw personal data in the log line.

## 5. Admin interface

An admin UI over the authenticated API. It is a client of this backend, not a second place where scheduling rules live. The backend remains the source of truth for validation and permissions.

## 6. Background jobs and notifications using Redis/Celery

Introduce a worker only when a job exists. Redis is already in Compose, and `REDIS_URL` is already a setting, so the worker can share configuration without a rewrite. Celery is not a dependency today. Jobs should call services with their own database sessions. They should not import FastAPI routers. Notification delivery belongs here rather than in the request that triggered it.

## 7. AI integrations and document extraction

`app/modules/ai/` and `app/modules/documents/` describe the boundary. Provider SDKs stay behind a service in the AI module. Document extraction stores metadata and structured results. Routers do not call a provider. No LLM framework or vector database is installed now; add one when a concrete extraction flow needs it.

## 8. External integrations

Clinic systems, calendars, and other third-party APIs. Each integration gets an adapter called by a service, with timeouts and explicit error mapping. Do not scatter HTTP clients through routers. Secrets stay in the environment, on the same pattern as `DATABASE_URL`.

## 9. Video event intelligence using Raspberry Pi, GStreamer, and a Python processing module

Capture and processing run beside the API, on a device pipeline (Raspberry Pi, GStreamer, and a Python processing step). `app/modules/video/` should ingest events that the pipeline has already produced. The API process should not embed a media server. The processing code can live in its own module or worker and should reuse the database session factory rather than a second schema tool.

## 10. Deployment, monitoring, security, and production hardening

Ship the single backend process with reviewed migrations, real secrets, and the authentication stage already done. Add process monitoring, request correlation, backup and restore, dependency updates, and a security pass over headers, data retention, and logs. `/health/live` and `/health/ready` are the probe split to build on. Ready still needs a conscious decision about whether production readiness should also require the current Alembic revision.
