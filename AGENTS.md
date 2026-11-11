# Repository Guidelines

## Project Structure

This repository is a Django application. `sboi/` contains project settings, URL routing, middleware, and WSGI/ASGI entry points. Feature code is split into Django apps: `home/`, `members/`, `communications/`, `contact/`, `gallery/`, `blackboard/`, `notifications/`, `about/`, and `values/`. Each app keeps its models, views, URLs, migrations, and tests together. Shared templates are in `templates/`; frontend assets are in `static/`; uploaded and private files use `media/` and `private_media/`. Deployment guidance and integration notes are in `DEPLOYMENT.md` and `docs/`.

## Build, Test, and Development

Use Python 3 with dependencies from `requirements.txt` installed in a virtual environment. Run these commands from the repository root:

- `python manage.py runserver` starts the local development server.
- `python manage.py check` checks Django configuration and app wiring.
- `python manage.py makemigrations` creates migrations after model changes; inspect generated files before committing.
- `python manage.py migrate` applies database migrations locally.
- `python manage.py test` runs the Django test suite across the apps.

For production setup and static-file collection, follow `DEPLOYMENT.md` and use the production settings only where its instructions specify.

## Coding Style

Follow standard Python style: four spaces for indentation, `snake_case` for functions and variables, `PascalCase` for classes, and lowercase Django app/module names. Keep business logic in the relevant app and reuse its forms, services, and permission helpers rather than duplicating behavior in views. Name migrations with Django's generated numeric prefix and a short descriptive suffix. Match the surrounding template and static-file conventions when changing UI.

## Testing

Tests use Django's built-in test framework and live in each app's `tests.py` or focused `test_*.py` modules (for example, `home/test_permissions.py`). Name test methods `test_<behavior>` and cover permission-sensitive, form, and view changes. Run `python manage.py test <app_label>` for focused checks, then `python manage.py test` before submitting broader changes. No separate coverage threshold or lint command is configured in the repository.

## Commits and Pull Requests

Recent commit subjects are short, lowercase summaries (for example, `fixes`, `new features`, `membership update`). Keep commits focused and describe the change directly. Pull requests should explain user-visible behavior and relevant implementation choices, link an issue when available, include screenshots for UI changes, and note migration or configuration steps. Mention the checks you ran and any checks still needed.

## Configuration and Security

Use `.env.example` for production configuration and keep credentials in environment settings; never commit secrets from `.env`. Production loads `SECRET_KEY` from the environment, while local development generates a temporary key unless `DJANGO_SECRET_KEY` is set. Treat `private_media/` and member data as sensitive. Review migrations and access-control changes carefully before deployment.
