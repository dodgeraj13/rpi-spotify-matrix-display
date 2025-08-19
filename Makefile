help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package dependencies
	python3 -m venv .venv
	.venv/bin/pip install -e .
	@rm -rf *.egg-info/
	@echo ""
	@echo "✅ rpi-spotify-matrix-display successfully installed!"
	@echo ""
	@make help

clean: ## Reset repo to a clean state
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the display on a raspberry pi connected matrix
	python main.py

emulate: ## Run the display in an emulator window
	python main.py -e

run-fullscreen: ## Run the display on a raspberry pi connected matrix with fullscreen artwork
	python main.py -f

emulate-fullscreen: ## Run the display in an emulator window with fullscreen artwork
	python main.py -ef