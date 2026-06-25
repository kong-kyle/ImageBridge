---
name: image-bridge
description: Generate images through a configurable third-party or OpenAI-compatible image API. Use when the user asks to generate, create, draw, design, render, or produce an image, poster, wallpaper, avatar, cover, banner, illustration, logo concept, product visual, or explicitly invokes imageBridge, image-bridge, /imageBridge, /image-bridge, or $image-bridge.
---

# ImageBridge

Use this skill to turn a user request into an image-generation API call through the bundled `scripts/image_bridge.py` bridge.

## Workflow

1. Confirm the image intent, final prompt, aspect/size, style, and output folder from the conversation. Ask one concise question only when a missing detail would materially change the result.
2. Locate configuration in this order: `--config`, `IMAGEBRIDGE_CONFIG`, `./.imagebridge/config.json`, then `~/.imagebridge/config.json`.
3. If no configuration exists, help the user create one from `references/configuration.md` or by running `python3 <skill-dir>/scripts/image_bridge.py --print-config-template`. Store secrets in environment variables, not in committed files.
4. Generate the image by running:

   ```bash
   python3 <skill-dir>/scripts/image_bridge.py --prompt "<final prompt>" --size "<size>" --output-dir "<output-dir>"
   ```

   In Claude Code, `<skill-dir>` can be `${CLAUDE_SKILL_DIR}`. In Codex, use the directory that contains this `SKILL.md`.
5. Report the saved image path and metadata path. If the provider returns unsupported size/model errors, adjust only provider-specific parameters that are clearly supported by the configuration or ask for the desired fallback.

## Prompt Handling

- Preserve user intent first. Improve clarity, composition, and style only when it helps image quality.
- For Chinese requests, keep the generated prompt in Chinese unless the configured model works better with English and the user has not constrained language.
- For "4K poster" requests, prefer a portrait poster ratio and the largest configured supported size. Do not claim true 4096 px output unless the provider accepted that size.
- For brand or person likeness requests, ask for reference assets when needed and supported; otherwise state that the run is text-only.

## Safety And Credentials

- Never print API keys, bearer tokens, or full secret-bearing config.
- Prefer `api_key_env` and shell environment variables over inline `api_key`.
- Do not commit `./.imagebridge/config.json`, generated images, or provider responses unless the user explicitly asks.
- If a network call fails because no key, quota, model access, or provider endpoint is configured, explain the exact missing item and stop after giving the next command/config edit.

## Resources

- `scripts/image_bridge.py`: stdlib-only CLI that sends a JSON request, downloads or decodes returned images, and writes metadata.
- `references/configuration.md`: configuration schema, provider examples, installation notes, and troubleshooting.
