# Test report

Date: 2026-10-24

## Backend

Command (from `backend`): `python -m pytest -q`

Result: **5 passed, 1 third-party deprecation warning, 0 failures** (1.03 seconds).

Covered behavior: protected endpoints and invalid token; registration and duplicate account; valid and invalid login; role restrictions; vehicle creation, listing, update, deletion and missing ID; combined search filters and invalid price range; vehicle validation; purchase until sold out; forbidden and valid restock; two concurrent purchase attempts for the last vehicle; persistence across separate database connections.

## Frontend

Command (from `frontend`): `npm run build`

Result: **passed**. Vite v5.4.21 transformed 1,580 modules and emitted a production bundle.

## Limits

Automated browser interaction and final application screenshots could not be completed in this workspace. The frontend build and API tests passed, but the owner should run the UI in their own browser, capture genuine screenshots, and check responsive behavior before submission.
