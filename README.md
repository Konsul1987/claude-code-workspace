# claude-code-workspace

## Auto Mode

This workspace has Claude Code auto mode enabled by default via `.claude/settings.json`.

Auto mode uses a background classifier to review actions before they run, reducing permission prompts while maintaining safety checks. Unlike `bypassPermissions`, auto mode still blocks suspicious actions such as:

- Downloading and executing remote code
- Sending sensitive data to external endpoints
- Production deploys and migrations
- Force pushing or pushing directly to `main`

### Requirements

- Plan: Team, Enterprise, or API
- Model: Claude Sonnet 4.6 or Opus 4.6
- Provider: Anthropic API

### Usage

Auto mode activates automatically when opening this workspace. You can also cycle between permission modes with `Shift+Tab` during a session, or launch with:

```bash
claude --enable-auto-mode
```