# ImageBridge

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

安装时会提示输入生图接口 URL、API Key 和模型名，并自动生成 `~/.imagebridge/config.json` 与 `~/.imagebridge/.env`。

## 2. 配置 url、key 和 model

按安装器提示填写：

```text
Image API URL: https://api.example.com/v1/images/generations
Image API Key: sk-...
Image model: provider-image-model
```

安装器会自动写入配置，通常可以直接使用。需要在 shell 里手动运行脚本时，可以执行：

```bash
source ~/.imagebridge/.env
```

也可以无交互安装：

```bash
IMAGEBRIDGE_URL="https://api.example.com/v1/images/generations" \
IMAGEBRIDGE_API_KEY="sk-..." \
IMAGEBRIDGE_MODEL="provider-image-model" \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/kong-kyle/ImageBridge/main/install.sh)"
```

## 3. 使用

Codex：

```text
Use $image-bridge to generate a 4K product launch poster, portrait layout, futuristic lighting.
```

Claude Code：

```text
/image-bridge 帮我生成一张 4K 科技发布会海报，竖版，蓝白配色
```

完整中文安装和使用说明见 [docs/INSTALL.zh-CN.md](docs/INSTALL.zh-CN.md)。
