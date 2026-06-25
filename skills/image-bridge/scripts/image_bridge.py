#!/usr/bin/env python3
"""ImageBridge: call a configurable image generation HTTP endpoint."""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as _dt
import json
import mimetypes
import os
from pathlib import Path
import re
import shlex
import ssl
import sys
import time
from typing import Any
from urllib import error, request
from urllib.parse import urlparse, urlunparse


DEFAULT_CONFIG_PATHS = (
    Path(".imagebridge/config.json"),
    Path.home() / ".imagebridge" / "config.json",
)

CONFIG_TEMPLATE: dict[str, Any] = {
    "active": "default",
    "output_dir": "imagebridge-output",
    "providers": {
        "default": {
            "endpoint": "https://api.example.com/v1/images/generations",
            "method": "POST",
            "api_key_env": "IMAGEBRIDGE_API_KEY",
            "model": "your-image-model",
            "timeout_seconds": 120,
            "field_map": {
                "prompt": "prompt",
                "model": "model",
                "size": "size",
                "n": "n",
                "negative_prompt": "negative_prompt",
            },
            "payload_defaults": {
                "response_format": "b64_json"
            },
            "headers": {
                "Content-Type": "application/json"
            },
            "tls_verify": False,
            "response": {
                "data_path": "data",
                "base64_path": "b64_json",
                "url_path": "url"
            }
        }
    }
}


SECRET_KEYS = ("api_key", "authorization", "token", "secret", "password")
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
LONG_VALUE_LIMIT = 240


class ImageBridgeError(Exception):
    """Expected operational error."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lower = key.lower()
            if any(secret in lower for secret in SECRET_KEYS):
                result[key] = "***"
            elif lower in ("b64_json", "base64", "image", "image_base64") and isinstance(item, str):
                result[key] = f"<{len(item)} chars omitted>"
            elif lower == "headers" and isinstance(item, dict):
                result[key] = {
                    header: ("***" if header.lower() == "authorization" else sanitize(header_value))
                    for header, header_value in item.items()
                }
            else:
                result[key] = sanitize(item)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str) and (
        len(value) > LONG_VALUE_LIMIT or value.startswith("data:image/")
    ):
        return f"<{len(value)} chars omitted>"
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ImageBridgeError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ImageBridgeError(f"Invalid JSON config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ImageBridgeError(f"Config root must be an object: {path}")
    return data


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        try:
            parts = shlex.split(line, posix=True)
        except ValueError:
            continue
        if not parts or "=" not in parts[0]:
            continue
        key, value = parts[0].split("=", 1)
        if key:
            os.environ.setdefault(key, value)


def load_related_env(config_path: Path | None) -> None:
    if config_path:
        load_env_file(config_path.expanduser().parent / ".env")
    load_env_file(Path.home() / ".imagebridge" / ".env")


def find_config(explicit_path: str | None) -> tuple[dict[str, Any], Path | None]:
    if explicit_path:
        path = Path(explicit_path).expanduser()
        return load_json(path), path

    env_path = os.environ.get("IMAGEBRIDGE_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        return load_json(path), path

    for candidate in DEFAULT_CONFIG_PATHS:
        path = candidate.expanduser()
        if path.exists():
            return load_json(path), path

    raise ImageBridgeError(
        "No ImageBridge config found. Create ./.imagebridge/config.json, "
        "~/.imagebridge/config.json, set IMAGEBRIDGE_CONFIG, or pass --config."
    )


def normalize_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.scheme:
        endpoint = "https://" + endpoint
        parsed = urlparse(endpoint)

    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        path = "/v1/images/generations"
    elif path == "/v1":
        path = "/v1/images/generations"
    elif path.endswith("/v1"):
        path = path + "/images/generations"

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def active_provider(config: dict[str, Any], provider_name: str | None) -> tuple[str, dict[str, Any]]:
    providers = config.get("providers")
    if isinstance(providers, dict):
        name = provider_name or str(config.get("active") or next(iter(providers)))
        provider = providers.get(name)
        if not isinstance(provider, dict):
            available = ", ".join(sorted(providers))
            raise ImageBridgeError(f"Unknown provider '{name}'. Available providers: {available}")
        merged = {key: value for key, value in config.items() if key not in ("providers", "active")}
        merged = deep_merge(merged, provider)
        return name, merged

    if provider_name:
        raise ImageBridgeError("--provider requires a config with a providers object")
    return str(config.get("active") or "default"), config


def set_path(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    current = target
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


def tls_verify(provider: dict[str, Any]) -> bool:
    env_value = os.environ.get("IMAGEBRIDGE_TLS_VERIFY")
    if env_value is not None:
        return as_bool(env_value, False)
    return as_bool(provider.get("tls_verify"), False)


def apply_params(payload: dict[str, Any], params: list[str]) -> None:
    for item in params:
        if "=" not in item:
            raise ImageBridgeError(f"Invalid --param '{item}'. Use key=value.")
        key, raw_value = item.split("=", 1)
        set_path(payload, key, parse_value(raw_value))


def build_payload(provider: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = copy.deepcopy(provider.get("payload_defaults") or {})
    if not isinstance(payload, dict):
        raise ImageBridgeError("payload_defaults must be an object")

    field_map = provider.get("field_map") or {}
    if not isinstance(field_map, dict):
        raise ImageBridgeError("field_map must be an object")

    def mapped(field: str, value: Any) -> None:
        if value in (None, ""):
            return
        target = field_map.get(field, field)
        if target:
            set_path(payload, str(target), value)

    mapped("prompt", args.prompt)
    mapped("model", args.model or provider.get("model"))
    mapped("size", args.size)
    mapped("n", args.n)
    mapped("negative_prompt", args.negative_prompt)
    apply_params(payload, args.param)
    return expand_env(payload)


def build_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = provider.get("headers") or {}
    if not isinstance(headers, dict):
        raise ImageBridgeError("headers must be an object")

    result = {str(key): str(value) for key, value in expand_env(headers).items()}
    result.setdefault("Content-Type", "application/json")
    result.setdefault("User-Agent", "ImageBridge/1.0")

    api_key = provider.get("api_key")
    api_key_env = provider.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(str(api_key_env), api_key)
    if api_key and "Authorization" not in result:
        result["Authorization"] = f"Bearer {api_key}"
    return result


def json_path(value: Any, path: str | None) -> Any:
    if not path:
        return value
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ImageBridgeError(f"Response path '{path}' did not match response") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ImageBridgeError(f"Response path '{path}' did not match response")
    return current


def request_json(
    endpoint: str,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
    verify_tls: bool,
) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=timeout, context=ssl_context(verify_tls)) as response:
            raw = response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ImageBridgeError(f"Provider HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ImageBridgeError(f"Provider request failed: {exc.reason}") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ImageBridgeError("Provider response was not valid JSON") from exc


def ssl_context(verify_tls: bool = True) -> ssl.SSLContext:
    if not verify_tls:
        return ssl._create_unverified_context()

    cafile = os.environ.get("IMAGEBRIDGE_CA_FILE")
    candidates = [cafile] if cafile else []
    candidates.extend([
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def infer_extension(content_type: str | None, fallback: str) -> str:
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed.lstrip(".")
    return fallback.lstrip(".")


def download_url(url: str, timeout: int, verify_tls: bool = True) -> tuple[bytes, str | None]:
    try:
        with request.urlopen(url, timeout=timeout, context=ssl_context(verify_tls)) as response:
            return response.read(), response.headers.get("Content-Type")
    except error.URLError as exc:
        raise ImageBridgeError(f"Image download failed: {exc.reason}") from exc


def decode_data_url(value: str) -> tuple[bytes, str]:
    header, encoded = value.split(",", 1)
    match = re.search(r"data:image/([a-zA-Z0-9.+-]+);base64", header)
    extension = match.group(1).lower() if match else "png"
    return base64.b64decode(encoded), extension


def extract_images(
    response_json: Any,
    provider: dict[str, Any],
    timeout: int,
    verify_tls: bool = True,
) -> list[tuple[bytes, str, dict[str, Any]]]:
    response_cfg = provider.get("response") or {}
    if not isinstance(response_cfg, dict):
        raise ImageBridgeError("response must be an object")

    data_path = response_cfg.get("data_path", "data")
    base64_path = response_cfg.get("base64_path", "b64_json")
    url_path = response_cfg.get("url_path", "url")
    default_ext = str(response_cfg.get("extension", "png"))

    records = json_path(response_json, str(data_path)) if data_path else response_json
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise ImageBridgeError("Response image data must be an object or array")

    images: list[tuple[bytes, str, dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if base64_path:
            try:
                encoded = json_path(record, str(base64_path))
            except ImageBridgeError:
                encoded = None
            if isinstance(encoded, str) and encoded:
                if encoded.startswith("data:image/"):
                    data, ext = decode_data_url(encoded)
                else:
                    data, ext = base64.b64decode(encoded), default_ext
                images.append((data, ext, record))
                continue
        if url_path:
            try:
                url = json_path(record, str(url_path))
            except ImageBridgeError:
                url = None
            if isinstance(url, str) and url:
                data, content_type = download_url(url, timeout, verify_tls)
                images.append((data, infer_extension(content_type, default_ext), record))

    if not images:
        raise ImageBridgeError("No image found in provider response. Check response.data_path/base64_path/url_path.")
    return images


def safe_stem(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())[:48].strip("-._")
    return cleaned or "image"


def save_outputs(
    images: list[tuple[bytes, str, dict[str, Any]]],
    output_dir: Path,
    prompt: str,
    provider_name: str,
    payload: dict[str, Any],
    response_json: Any,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}-{safe_stem(prompt)}"
    image_paths: list[str] = []

    for index, (data, extension, _record) in enumerate(images, start=1):
        suffix = f"-{index}" if len(images) > 1 else ""
        path = output_dir / f"{stem}{suffix}.{extension.lstrip('.')}"
        path.write_bytes(data)
        image_paths.append(str(path))

    metadata = {
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "provider": provider_name,
        "prompt": prompt,
        "payload": sanitize(payload),
        "images": image_paths,
        "response": sanitize(response_json),
    }
    metadata_path = output_dir / f"{stem}.metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def output_dir(provider: dict[str, Any], args: argparse.Namespace) -> Path:
    raw = args.output_dir or provider.get("output_dir") or "imagebridge-output"
    return Path(str(raw)).expanduser()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate images through a configurable image API.")
    parser.add_argument("--prompt", help="Final image prompt")
    parser.add_argument("--negative-prompt", help="Negative prompt if supported by provider")
    parser.add_argument("--size", help="Provider-specific size, for example 1024x1024 or 4096x4096")
    parser.add_argument("--n", type=int, help="Number of images if supported by provider")
    parser.add_argument("--model", help="Override configured model")
    parser.add_argument("--provider", help="Provider profile name from config.providers")
    parser.add_argument("--config", help="Path to ImageBridge config JSON")
    parser.add_argument("--output-dir", help="Directory for generated images and metadata")
    parser.add_argument("--param", action="append", default=[], help="Extra provider payload value as key=value; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Print sanitized request and do not call provider")
    parser.add_argument("--print-config-template", action="store_true", help="Print example JSON config")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.print_config_template:
        print(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    if not args.prompt:
        raise ImageBridgeError("--prompt is required unless --print-config-template is used")

    config, config_path = find_config(args.config)
    load_related_env(config_path)
    provider_name, provider = active_provider(config, args.provider)
    provider = expand_env(provider)

    endpoint = provider.get("endpoint")
    if not endpoint:
        raise ImageBridgeError("Provider endpoint is required")
    endpoint = normalize_endpoint(str(endpoint))

    method = str(provider.get("method", "POST"))
    timeout = int(provider.get("timeout_seconds", 120))
    verify_tls = tls_verify(provider)
    payload = build_payload(provider, args)
    headers = build_headers(provider)

    request_summary = {
        "config_path": str(config_path) if config_path else None,
        "provider": provider_name,
        "endpoint": endpoint,
        "method": method,
        "headers": headers,
        "payload": payload,
        "output_dir": str(output_dir(provider, args)),
        "tls_verify": verify_tls,
    }

    if args.dry_run:
        print(json.dumps(sanitize(request_summary), ensure_ascii=False, indent=2))
        return 0

    started = time.time()
    response_json = request_json(str(endpoint), method, headers, payload, timeout, verify_tls)
    images = extract_images(response_json, provider, timeout, verify_tls)
    metadata = save_outputs(images, output_dir(provider, args), args.prompt, provider_name, payload, response_json)
    metadata["elapsed_seconds"] = round(time.time() - started, 3)
    print(json.dumps(sanitize(metadata), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ImageBridgeError as exc:
        print(f"image_bridge.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
