# Rahat komandalar toplusu
# İstifadə: make <hədəf>

VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

.PHONY: install run test smoke compose-up compose-down

install: ## Virtual mühit yarat və asılılıqları qur
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt

run: ## Tətbiqi lokal işə sal (mock rejimində açarsız işləyir)
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test: ## Bütün testləri işə sal
	$(PY) -m pytest tests/ -v

smoke: ## Uçdan-uca smoke test (serveri özü qaldırır)
	$(PY) scripts/smoke_test.py

compose-up: ## Docker ilə bütün stack-i qaldır (app + Qdrant + n8n)
	docker compose up -d --build

compose-down: ## Docker stack-i dayandır
	docker compose down
