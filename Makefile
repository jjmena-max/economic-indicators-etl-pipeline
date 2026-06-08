.PHONY: install dev test lint run export clean docker-up docker-down

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check .

run:
	python scripts/run_pipeline.py

export:
	python scripts/run_pipeline.py --export data/sample_economic_indicators.csv

clean:
	rm -f *.db
	rm -rf .pytest_cache .ruff_cache **/__pycache__

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
