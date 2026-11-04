#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# LinuxIsland Quick Setup
# Version: 1.0.0
# ============================================================

VERSION="1.0.0"
BARE=false
APT_UPDATED=false
PACKAGE_MANAGER=""
DISTRO="Unknown Linux distribution"

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# ============================================================
# ARGUMENTS
# ============================================================

for arg in "$@"; do
    case "$arg" in
        --bare)
            BARE=true
            ;;
        --help|-h)
            cat <<EOF
LinuxIsland Quick Setup v${VERSION}

Usage:
  ./quicksetup.sh
  ./quicksetup.sh --bare

Options:
  --bare     Use plain text instead of FIGlet.
  --help     Display this help message.

The script installs dependencies and configures automatic startup
(Hyprland exec-once, systemd user services, or shell profile).
EOF
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$arg" >&2
            exit 2
            ;;
    esac
done

# ============================================================
# TERMINAL STYLING
# ============================================================

if [[ -t 1 ]]; then
    RESET='\033[0m'
    BOLD='\033[1m'
    DIM='\033[2m'
    CYAN='\033[38;5;45m'
    BLUE='\033[38;5;39m'
    GREEN='\033[38;5;82m'
    YELLOW='\033[38;5;220m'
    RED='\033[38;5;196m'
    WHITE='\033[97m'
else
    RESET='' BOLD='' DIM='' CYAN=''
    BLUE='' GREEN='' YELLOW='' RED='' WHITE=''
fi

# ============================================================
# UI FUNCTIONS
# ============================================================

line() {
    printf "${DIM}────────────────────────────────────────────────────────${RESET}\n"
}

info() {
    printf " ${CYAN}◆${RESET} %s\n" "$*"
}

success() {
    printf " ${GREEN}✔${RESET} %s\n" "$*"
}

warning() {
    printf " ${YELLOW}⚠${RESET} %s\n" "$*"
}

error() {
    printf " ${RED}✖${RESET} %s\n" "$*" >&2
}

section() {
    printf "\n${BOLD}${CYAN}  %s${RESET}\n" "$*"
    line
}

confirm() {
    local answer

    while true; do
        printf "${YELLOW}%s [y/N]: ${RESET}" "$1"
        read -r answer || answer=""

        case "$answer" in
            y|Y|yes|YES) return 0 ;;
            n|N|no|NO|"") return 1 ;;
            *) warning "Please answer yes or no." ;;
        esac
    done
}

# ============================================================
# MAKE SHELL SCRIPTS EXECUTABLE
# ============================================================

section "PROJECT PREPARATION"

if ! find "$PROJECT_DIR" \
    -type d -name .git -prune -o \
    -type f -name '*.sh' -exec chmod +x {} +; then
    error "Could not set executable permissions on shell scripts."
    exit 1
fi

success "All project shell scripts are executable."

# ============================================================
# DISTRIBUTION DETECTION
# ============================================================

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    DISTRO="${PRETTY_NAME:-Unknown Linux distribution}"
fi

if command -v apt-get >/dev/null 2>&1; then
    PACKAGE_MANAGER="apt"
elif command -v pacman >/dev/null 2>&1; then
    PACKAGE_MANAGER="pacman"
elif command -v dnf >/dev/null 2>&1; then
    PACKAGE_MANAGER="dnf"
else
    PACKAGE_MANAGER="unknown"
fi

# ============================================================
# PRIVILEGE HANDLING
# ============================================================

if [[ "$EUID" -eq 0 ]]; then
    SUDO=()
elif command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
else
    error "sudo is unavailable."
    printf "\nRun this script as root or install sudo.\n"
    exit 1
fi

# ============================================================
# MANUAL INSTALLATION FALLBACK
# ============================================================

manual_fallback() {
    local reason="$1"

    printf "\n"
    error "Automatic installation cannot continue."
    warning "$reason"

    section "MANUAL DEPENDENCIES"

    case "$PACKAGE_MANAGER" in
        apt)
            printf "${BOLD}Ubuntu / Debian${RESET}\n\n"
            printf "  python3\n"
            printf "  python3-gi\n"
            printf "  python3-cairo\n"
            printf "  python3-pyudev\n"
            printf "  gir1.2-gtk-3.0\n"
            printf "  gir1.2-gtk-layer-shell-0.1\n"
            printf "  libgtk-3-0\n"
            printf "  libgtk-layer-shell0\n"
            [[ "$BARE" == false ]] && printf "  figlet\n"
            printf "\n"
            printf "Install with:\n\n"
            printf "  sudo apt install python3 python3-gi python3-cairo \\\\\n"
            printf "    python3-pyudev gir1.2-gtk-3.0 \\\\\n"
            printf "    gir1.2-gtk-layer-shell-0.1 \\\\\n"
            printf "    libgtk-3-0 libgtk-layer-shell0"
            [[ "$BARE" == false ]] && printf " figlet"
            printf "\n"
            ;;
        pacman)
            printf "${BOLD}Arch Linux${RESET}\n\n"
            printf "  python\n"
            printf "  python-gobject\n"
            printf "  python-cairo\n"
            printf "  python-pyudev\n"
            printf "  gtk3\n"
            printf "  gtk-layer-shell\n"
            [[ "$BARE" == false ]] && printf "  figlet\n"
            printf "\n"
            printf "Install with:\n\n"
            printf "  sudo pacman -S python python-gobject python-cairo \\\\\n"
            printf "    python-pyudev gtk3 gtk-layer-shell"
            [[ "$BARE" == false ]] && printf " figlet"
            printf "\n"
            ;;
        dnf)
            printf "${BOLD}Fedora${RESET}\n\n"
            printf "  python3\n"
            printf "  python3-gobject\n"
            printf "  python3-cairo\n"
            printf "  python3-pyudev\n"
            printf "  gtk3\n"
            printf "  gtk-layer-shell\n"
            [[ "$BARE" == false ]] && printf "  figlet\n"
            printf "\n"
            printf "Install with:\n\n"
            printf "  sudo dnf install python3 python3-gobject \\\\\n"
            printf "    python3-cairo python3-pyudev \\\\\n"
            printf "    gtk3 gtk-layer-shell"
            [[ "$BARE" == false ]] && printf " figlet"
            printf "\n"
            ;;
        *)
            printf "  Python 3\n"
            printf "  PyGObject\n"
            printf "  Pycairo\n"
            printf "  PyUDev\n"
            printf "  GTK 3\n"
            printf "  GTK Layer Shell\n"
            printf "  GObject Introspection\n"
            [[ "$BARE" == false ]] && printf "  FIGlet\n"
            printf "\n"
            printf "Your distribution's native package manager must be used.\n"
            ;;
    esac

    printf "\n"
    warning "No pip installation was attempted."
    warning "Install the dependencies manually, then rerun quicksetup.sh."
    exit 1
}

# ============================================================
# PACKAGE MANAGER
# ============================================================

refresh_package_index() {
    if [[ "$PACKAGE_MANAGER" == "apt" && "$APT_UPDATED" == false ]]; then
        info "Refreshing APT package indexes..."

        if ! "${SUDO[@]}" apt-get update; then
            return 1
        fi

        APT_UPDATED=true
    fi
}

install_packages() {
    case "$PACKAGE_MANAGER" in
        apt)
            refresh_package_index || return 1
            "${SUDO[@]}" apt-get install -y "$@"
            ;;
        pacman)
            "${SUDO[@]}" pacman -S --needed --noconfirm "$@"
            ;;
        dnf)
            "${SUDO[@]}" dnf install -y "$@"
            ;;
        *)
            return 1
            ;;
    esac
}

# ============================================================
# STAGE 1 — FIGLET BOOTSTRAP
# ============================================================

if [[ "$PACKAGE_MANAGER" == "unknown" ]]; then
    manual_fallback "No supported package manager was detected."
fi

if [[ "$BARE" == false ]]; then

    if ! command -v figlet >/dev/null 2>&1; then

        section "FIGLET BOOTSTRAP"

        warning "FIGlet is not installed."
        info "FIGlet must be installed before the main setup."

        if ! confirm "Install FIGlet now?"; then
            error "Normal setup requires FIGlet."
            printf "\nRun: ./quicksetup.sh --bare\n\n"
            exit 1
        fi

        if ! install_packages figlet; then
            manual_fallback "FIGlet could not be installed. Your environment may not support normal package installation."
        fi

        if ! command -v figlet >/dev/null 2>&1; then
            manual_fallback "FIGlet was installed but its executable could not be found."
        fi

        success "FIGlet installed."
    else
        success "FIGlet is already installed."
    fi

fi

# ============================================================
# HEADER
# ============================================================

clear 2>/dev/null || true

if [[ "$BARE" == true ]]; then
    printf "${CYAN}${BOLD}LINUXISLAND${RESET}\n"
else
    printf "${CYAN}${BOLD}"
    figlet "LinuxIsland"
    printf "${RESET}"
fi

printf "\n"
printf "  ${WHITE}${BOLD}QUICK SETUP${RESET} ${DIM}v${VERSION}${RESET}\n"
printf "  ${DIM}Interactive dependency installer${RESET}\n"
printf "\n"
line

# ============================================================
# STAGE 2 — SYSTEM INFORMATION
# ============================================================

section "SYSTEM INFORMATION"

info "Distribution: $DISTRO"
info "Package manager: $PACKAGE_MANAGER"
info "Project directory: $PROJECT_DIR"

if command -v python3 >/dev/null 2>&1; then
    success "Python: $(python3 --version)"
else
    warning "Python 3 is not installed."
fi

if [[ "$BARE" == true ]]; then
    warning "Bare mode enabled."
fi

# ============================================================
# STAGE 3 — DEPENDENCY RESOLUTION
# ============================================================

section "DEPENDENCY RESOLUTION"

printf "  ${BOLD}Python dependencies${RESET}\n"
printf "    • PyGObject\n"
printf "    • Pycairo\n"
printf "    • PyUDev\n\n"

printf "  ${BOLD}System dependencies${RESET}\n"
printf "    • Python 3\n"
printf "    • GTK 3\n"
printf "    • GTK Layer Shell\n"
printf "    • GObject Introspection\n\n"

# Resolve distribution-specific package names.

case "$PACKAGE_MANAGER" in

    apt)
        refresh_package_index ||
            manual_fallback "APT package index refresh failed."

        LAYER_GIR=""

        for candidate in \
            gir1.2-gtk-layer-shell-0.1 \
            gir1.2-gtklayershell-0.1
        do
            if apt-cache show "$candidate" >/dev/null 2>&1; then
                LAYER_GIR="$candidate"
                break
            fi
        done

        if [[ -z "$LAYER_GIR" ]]; then
            manual_fallback "No GTK Layer Shell introspection package was found in the configured APT repositories."
        fi

        PACKAGES=(
            python3
            python3-gi
            python3-cairo
            python3-pyudev
            gir1.2-gtk-3.0
            "$LAYER_GIR"
            libgtk-3-0
            libgtk-layer-shell0
        )
        ;;

    pacman)
        PACKAGES=(
            python
            python-gobject
            python-cairo
            python-pyudev
            gtk3
            gtk-layer-shell
        )
        ;;

    dnf)
        PACKAGES=(
            python3
            python3-gobject
            python3-cairo
            python3-pyudev
            gtk3
            gtk-layer-shell
        )
        ;;

esac

# ============================================================
# STAGE 4 — CONFIRMATION
# ============================================================

section "INSTALLATION SUMMARY"

info "Package manager: $PACKAGE_MANAGER"

printf "\n"
printf "  Packages to install:\n"

for package in "${PACKAGES[@]}"; do
    printf "    • %s\n" "$package"
done

printf "\n"

if ! confirm "Proceed with installation?"; then
    warning "Installation cancelled."
    exit 0
fi

# ============================================================
# STAGE 5 — INSTALLATION
# ============================================================

section "INSTALLING DEPENDENCIES"

if ! install_packages "${PACKAGES[@]}"; then
    manual_fallback "The package manager failed to install one or more dependencies. This can happen in restricted containers, immutable systems, or unsupported environments."
fi

success "Package installation completed."

# ============================================================
# STAGE 6 — VERIFICATION
# ============================================================

section "VERIFYING DEPENDENCIES"

# Prefer the distribution-managed Python so its native packages
# are visible, particularly on Ubuntu.

if [[ -x /usr/bin/python3 ]]; then
    PYTHON_BIN="/usr/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    manual_fallback "Python 3 is unavailable."
fi

if ! "$PYTHON_BIN" - <<'PY'
import importlib
import sys

checks = {
    "gi": "PyGObject",
    "cairo": "Pycairo",
    "pyudev": "PyUDev",
}

failed = []

for module, name in checks.items():
    try:
        importlib.import_module(module)
        print(f"  OK: {name}")
    except Exception as exc:
        print(f"  FAIL: {name}: {exc}")
        failed.append(name)

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gio, GLib

    print("  OK: GTK 3 / Gio / GLib")

    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell

    print("  OK: GTK Layer Shell")

except Exception as exc:
    print(f"  FAIL: GTK introspection: {exc}")
    failed.append("GTK introspection")

if failed:
    print("\nMissing or unusable dependencies:", ", ".join(failed))
    sys.exit(1)
PY
then
    manual_fallback "One or more Python or GTK dependencies failed verification."
fi

success "All dependency checks passed."

# ============================================================
# STAGE 7 — STARTUP CONFIGURATION
# ============================================================

section "STARTUP CONFIGURATION"

WATCHERS=(
    dynamic_island.py
    battery_warn.py
    charging_watcher.py
    desktop_watcher.py
    notification.py
    temprature.py
    usb_watcher.py
    volume_watcher.py
    wifi.py
)

# --- Detect startup method (priority: Hyprland > systemd > .profile) ---

STARTUP_METHOD=""
HYPRLAND_CONF=""

if command -v hyprctl >/dev/null 2>&1 || [[ -f "$HOME/.config/hypr/hyprland.conf" ]]; then
    STARTUP_METHOD="hyprland"
    HYPRLAND_CONF="$HOME/.config/hypr/hyprland.conf"
elif command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
    STARTUP_METHOD="systemd"
else
    STARTUP_METHOD="profile"
fi

info "Detected startup method: ${STARTUP_METHOD}"

if ! confirm "Configure LinuxIsland to start automatically?"; then
    warning "Skipping startup configuration."
    printf "\n"
else

    case "$STARTUP_METHOD" in

        # ----------------------------------------------------------
        # HYPRLAND — exec-once entries
        # ----------------------------------------------------------
        hyprland)
            info "Configuring Hyprland exec-once entries..."

            if [[ ! -d "$(dirname "$HYPRLAND_CONF")" ]]; then
                mkdir -p "$(dirname "$HYPRLAND_CONF")"
            fi

            if [[ ! -f "$HYPRLAND_CONF" ]]; then
                touch "$HYPRLAND_CONF"
                info "Created $HYPRLAND_CONF"
            fi

            # Back up existing config.
            cp "$HYPRLAND_CONF" "${HYPRLAND_CONF}.bak.$(date +%Y%m%d%H%M%S)"
            info "Backup saved."

            for script in "${WATCHERS[@]}"; do
                line_entry="exec-once = ${PYTHON_BIN} ${PROJECT_DIR}/${script}"

                # Skip if already present.
                if grep -qF "$line_entry" "$HYPRLAND_CONF"; then
                    continue
                fi

                echo "$line_entry" >> "$HYPRLAND_CONF"
            done

            success "Hyprland exec-once entries added to $HYPRLAND_CONF"
            info "They will take effect on your next Hyprland session (or after 'hyprctl reload')."
            ;;

        # ----------------------------------------------------------
        # SYSTEMD — user services
        # ----------------------------------------------------------
        systemd)
            info "Creating systemd user services..."

            UNIT_DIR="$HOME/.config/systemd/user"
            mkdir -p "$UNIT_DIR"

            for script in "${WATCHERS[@]}"; do
                unit_name="linuxisland-$(basename "$script" .py)"
                unit_file="${UNIT_DIR}/${unit_name}.service"

                cat > "$unit_file" <<UNIT
[Unit]
Description=LinuxIsland ${script}
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} ${PROJECT_DIR}/${script}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT

                systemctl --user daemon-reload 2>/dev/null || true
            done

            # Enable all units.
            for script in "${WATCHERS[@]}"; do
                unit_name="linuxisland-$(basename "$script" .py)"
                systemctl --user enable "linuxisland-${unit_name#.service}" 2>/dev/null || \
                    systemctl --user enable "${UNIT_DIR}/linuxisland-$(basename "$script" .py).service" 2>/dev/null || true
            done

            success "Systemd user services created and enabled."
            info "They will start on your next login (or run 'systemctl --user start linuxisland-*' now)."
            ;;

        # ----------------------------------------------------------
        # FALLBACK — append to ~/.profile or ~/.bashrc
        # ----------------------------------------------------------
        profile)
            info "No Hyprland or systemd detected. Using shell profile..."

            PROFILE_FILE=""
            for candidate in "$HOME/.profile" "$HOME/.bashrc"; do
                if [[ -f "$candidate" ]]; then
                    PROFILE_FILE="$candidate"
                    break
                fi
            done

            if [[ -z "$PROFILE_FILE" ]]; then
                PROFILE_FILE="$HOME/.profile"
                touch "$PROFILE_FILE"
            fi

            MARKER_BEGIN="# >>> LinuxIsland >>>"
            MARKER_END="# <<< LinuxIsland <<<"

            # Remove old block if present.
            if grep -qF "$MARKER_BEGIN" "$PROFILE_FILE"; then
                sed -i "/$MARKER_BEGIN/,/$MARKER_END/d" "$PROFILE_FILE"
            fi

            {
                echo ""
                echo "$MARKER_BEGIN"
                for script in "${WATCHERS[@]}"; do
                    echo "nohup ${PYTHON_BIN} ${PROJECT_DIR}/${script} >/dev/null 2>&1 &"
                done
                echo "$MARKER_END"
            } >> "$PROFILE_FILE"

            success "Startup block added to $PROFILE_FILE"
            info "LinuxIsland will launch on your next shell login."
            ;;

    esac

fi

# ============================================================
# COMPLETION
# ============================================================

section "INSTALLATION COMPLETE"

printf "\n"
printf "  ${GREEN}${BOLD}LinuxIsland is ready!${RESET}\n"
printf "\n"
printf "  Python executable:\n"
printf "    %s\n" "$PYTHON_BIN"
printf "\n"
printf "  Project directory:\n"
printf "    %s\n" "$PROJECT_DIR"
printf "\n"

if [[ -n "$STARTUP_METHOD" ]]; then
    printf "  Startup configured via: ${CYAN}${BOLD}%s${RESET}\n" "$STARTUP_METHOD"
    printf "\n"
fi

printf "  To launch manually:\n\n"
printf "    ${CYAN}${BOLD}%s dynamic_island.py${RESET}\n" "$PYTHON_BIN"
printf "\n"

printf "\n"
line
printf "  ${DIM}LinuxIsland Quick Setup v${VERSION}${RESET}\n"
printf "  ${DIM}Setup finished successfully.${RESET}\n\n"
