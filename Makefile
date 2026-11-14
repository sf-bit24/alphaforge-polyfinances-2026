install:
	python -m pip install -r requirements.txt

run:
	streamlit run app/main.py

test:
	pytest -q

lint:
	ruff check app brain tests

format:
	black app brain tests
