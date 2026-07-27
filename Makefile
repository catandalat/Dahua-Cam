.PHONY: up down api listener web test probe

up:
	docker compose -f infra/docker-compose.yml up --build

down:
	docker compose -f infra/docker-compose.yml down

api:
	PYTHONPATH=packages:apps uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

listener:
	PYTHONPATH=packages:apps python -m listener.main

web:
	cd apps/web && npm run dev

test:
	PYTHONPATH=packages:apps pytest -q

infra:
	docker compose -f infra/docker-compose.yml up -d postgres redis
