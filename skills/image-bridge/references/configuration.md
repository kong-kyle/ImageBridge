# ImageBridge Configuration

ImageBridge reads JSON configuration from `--config`, `IMAGEBRIDGE_CONFIG`, `./.imagebridge/config.json`, then `~/.imagebridge/config.json`.

Keep provider keys in environment variables:

```bash
export IMAGEBRIDGE_API_KEY="sk-..."
mkdir -p ~/.imagebridge
python3 <skill-dir>/scripts/image_bridge.py --print-config-template > ~/.imagebridge/config.json
```

## Schema

```json
{
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
        "negative_prompt": "negative_prompt"
      },
      "payload_defaults": {
        "response_format": "b64_json"
      },
      "headers": {
        "Content-Type": "application/json"
      },
      "tls_verify": false,
      "response": {
        "data_path": "data",
        "base64_path": "b64_json",
        "url_path": "url",
        "extension": "png"
      }
    }
  }
}
```

## Fields

- `active`: default provider profile under `providers`.
- `output_dir`: default folder for generated images and metadata.
- `endpoint`: provider URL. You can use a base URL such as `https://api.example.com` or `https://api.example.com/v1`; ImageBridge normalizes it to `/v1/images/generations`. If your provider uses a custom path, provide the full image generation endpoint.
- `api_key_env`: environment variable that stores the API key. The script adds `Authorization: Bearer <key>` when `headers.Authorization` is not already set.
- `headers`: extra request headers. Values can include `${ENV_NAME}` placeholders.
- `tls_verify`: whether to verify HTTPS certificates. Defaults to `false` for broad third-party gateway compatibility. Set to `true` for strict production TLS verification. `IMAGEBRIDGE_TLS_VERIFY=true` overrides config.
- `payload_defaults`: provider-specific JSON values sent on every request.
- `field_map`: maps common CLI concepts to provider payload fields. Use nested dotted paths such as `input.prompt` if the provider requires nested JSON.
- `response`: tells the script how to find image data in the JSON response. OpenAI-compatible APIs usually return `data[].b64_json` or `data[].url`.

## Provider Examples

### OpenAI-compatible endpoint

```json
{
  "active": "compatible",
  "output_dir": "imagebridge-output",
  "providers": {
    "compatible": {
      "endpoint": "https://api.example.com/v1/images/generations",
      "api_key_env": "IMAGEBRIDGE_API_KEY",
      "model": "provider-image-model",
      "field_map": {
        "prompt": "prompt",
        "model": "model",
        "size": "size",
        "n": "n"
      },
      "payload_defaults": {
        "response_format": "b64_json"
      },
      "response": {
        "data_path": "data",
        "base64_path": "b64_json",
        "url_path": "url",
        "extension": "png"
      }
    }
  }
}
```

### Provider that uses `image_size`

```json
{
  "active": "custom",
  "providers": {
    "custom": {
      "endpoint": "https://api.example.com/v1/images/generations",
      "api_key_env": "CUSTOM_IMAGE_API_KEY",
      "model": "custom-image-model",
      "field_map": {
        "prompt": "prompt",
        "model": "model",
        "size": "image_size",
        "n": "batch_size",
        "negative_prompt": "negative_prompt"
      },
      "payload_defaults": {
        "guidance_scale": 7.5,
        "num_inference_steps": 28
      },
      "response": {
        "data_path": "images",
        "base64_path": "b64_json",
        "url_path": "url",
        "extension": "png"
      }
    }
  }
}
```

## Commands

Dry-run without calling the provider:

```bash
python3 <skill-dir>/scripts/image_bridge.py \
  --prompt "赛博朋克城市夜景海报，电影级灯光" \
  --size 1024x1792 \
  --dry-run
```

Generate one image:

```bash
python3 <skill-dir>/scripts/image_bridge.py \
  --prompt "4K 科技发布会主视觉海报，蓝白配色，未来感" \
  --size 1024x1792 \
  --output-dir imagebridge-output
```

Override provider-specific payload:

```bash
python3 <skill-dir>/scripts/image_bridge.py \
  --prompt "产品摄影，白底，高级质感" \
  --param seed=12345 \
  --param scheduler=euler
```

## Troubleshooting

- `No ImageBridge config found`: create `~/.imagebridge/config.json`, `./.imagebridge/config.json`, set `IMAGEBRIDGE_CONFIG`, or pass `--config`.
- `Provider HTTP 401/403`: check API key, account permission, and model access.
- `No image found in provider response`: update `response.data_path`, `response.base64_path`, or `response.url_path` for the provider's actual response JSON.
- Size errors: use a size supported by the configured provider. Many providers do not accept literal `4096x4096`; generate the largest supported image and upscale externally if needed.
