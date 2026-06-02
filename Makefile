.PHONY: install db seed test run-api run-mcp run-cli clean

install:
	uv venv --python 3.12
	uv pip install -r requirements.txt

db:
	createdb part_registry 2>/dev/null || true
	psql part_registry -f migrations/001_init.sql
	psql part_registry -f migrations/002_add_scope_to_call_logs.sql

seed:
	.venv/bin/python scripts/seed.py

test:
	.venv/bin/pytest tests/ -v -W error

test-mcp:
	.venv/bin/python scripts/test_mcp.py

run-api:
	.venv/bin/python api/app.py

run-mcp:
	PART_API_KEY=sk-finance-team-key-001 .venv/bin/python mcp_server/app.py

run-cli:
	.venv/bin/python scripts/mcp_interactive.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v

clean:
	rm -rf .venv __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
