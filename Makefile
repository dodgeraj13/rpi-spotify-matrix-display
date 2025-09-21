help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package dependencies and request Spotify credentials
	python3 -m venv .venv
	.venv/bin/pip install -e .
	@rm -rf *.egg-info/
	@if grep -q "client_id = <YOUR_CLIENT_ID_HERE>" config.ini; then \
		echo "Please provide your Spotify API credentials:"; \
		echo "You can get these from: https://developer.spotify.com/dashboard"; \
		echo ""; \
		read -p "Enter Spotify Client ID: " client_id; \
		read -p "Enter Spotify Client Secret: " client_secret; \
		sed -i '' "s/client_id = <YOUR_CLIENT_ID_HERE>/client_id = $$client_id/" config.ini; \
		sed -i '' "s/client_secret = <YOUR_CLIENT_SECRET_HERE>/client_secret = $$client_secret/" config.ini; \
	fi
	@echo ""
	@echo "✅ rpi-spotify-matrix-display successfully installed!"
	@echo ""
	@echo "🧮 To run on an pi-connected matrix: \033[1;36mmake run\033[0m"
	@echo "🖥️ To run within an emulator window: \033[1;36mmake emulate\033[0m"

clean: ## Reset repo to a clean state
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: ## Run the display on a raspberry pi connected matrix
	.venv/bin/python main.py

emulate: ## Run the display within an emulator window
	.venv/bin/python main.py -e