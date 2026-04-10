install: ## Install dependencies and request Spotify credentials
	git submodule update --init --recursive --depth 1
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e . -e ./deps/librelyrics -e ./deps/librelyrics-spotify
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

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean: ## Reset repo to a clean state
	@echo "🧹 Resetting repo to a clean state...";
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || sudo rm -rf {} +
	find . -type f -name "*.pyc" -exec rm -f {} + 2>/dev/null || sudo rm -f {} +
	git submodule deinit --all -f
	@if [ -f /etc/systemd/system/matrix.service ]; then \
		echo "🗑 Removing matrix systemd service..."; \
		sudo systemctl stop matrix || true; \
		sudo systemctl disable matrix || true; \
		sudo rm /etc/systemd/system/matrix.service; \
		sudo systemctl daemon-reload; \
	fi
	@if grep -q "alias matrix=" ~/.bash_aliases 2>/dev/null; then \
		echo "🗑 Removed 'matrix' alias from ~/.bash_aliases"; \
		sed "/alias matrix=/d" ~/.bash_aliases > ~/.bash_aliases.tmp && mv ~/.bash_aliases.tmp ~/.bash_aliases; \
	fi
	@echo "✅ Repo cleaned."

emulate: ## Run the display within an emulator window
	.venv/bin/python main.py --emulate

## RASPBERRY PI SPECIFIC TARGETS ##

run: rpi-bindings rpi-service ## Run the display on a raspberry pi connected matrix
	@echo "▶️ Starting Spotify Matrix Display..."
	sudo .venv/bin/python main.py

rpi-bindings: ## Raspberry Pi ONLY - Install required python bindings
	@if ! dpkg -s python3-dev >/dev/null 2>&1; then \
		echo "📦 Installing python3-dev..."; \
		sudo apt-get update && sudo apt-get install -y python3-dev; \
	fi
	@if ! dpkg -s cmake >/dev/null 2>&1; then \
		echo "📦 Installing cmake..."; \
		sudo apt-get update && sudo apt-get install -y cmake; \
	fi
	@if ! .venv/bin/python -c "import rgbmatrix" >/dev/null 2>&1; then \
		echo "🔨 Building and installing rpi-rgb-led-matrix..."; \
		cd deps/rpi-rgb-led-matrix && make; \
		.venv/bin/pip install ./deps/rpi-rgb-led-matrix; \
	fi

rpi-service: ## Raspberry Pi ONLY - Set up systemd service and alias
	@if [ ! -f /etc/systemd/system/matrix.service ]; then \
		echo "⚙️ Installing systemd service..."; \
		sudo cp /home/pi/rpi-spotify-matrix-display/matrix.service /etc/systemd/system/matrix.service; \
		echo "🔄 Reloading systemd..."; \
		sudo systemctl daemon-reload; \
		echo "✅ Enabling matrix service..."; \
		sudo systemctl enable matrix; \
		echo "🎉 Matrix service installed!"; \
	fi
	@if ! grep -q "alias matrix=" ~/.bash_aliases 2>/dev/null; then \
		echo "⚡ Adding alias 'matrix' to ~/.bash_aliases..."; \
		echo "alias matrix='sudo service matrix'" >> ~/.bash_aliases; \
		source ~/.bash_aliases; \
		echo "Use matrix start|stop|restart to control it."; \
		echo ""; \
	fi

rpi-optimize: ## Raspberry Pi ONLY - Optimize matrix performance (OPTIONAL)
	@read -p "⚠️ Would you like to reserve a CPU core for the display and disable onboard audio to optimize performance? [y/N]: " proceed; \
	if [ "$$proceed" != "y" ] && [ "$$proceed" != "Y" ]; then \
		echo "Optimization aborted by user."; \
		exit 0; \
	fi; \
	changed=0; \
	if ! grep -q "isolcpus=3" /boot/firmware/cmdline.txt; then \
		echo "⚙️  Adding isolcpus=3 to /boot/firmware/cmdline.txt..."; \
		sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.tmp; \
		sudo sed -i 's/$$/ isolcpus=3/' /boot/firmware/cmdline.txt.tmp; \
		sudo mv /boot/firmware/cmdline.txt.tmp /boot/firmware/cmdline.txt; \
		echo "✅ isolcpus=3 added."; \
		changed=1; \
	fi; \
	if ! grep -q "^blacklist snd_bcm2835" /etc/modprobe.d/alsa-blacklist.conf 2>/dev/null; then \
		echo "⚙️  Blacklisting onboard audio (snd_bcm2835)..."; \
		echo "blacklist snd_bcm2835" | sudo tee -a /etc/modprobe.d/alsa-blacklist.conf > /dev/null; \
		echo "✅ snd_bcm2835 blacklisted."; \
		changed=1; \
	fi; \
	if ! grep -q "^dtparam=audio=off" /boot/firmware/config.txt; then \
		echo "⚙️  Disabling onboard audio in config.txt..."; \
		sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' /boot/firmware/config.txt || true; \
		if ! grep -q "^dtparam=audio=off" /boot/firmware/config.txt; then \
			echo "dtparam=audio=off" | sudo tee -a /boot/firmware/config.txt > /dev/null; \
		fi; \
		echo "✅ Onboard audio disabled."; \
		changed=1; \
	fi; \
	if [ $$changed -eq 1 ]; then \
		echo "🔄 Please reboot your Raspberry Pi for changes to take effect."; \
		echo ""; \
		read -p "Reboot now? [y/N]: " ans; \
		if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
			echo "Rebooting..."; \
			sudo reboot; \
		else \
			echo "Reboot skipped. Remember to reboot manually later."; \
		fi; \
	fi