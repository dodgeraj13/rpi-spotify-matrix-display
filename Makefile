install: ## Install package dependencies and request Spotify credentials
	python3 -m venv .venv
	.venv/bin/pip install -e .
	@rm -rf *.egg-info/
	@if grep -q "client_id = <YOUR_CLIENT_ID_HERE>" config.ini; then \
		echo ""; \
		echo "Please provide your Spotify API credentials:"; \
		echo "You can obtain these from: https://developer.spotify.com/dashboard"; \
		echo ""; \
		read -p "Enter Spotify Client ID: " client_id; \
		read -p "Enter Spotify Client Secret: " client_secret; \
		sed "s/client_id = <YOUR_CLIENT_ID_HERE>/client_id = $$client_id/" config.ini > config.ini.tmp && mv config.ini.tmp config.ini; \
		sed "s/client_secret = <YOUR_CLIENT_SECRET_HERE>/client_secret = $$client_secret/" config.ini > config.ini.tmp && mv config.ini.tmp config.ini; \
	fi
	@echo ""
	@echo "✅ rpi-spotify-matrix-display successfully installed!"
	@echo ""
	@echo "🧮 To run on an pi-connected matrix: \033[1;36mmake run\033[0m"
	@echo "🖥️ To run within an emulator window: \033[1;36mmake emulate\033[0m"

build-matrix: ## Build rpi-rgb-led-matrix and install its python bindings
	@if ! dpkg -s python3-dev >/dev/null 2>&1; then \
		echo "📦 Installing python3-dev..."; \
		sudo apt-get update && sudo apt-get install -y python3-dev; \
	fi
	@if ! dpkg -s cython3 >/dev/null 2>&1; then \
		echo "📦 Installing cython3..."; \
		sudo apt-get update && sudo apt-get install -y cython3; \
	fi
	@if [ ! -f rpi-rgb-led-matrix/bindings/python/rgbmatrix/_rgbmatrix.cpython-*.so ]; then \
		echo "🔨 Building rpi-rgb-led-matrix..."; \
		cd rpi-rgb-led-matrix && \
			make -C bindings/python/rgbmatrix -B CYTHON=cython3 && \
			make; \
	fi
	@if ! .venv/bin/python -c "import rgbmatrix" >/dev/null 2>&1; then \
		echo "📦 Installing Python bindings..."; \
		.venv/bin/pip install rpi-rgb-led-matrix/bindings/python --use-pep517; \
	fi

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean: ## Reset repo to a clean state
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run: build-matrix ## Run the display on a raspberry pi connected matrix
	.venv/bin/python main.py

emulate: ## Run the display within an emulator window
	.venv/bin/python main.py -e