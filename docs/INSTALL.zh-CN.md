# ImageBridge 安装使用说明

ImageBridge 是一份可同时安装到 Codex 和 Claude Code 的 Agent Skill，用来通过可配置的第三方生图模型生成图片、海报、头像、壁纸、封面图等。

核心 skill 只有一份：`skills/image-bridge/SKILL.md`。

## 1. 安装

同时安装到 Codex 和 Claude Code：

```bash
curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh | bash
```

只安装 Codex：

```bash
curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh | bash -s -- codex
```

只安装 Claude Code：

```bash
curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh | bash -s -- claude
```

安装器会完成两件事：

- 安装 skill 到 Codex 或 Claude Code。
- 提示输入 Base URL、Key 和 Model，并生成本机配置。

安装后路径：

| 工具 | 路径 | 调用方式 |
| --- | --- | --- |
| Codex | `${CODEX_HOME:-~/.codex}/skills/image-bridge/SKILL.md` | `$image-bridge` 或 `/skills` |
| Claude Code | `~/.claude/skills/image-bridge/SKILL.md` | `/image-bridge` |

如果本机曾经安装过旧版 `~/.agents/skills/image-bridge`，安装器会自动删除这个旧副本，避免 Codex 技能列表出现两个 ImageBridge。

Codex 安装后请重启 Codex，让新 skill 被重新扫描。

## 2. 配置 url、key 和 model

安装时按提示输入：

```text
Image API URL: https://api.example.com
Image API Key: sk-...
Image model: provider-image-model
```

输入 `https://api.example.com` 或 `https://api.example.com/v1` 时，ImageBridge 会自动使用 `/v1/images/generations`。如果服务商使用自定义路径，也可以直接填写完整生图 endpoint。

安装器会写入：

```text
~/.imagebridge/config.json
~/.imagebridge/.env
```

ImageBridge 会自动读取这个 `.env` 文件。需要在 shell 里手动运行脚本时，可以执行：

```bash
source ~/.imagebridge/.env
```

生成的 `~/.imagebridge/config.json` 结构如下：

```json
{
  "active": "default",
  "output_dir": "imagebridge-output",
  "providers": {
    "default": {
      "endpoint": "https://api.example.com/v1/images/generations",
      "api_key_env": "IMAGEBRIDGE_API_KEY",
      "model": "provider-image-model",
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

无交互安装：

```bash
IMAGEBRIDGE_URL="https://api.example.com/v1/images/generations" \
IMAGEBRIDGE_API_KEY="sk-..." \
IMAGEBRIDGE_MODEL="provider-image-model" \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh)"
```

默认不校验 TLS 证书，兼容内网代理、自签名证书和部分第三方网关。如果你需要严格校验证书，可以开启：

```bash
IMAGEBRIDGE_URL="https://api.example.com" \
IMAGEBRIDGE_API_KEY="sk-..." \
IMAGEBRIDGE_MODEL="provider-image-model" \
IMAGEBRIDGE_TLS_VERIFY=true \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh)"
```

也可以在 `~/.imagebridge/config.json` 里设置：

```json
{
  "tls_verify": true
}
```

公网生产环境建议开启证书校验。

如果服务商不是 OpenAI-compatible 字段名，只改 `field_map` 即可。例如服务商使用 `image_size`：

```json
{
  "field_map": {
    "prompt": "prompt",
    "model": "model",
    "size": "image_size",
    "n": "batch_size",
    "negative_prompt": "negative_prompt"
  }
}
```

如果服务商响应不是 `data[].b64_json` 或 `data[].url`，按实际响应修改 `response.data_path`、`response.base64_path` 或 `response.url_path`。

## 3. 使用

在 Codex 中可以自然语言触发：

```text
帮我生成一张 4K 科技发布会海报，竖版，蓝白配色，未来感
```

也可以显式触发：

```text
Use $image-bridge to generate a 4K poster for a new AI image product.
```

在 Claude Code 中使用：

```text
/image-bridge 帮我生成一张 4K 的科幻电影海报
```

直接测试脚本：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/image-bridge/scripts/image_bridge.py" \
  --prompt "赛博朋克城市夜景海报，电影级灯光" \
  --size 1024x1792 \
  --dry-run
```

真实生成：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/image-bridge/scripts/image_bridge.py" \
  --prompt "4K 科技发布会主视觉海报，蓝白配色，未来感" \
  --size 1024x1792 \
  --output-dir imagebridge-output
```

输出目录会包含图片和同名 `.metadata.json` 元数据文件。
