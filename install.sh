#!/usr/bin/env bash
set -euo pipefail

REPO="${IMAGEBRIDGE_REPO:-kong-kyle/ImageBridge}"
REF="${IMAGEBRIDGE_REF:-main}"
TARGET="${1:-${TARGET:-both}}"
CONFIG_DIR="${IMAGEBRIDGE_CONFIG_DIR:-$HOME/.imagebridge}"
CONFIG_FILE="$CONFIG_DIR/config.json"
ENV_FILE="$CONFIG_DIR/.env"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

case "$TARGET" in
  codex|claude|both) ;;
  *)
    echo "TARGET must be codex, claude, or both" >&2
    exit 2
    ;;
esac

prompt() {
  local label="$1"
  local default_value="${2:-}"
  local secret="${3:-false}"
  local value=""

  if ! { : < /dev/tty > /dev/tty; } 2>/dev/null; then
    printf "%s" "$default_value"
    return 0
  fi

  if [ "$secret" = "true" ]; then
    printf "%s: " "$label" > /dev/tty
    IFS= read -r -s value < /dev/tty || true
    printf "\n" > /dev/tty
  else
    if [ -n "$default_value" ]; then
      printf "%s [%s]: " "$label" "$default_value" > /dev/tty
    else
      printf "%s: " "$label" > /dev/tty
    fi
    IFS= read -r value < /dev/tty || true
  fi

  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf "%s" "$value"
}

json_escape() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))'
}

shell_escape() {
  python3 -c 'import shlex, sys; print(shlex.quote(sys.stdin.read()))'
}

bool_json() {
  python3 -c '
import sys
value = sys.stdin.read().strip().lower()
if value in ("0", "false", "no", "n", "off"):
    print("false")
else:
    print("true")
'
}

normalize_endpoint() {
  python3 -c '
import sys
from urllib.parse import urlparse, urlunparse

raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit

parsed = urlparse(raw)
if not parsed.scheme:
    raw = "https://" + raw
    parsed = urlparse(raw)

path = parsed.path.rstrip("/")
if path in ("", "/"):
    path = "/v1/images/generations"
elif path == "/v1":
    path = "/v1/images/generations"
elif path.endswith("/v1"):
    path = path + "/images/generations"

print(urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")))
'
}

write_config() {
  local endpoint="$1"
  local api_key="$2"
  local model="$3"

  mkdir -p "$CONFIG_DIR"
  chmod 700 "$CONFIG_DIR"

  endpoint="$(printf "%s" "$endpoint" | normalize_endpoint)"
  endpoint_json="$(printf "%s" "$endpoint" | json_escape)"
  model_json="$(printf "%s" "$model" | json_escape)"
  tls_verify_json="$(printf "%s" "${IMAGEBRIDGE_TLS_VERIFY:-false}" | bool_json)"
  cat > "$CONFIG_FILE" <<EOF
{
  "active": "default",
  "output_dir": "imagebridge-output",
  "providers": {
    "default": {
      "endpoint": $endpoint_json,
      "api_key_env": "IMAGEBRIDGE_API_KEY",
      "model": $model_json,
      "field_map": {
        "prompt": "prompt",
        "model": "model",
        "size": "size",
        "n": "n",
        "negative_prompt": "negative_prompt"
      },
      "payload_defaults": {
        "response_format": "b64_json"
      },
      "tls_verify": $tls_verify_json,
      "response": {
        "data_path": "data",
        "base64_path": "b64_json",
        "url_path": "url",
        "extension": "png"
      }
    }
  }
}
EOF
  chmod 600 "$CONFIG_FILE"

  api_key_shell="$(printf "%s" "$api_key" | shell_escape)"
  cat > "$ENV_FILE" <<EOF
export IMAGEBRIDGE_API_KEY=$api_key_shell
export IMAGEBRIDGE_CONFIG="$CONFIG_FILE"
export IMAGEBRIDGE_TLS_VERIFY="$tls_verify_json"
EOF
  chmod 600 "$ENV_FILE"
}

curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz" | tar -xz -C "$TMP_DIR"
SKILL_DIR="$TMP_DIR/ImageBridge-${REF}/skills/image-bridge"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  echo "ImageBridge skill not found in downloaded archive" >&2
  exit 2
fi

install_skill() {
  local dest_root="$1"
  mkdir -p "$dest_root"
  rm -rf "$dest_root/image-bridge"
  cp -R "$SKILL_DIR" "$dest_root/"
  echo "Installed: $dest_root/image-bridge"
}

install_codex_skill() {
  local agents_root="$HOME/.agents/skills"
  local codex_root="${CODEX_HOME:-$HOME/.codex}/skills"

  install_skill "$agents_root"
  if [ "$codex_root" != "$agents_root" ]; then
    install_skill "$codex_root"
  fi
}

if [ "$TARGET" = "codex" ] || [ "$TARGET" = "both" ]; then
  install_codex_skill
fi

if [ "$TARGET" = "claude" ] || [ "$TARGET" = "both" ]; then
  install_skill "$HOME/.claude/skills"
fi

echo
echo "Configure ImageBridge"
endpoint="${IMAGEBRIDGE_URL:-}"
api_key="${IMAGEBRIDGE_API_KEY:-}"
model="${IMAGEBRIDGE_MODEL:-}"
tls_verify="${IMAGEBRIDGE_TLS_VERIFY:-false}"

if [ -z "$endpoint" ]; then
  endpoint="$(prompt "Image API URL" "")"
fi
if [ -z "$api_key" ]; then
  api_key="$(prompt "Image API Key" "" true)"
fi
if [ -z "$model" ]; then
  model="$(prompt "Image model" "")"
fi
if [ -z "${IMAGEBRIDGE_TLS_VERIFY:-}" ]; then
  tls_verify="$(prompt "Verify TLS certificates" "false")"
fi

if [ -z "$endpoint" ] || [ -z "$api_key" ] || [ -z "$model" ]; then
  echo "Skipped config: url, key, and model are required." >&2
  echo "Run again or create $CONFIG_FILE manually." >&2
  exit 2
fi

export IMAGEBRIDGE_TLS_VERIFY="$tls_verify"
write_config "$endpoint" "$api_key" "$model"

echo "Config written: $CONFIG_FILE"
echo "Key env written: $ENV_FILE"
echo
echo "The bridge loads this env file automatically. For direct shell use, you can also run:"
echo "  source $ENV_FILE"
echo
echo "ImageBridge installed and configured."
