#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# LinuxIsland Config CLI
# Manage module enable/disable and startup configuration.
# ============================================================

VERSION="1.0.0"
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/linuxisland"
CONFIG_FILE="${CONFIG_DIR}/config.json"
HYPRLAND_CONF="$HOME/.config/hypr/hyprland.conf"

# ============================================================
# STYLING
# ============================================================

if [[ -t 1 ]]; then
    RESET='\033[0m'
    BOLD='\033[1m'
    DIM='\033[2m'
    CYAN='\033[38;5;45m'
    GREEN='\033[38;5;82m'
    YELLOW='\033[38;5;220m'
    RED='\033[38;5;196m'
    WHITE='\033[97m'
else
    RESET='' BOLD='' DIM='' CYAN='' GREEN='' YELLOW='' RED='' WHITE=''
fi

# ============================================================
# MODULES
# ============================================================

ALL_MODULES=(
    dynamic_island
    battery_warn
    charging_watcher
    desktop_watcher
    notification
    temprature
    usb_watcher
    volume_watcher
    wifi
)

MODULE_DESCRIPTIONS=(
    "Main island display (required)"
    "Low battery warnings"
    "Charger plug/unplug events"
    "Desktop/workspace switch notifications"
    "D-Bus notification daemon"
    "CPU temperature monitoring"
    "USB device connect/disconnect"
    "Volume change events"
    "Wi-Fi connect/disconnect"
)

# ============================================================
# CONFIG FILE HELPERS
# ============================================================

ensure_config() {
    if [[ ! -d "$CONFIG_DIR" ]]; then
        mkdir -p "$CONFIG_DIR"
    fi

    if [[ ! -f "$CONFIG_FILE" ]]; then
        # Create default config with all modules enabled.
        local entries=()
        for module in "${ALL_MODULES[@]}"; do
            entries+=("    \"${module}\": true")
        done
        local joined
        joined=$(IFS=',\n'; echo "${entries[*]}")

        cat > "$CONFIG_FILE" <<EOF
{
  "modules": {
${joined}
  }
}
EOF
        printf " ${DIM}Created default config: %s${RESET}\n" "$CONFIG_FILE"
    fi
}

get_module_state() {
    local module="$1"
    python3 -c "
import json, sys
with open('${CONFIG_FILE}') as f:
    cfg = json.load(f)
print('true' if cfg.get('modules', {}).get('${module}', True) else 'false')
" 2>/dev/null || echo "true"
}

set_module_state() {
    local module="$1"
    local state="$2"  # "true" or "false"
    local py_bool="False"
    if [[ "$state" == "true" ]]; then
        py_bool="True"
    fi
    python3 -c "
import json
with open('${CONFIG_FILE}') as f:
    cfg = json.load(f)
cfg.setdefault('modules', {})['${module}'] = ${py_bool}
with open('${CONFIG_FILE}', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
"
}

# ============================================================
# STARTUP METHOD DETECTION
# ============================================================

detect_startup_method() {
    if command -v hyprctl >/dev/null 2>&1 || [[ -f "$HYPRLAND_CONF" ]]; then
        echo "hyprland"
    elif command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
        echo "systemd"
    else
        echo "profile"
    fi
}

# ============================================================
# STARTUP CONFIG HELPERS (Hyprland)
# ============================================================

hyprland_exec_line() {
    local module="$1"
    printf 'exec-once = python3 %s/%s.py' "$PROJECT_DIR" "$module"
}

hyprland_add_module() {
    local module="$1"
    if [[ ! -d "$(dirname "$HYPRLAND_CONF")" ]]; then
        mkdir -p "$(dirname "$HYPRLAND_CONF")"
    fi
    if [[ ! -f "$HYPRLAND_CONF" ]]; then
        touch "$HYPRLAND_CONF"
    fi

    local line
    line=$(hyprland_exec_line "$module")

    if grep -qF "$line" "$HYPRLAND_CONF"; then
        return 0
    fi

    echo "$line" >> "$HYPRLAND_CONF"
}

hyprland_remove_module() {
    local module="$1"
    [[ -f "$HYPRLAND_CONF" ]] || return 0

    local line
    line=$(hyprland_exec_line "$module")

    sed -i "\#^${line}$#d" "$HYPRLAND_CONF" 2>/dev/null || \
        grep -vF "$line" "$HYPRLAND_CONF" > "${HYPRLAND_CONF}.tmp" && mv "${HYPRLAND_CONF}.tmp" "$HYPRLAND_CONF"
}

hyprland_has_module() {
    local module="$1"
    [[ -f "$HYPRLAND_CONF" ]] || return 1
    local line
    line=$(hyprland_exec_line "$module")
    grep -qF "$line" "$HYPRLAND_CONF"
}

# ============================================================
# STARTUP CONFIG HELPERS (systemd)
# ============================================================

SYSTEMD_DIR="$HOME/.config/systemd/user"

systemd_unit_file() {
    local module="$1"
    printf '%s/linuxisland-%s.service' "$SYSTEMD_DIR" "$module"
}

systemd_add_module() {
    local module="$1"
    mkdir -p "$SYSTEMD_DIR"

    local unit_file
    unit_file=$(systemd_unit_file "$module")

    cat > "$unit_file" <<UNIT
[Unit]
Description=LinuxIsland ${module}
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=python3 ${PROJECT_DIR}/${module}.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT

    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable "linuxisland-${module}" 2>/dev/null || true
}

systemd_remove_module() {
    local module="$1"
    systemctl --user disable "linuxisland-${module}" 2>/dev/null || true
    rm -f "$(systemd_unit_file "$module")"
    systemctl --user daemon-reload 2>/dev/null || true
}

systemd_has_module() {
    local module="$1"
    [[ -f "$(systemd_unit_file "$module")" ]]
}

# ============================================================
# STARTUP CONFIG HELPERS (profile fallback)
# ============================================================

PROFILE_FILE=""
MARKER_BEGIN="# >>> LinuxIsland: ${MODULE_NAME:-config} >>>"
MARKER_END="# <<< LinuxIsland: config <<<"

find_profile_file() {
    for candidate in "$HOME/.profile" "$HOME/.bashrc"; do
        if [[ -f "$candidate" ]]; then
            PROFILE_FILE="$candidate"
            return
        fi
    done
    PROFILE_FILE="$HOME/.profile"
}

# ============================================================
# APPLY MODULE STATE TO STARTUP
# ============================================================

apply_module_to_startup() {
    local module="$1"
    local state="$2"  # "true" or "false"
    local method
    method=$(detect_startup_method)

    case "$method" in
        hyprland)
            if [[ "$state" == "true" ]]; then
                hyprland_add_module "$module"
            else
                hyprland_remove_module "$module"
            fi
            ;;
        systemd)
            if [[ "$state" == "true" ]]; then
                systemd_add_module "$module"
            else
                systemd_remove_module "$module"
            fi
            ;;
        profile)
            # For profile mode, we just track in config.json.
            # The user manages their own shell startup.
            ;;
    esac
}

# ============================================================
# UI HELPERS
# ============================================================

line() {
    printf "${DIM}────────────────────────────────────────────────────────${RESET}\n"
}

header() {
    printf "\n${BOLD}${CYAN}  LinuxIsland Config v%s${RESET}\n" "$VERSION"
    line
}

status_icon() {
    local state="$1"
    if [[ "$state" == "true" ]]; then
        printf "${GREEN}●${RESET}"
    else
        printf "${RED}○${RESET}"
    fi
}

# ============================================================
# COMMANDS
# ============================================================

cmd_status() {
    header
    ensure_config

    local method
    method=$(detect_startup_method)
    printf "  ${DIM}Startup method: %s${RESET}\n" "$method"
    printf "  ${DIM}Config file:    %s${RESET}\n\n" "$CONFIG_FILE"
    line

    for i in "${!ALL_MODULES[@]}"; do
        local module="${ALL_MODULES[$i]}"
        local desc="${MODULE_DESCRIPTIONS[$i]}"
        local state
        state=$(get_module_state "$module")

        # Check if it's actually in the startup config.
        local in_startup="no"
        case "$method" in
            hyprland)  hyprland_has_module "$module" && in_startup="yes" ;;
            systemd)   systemd_has_module "$module" && in_startup="yes" ;;
        esac

        printf "  $(status_icon "$state") ${BOLD}%-20s${RESET} ${DIM}%s${RESET}" \
            "$module" "$desc"

        if [[ "$in_startup" == "yes" ]]; then
            printf "  ${GREEN}[autostart]${RESET}\n"
        else
            printf "\n"
        fi
    done

    line
    printf "\n"
}

cmd_enable() {
    local module="$1"

    # Validate.
    local valid=false
    for m in "${ALL_MODULES[@]}"; do
        if [[ "$m" == "$module" ]]; then
            valid=true
            break
        fi
    done

    if [[ "$valid" == false ]]; then
        printf " ${RED}✖${RESET} Unknown module: %s\n" "$module"
        printf " ${DIM}Available: %s${RESET}\n" "${ALL_MODULES[*]}"
        exit 1
    fi

    ensure_config
    set_module_state "$module" "true"
    apply_module_to_startup "$module" "true"

    printf " ${GREEN}✔${RESET} Enabled ${BOLD}%s${RESET}\n" "$module"
}

cmd_disable() {
    local module="$1"

    # Validate.
    local valid=false
    for m in "${ALL_MODULES[@]}"; do
        if [[ "$m" == "$module" ]]; then
            valid=true
            break
        fi
    done

    if [[ "$valid" == false ]]; then
        printf " ${RED}✖${RESET} Unknown module: %s\n" "$module"
        printf " ${DIM}Available: %s${RESET}\n" "${ALL_MODULES[*]}"
        exit 1
    fi

    # Prevent disabling the main island.
    if [[ "$module" == "dynamic_island" ]]; then
        printf " ${YELLOW}⚠${RESET} Cannot disable dynamic_island (required for display).\n"
        exit 1
    fi

    ensure_config
    set_module_state "$module" "false"
    apply_module_to_startup "$module" "false"

    printf " ${RED}○${RESET} Disabled ${BOLD}%s${RESET}\n" "$module"
}

cmd_toggle() {
    local module="$1"
    ensure_config
    local state
    state=$(get_module_state "$module")

    if [[ "$state" == "true" ]]; then
        cmd_disable "$module"
    else
        cmd_enable "$module"
    fi
}

cmd_enable_all() {
    ensure_config
    for module in "${ALL_MODULES[@]}"; do
        set_module_state "$module" "true"
        apply_module_to_startup "$module" "true"
    done
    printf " ${GREEN}✔${RESET} All modules enabled.\n"
}

cmd_disable_all() {
    ensure_config
    for module in "${ALL_MODULES[@]}"; do
        if [[ "$module" == "dynamic_island" ]]; then
            continue
        fi
        set_module_state "$module" "false"
        apply_module_to_startup "$module" "false"
    done
    printf " ${RED}○${RESET} All watchers disabled (island kept).\n"
}

cmd_sync() {
    # Re-apply all module states to the startup config.
    ensure_config
    local method
    method=$(detect_startup_method)

    header
    printf "  Syncing modules to ${BOLD}%s${RESET} startup config...\n\n" "$method"

    for i in "${!ALL_MODULES[@]}"; do
        local module="${ALL_MODULES[$i]}"
        local state
        state=$(get_module_state "$module")
        apply_module_to_startup "$module" "$state"
        printf "  $(status_icon "$state") %s\n" "$module"
    done

    line
    printf "\n ${GREEN}✔${RESET} Sync complete.\n\n"
}

cmd_show_config() {
    ensure_config
    header
    printf "  ${DIM}%s${RESET}\n\n" "$CONFIG_FILE"
    cat "$CONFIG_FILE" | sed 's/^/  /'
    printf "\n"
}

# ============================================================
# HELP
# ============================================================

cmd_help() {
    cat <<EOF

${BOLD}${CYAN}LinuxIsland Config v${VERSION}${RESET}

Usage: config.sh <command> [module]

${BOLD}Commands:${RESET}
  status              Show all modules and their state.
  enable <module>     Enable a module + add to autostart.
  disable <module>    Disable a module + remove from autostart.
  toggle <module>     Toggle a module on/off.
  enable-all          Enable all modules.
  disable-all         Disable all watchers (keeps island).
  sync                Re-apply config to startup method.
  show-config         Print the raw JSON config file.
  help                Show this help.

${BOLD}Modules:${RESET}
EOF
    for i in "${!ALL_MODULES[@]}"; do
        printf "  %-20s %s\n" "${ALL_MODULES[$i]}" "${MODULE_DESCRIPTIONS[$i]}"
    done

    cat <<EOF

${BOLD}Examples:${RESET}
  ./config.sh status
  ./config.sh disable wifi
  ./config.sh toggle desktop_watcher
  ./config.sh enable-all
  ./config.sh sync

Config file: ${DIM}$CONFIG_FILE${RESET}
Startup method auto-detected (Hyprland > systemd > profile).
EOF
    printf "\n"
}

# ============================================================
# MAIN DISPATCH
# ============================================================

if [[ $# -lt 1 ]]; then
    cmd_help
    exit 0
fi

COMMAND="$1"
shift

case "$COMMAND" in
    status|s)
        cmd_status
        ;;
    enable|on)
        [[ $# -ge 1 ]] || { echo "Usage: config.sh enable <module>" >&2; exit 1; }
        cmd_enable "$1"
        ;;
    disable|off)
        [[ $# -ge 1 ]] || { echo "Usage: config.sh disable <module>" >&2; exit 1; }
        cmd_disable "$1"
        ;;
    toggle|t)
        [[ $# -ge 1 ]] || { echo "Usage: config.sh toggle <module>" >&2; exit 1; }
        cmd_toggle "$1"
        ;;
    enable-all|all-on)
        cmd_enable_all
        ;;
    disable-all|all-off)
        cmd_disable_all
        ;;
    sync)
        cmd_sync
        ;;
    show-config|cat)
        cmd_show_config
        ;;
    help|-h|--help)
        cmd_help
        ;;
    *)
        printf " ${RED}✖${RESET} Unknown command: %s\n" "$COMMAND"
        printf " Run 'config.sh help' for usage.\n"
        exit 1
        ;;
esac
