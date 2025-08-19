help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package dependencies
	pip install -e .

clean: ## Clean build folder and virtual environment
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the display on a raspberry pi connected matrix
	python main.py

run-emulator: ## Run the display in an emulator window
	python main.py -e

run-fullscreen: ## Run the display on a raspberry pi connected matrix with fullscreen artwork
	python main.py -f

run-emulator-fullscreen: ## Run the display in an emulator window with fullscreen artwork
	python main.py -ef