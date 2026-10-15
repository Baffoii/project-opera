# One-command CI-style check. Needs Node >=24 on PATH and backend/.venv (see README "Running OPERA").
.PHONY: test test-backend test-frontend test-upstream
test: test-backend test-frontend test-upstream

test-backend:
	cd backend && .venv/bin/pytest

test-frontend:
	npx vitest run

test-upstream:
	npm run check:boundaries
	npm run format:check
	npm test
