# Architecture

This is a modular monolith: one deployable Python process. HTTP routing, business rules, database access, and request validation are separate. There is no service mesh, no generic repository framework, and no background worker yet.

Authentication and authorization are not implemented. The users module is a technical example so the layout, transactions, and tests have a real vertical slice. Do not treat it as an account system.

## Layout adjustments

The tree matches the requested shape, with two small files added so the layers stay importable later:

- `app/api/deps.py` holds the FastAPI session dependency. `app/db/session.py` only builds an engine and a session factory, so a future worker can import it without importing FastAPI.
- `app/api/errors.py` maps failures onto the JSON error envelope. Domain exception types stay in `app/core/exceptions.py`, so services do not import FastAPI.

`common/` is omitted. Shared code that exists today already has a home in `core`, `db`, or `api`. `scripts/` is omitted. The setup commands are in the README because they are not a program of their own.

`app/modules/appointments/`, `documents/`, `ai/`, and `video/` contain a README and no Python modules. Appointments are a later roadmap item. Empty routers, models, and repositories would look like a feature that exists and would give new code nothing real to call.

## Responsibilities

| Module | Owns | Does not own |
| --- | --- | --- |
| `app/main.py` | Process composition, lifespan, access log | Business rules |
| `app/api/router.py` | Mounting versioned routers | SQL and rules |
| `app/api/health.py` | `/health/live` and `/health/ready` | Schema version checks |
| `app/api/deps.py` | Request transaction | Query details |
| `app/api/errors.py` | HTTP status and error JSON | Deciding the rule that failed |
| `app/core/config.py` | Environment settings | Connections |
| `app/core/logging.py` | JSON log format | Request bodies |
| `app/core/exceptions.py` | `NotFoundError`, `ConflictError`, `DomainValidationError` | Status wiring |
| `app/db/base.py` | Metadata and constraint names | Feature tables |
| `app/db/session.py` | Engine and session factory | FastAPI |
| `app/modules/users/` | User HTTP, rules, and SQL | Passwords, sessions, roles |
| `migrations/` | Reviewed schema changes | Application startup |

Feature modules do not import each other. `app/db` does not import feature models. `migrations/env.py` imports models because it is the migration composition root. When a new model is added, it has to be imported there or Alembic will not see the table.

## Dependency direction

```text
uvicorn
  -> app.main.create_app
       -> api routers
            -> module services
                 -> module repositories
                      -> SQLAlchemy models
                           -> app.db.base
       -> core.config / core.logging / core.exceptions
       -> db.session (engine lifecycle only)
```

Routers translate HTTP into service calls and translate entities into Pydantic schemas. Services enforce rules and never see a `Request`. Repositories run SQL and let database exceptions surface. The service translates a duplicate-key `IntegrityError` into `ConflictError` so the race and the pre-check produce the same outcome.

## Request lifecycle

`POST /api/v1/users` with a JSON body:

1. Uvicorn hands the request to the FastAPI app created by `create_app`.
2. `AccessLogMiddleware` records method, path, status, and duration after the response starts. It does not read the body or the query string.
3. The router in `app/modules/users/router.py` matches `/users` under the `/api/v1` prefix.
4. Pydantic validates the body as `UserCreate`. Unknown fields are rejected. Whitespace is stripped. This is request validation, not the business rule.
5. FastAPI resolves `get_user_service`, which depends on `get_db_session`. One `AsyncSession` is opened for the request.
6. `UserService.create_user` strips and checks the display name, lowercases the email, and rejects a known duplicate.
7. `UserRepository.add` flushes an `INSERT`. A unique-constraint failure becomes `ConflictError`.
8. The router builds `UserRead` from the entity. The entity is not returned directly.
9. If the route returns, the session dependency commits. If it raises, the dependency rolls back and `app/api/errors.py` writes the error envelope.
10. The access log line is written.

Health routes are registered on the application root, not on `api_router`. Probes should keep working when `/api/v1` changes. `/health/live` does not take a session. `/health/ready` borrows a connection from the engine and runs `SELECT 1`. Readiness means the server can reach Postgres. It does not mean the latest Alembic revision is applied.

`redirect_slashes` is off. `/api/v1/users/` is a 404, not a redirect.

## Database session lifecycle

`lifespan` in `app/main.py` builds one async engine and one `async_sessionmaker`, stores them on `app.state`, and calls `engine.dispose()` on shutdown. Nothing global holds the engine. The module-level name `app` exists because Uvicorn imports `app.main:app`. Tests call `create_app(settings)` and get a separate instance.

`get_db_session` is the transaction boundary:

- Entering the dependency opens a session.
- The repository may `flush`, which sends SQL and runs constraints before the route returns.
- A normal return commits during dependency cleanup, after the path function has returned.
- Any exception rolls the session back, then the exception continues to the HTTP handler.

There is no `create_all()` path. Schema changes are Alembic revisions applied by an explicit command. The initial revision was written to match `User.__table__` and is covered by `tests/unit/test_metadata.py`. Later revisions should be autogenerated, then read, from the repository root:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

`DATABASE_URL` is read from settings inside `migrations/env.py`. `alembic.ini` does not contain a password. The URL must use the `postgresql+asyncpg` driver. A sync driver or SQLite is rejected so the runtime and the tests stay on the same stack.

`expire_on_commit` is false. After a commit, response code can still read attributes that were loaded. An async session cannot lazy-load, and an expired attribute would raise.

SQL echo is off in every environment. An `INSERT` log line would contain the email address.

## Settings and logs

`Settings` is a pydantic-settings model. Process environment variables override `.env`. `get_settings()` is cached for the process because the values do not change at runtime. That cache is the only intentional process-level singleton, and it stores configuration, not entities or connections. Tests that change variables call `get_settings.cache_clear()`.

`redis_url` is part of settings so a worker can share configuration later. No module reads it today.

Production with `DEBUG=true` fails at startup.

The log formatter allows only `error_type`, `error_frames`, `http_method`, `path`, `status_code`, and `duration_ms` as extra fields. Exception messages are not written. Database drivers put the DSN and bound parameters, including emails, in those messages. A readiness failure logs the exception class and a static sentence.

## Errors

| Situation | Status | `error.code` |
| --- | --- | --- |
| Body or query fails Pydantic | 422 | `validation_error` |
| Service rejects a value | 422 | `domain_validation_error` |
| Duplicate email | 409 | `duplicate_email` |
| Unknown user id | 404 | `user_not_found` |
| Unknown path | 404 | `route_not_found` |
| Unhandled exception | 500 | `internal_error` |

Clients of the HTTP API normally see `validation_error` for bad input, because the schema runs first. `domain_validation_error` is what a direct service call raises. Unit tests cover that path. The 500 body is generic. The server log gets the exception type and file:line frames, not the exception text.

## Users

`users` has `id`, `display_name`, `email`, `is_active`, `created_at`, and `updated_at`. `id` is a UUID generated in the service so the value exists before the insert. Emails are stored lowercase. The column itself is case-sensitive; the service normalizes first, and `uq_users_email` rejects a race that the lookup missed. Display names are stripped, must be non-blank, and are at most 120 characters. `is_active` defaults to true and can be set false. Inactive rows are still returned. There is no filter that hides them, because that would be a product rule this slice does not have.

`updated_at` is maintained by the ORM (`onupdate`) plus a server default. There is no update route yet, and there is no database trigger. That is acceptable while this process is the only writer. A trigger belongs with the first feature that updates rows outside the ORM.

List results are ordered by `created_at` descending, then `id` descending. `limit` defaults to 50 and cannot exceed 100. `total` is the count of all rows, not the page size.

## How to add a module

1. Create `app/modules/<name>/` with `router.py`, `schemas.py`, `models.py`, `repository.py`, and `service.py` only when each file has real behavior.
2. Put invariants in the service. Keep the router limited to status codes, dependencies, and schema mapping.
3. Include the router from `app/api/router.py`.
4. Import the model from `migrations/env.py`.
5. Generate a revision, read the SQL, and add a metadata assertion if the table shape is easy to get wrong.
6. Add service tests with an in-memory stand-in and API tests that use `TEST_DATABASE_URL`.

Do not import another feature module to share a helper. If two modules need the same policy, promote a concrete function into `core` when the second caller exists.

## What is deliberately absent

- Celery, RQ, or any job runner. Redis is only a Compose service and a setting.
- LLM clients, vector databases, and object storage.
- A frontend.
- A base repository class or a unit-of-work framework. The session dependency is the unit of work.
- Startup migrations. A crashed migration should not be hidden inside a rolling restart.
- Authentication middleware. Adding a fake `get_current_user` that always succeeds would teach the wrong shape.

A later worker should build `Settings`, call `create_db_engine`, open a session, and call a service. It should not call a route function. That is why services take plain values instead of Pydantic request models.

Video and AI code should arrive as their own modules. The API process should accept results or enqueue work. It should not host a GStreamer pipeline or a provider SDK in a request handler. Those dependencies are absent so they are a deliberate addition later, not an unused import now.
