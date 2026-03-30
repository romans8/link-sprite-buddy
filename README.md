# Link Sprite Buddy

An animated Link (SSBB) desktop companion that walks around your screen and reacts to Claude Code activity.

## Features

- **Patrol** — Link runs across your screen with sword and shield
- **Sword Slash** — Attack animation with sword thrust and sparks
- **Navi Scan** — Sword attack triggered when Claude Code searches
- **Meditate** — Idle thinking with thought bubbles showing hacker terms
- **Always on top** — Stays visible above terminals and other windows
- **Draggable** — Click and drag Link anywhere on your screen
- **Claude Code hooks** — Automatically reacts to tool usage

## Requirements

- Python 3
- PyQt5 (`pip install PyQt5`)
- Linux (X11 or Wayland via XWayland)

## Usage

```bash
# Launch Link
python3 link_sprite.py &

# Manual commands
./sprite_cmd.sh walk
./sprite_cmd.sh attack
./sprite_cmd.sh search
./sprite_cmd.sh think
./sprite_cmd.sh idle
```

## Controls

| Action | Effect |
|--------|--------|
| Left-click drag | Pick up and move Link |
| Double-click | Sword Slash! |
| Right-click | Context menu |

## Claude Code Integration

Add hooks to your project settings (`.claude/projects/<project>/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Grep|Glob|Agent",
        "hooks": [{"type": "command", "command": "/path/to/sprite_cmd.sh search"}]
      },
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "/path/to/sprite_cmd.sh attack"}]
      },
      {
        "matcher": "Read|Edit|Write",
        "hooks": [{"type": "command", "command": "/path/to/sprite_cmd.sh think"}]
      }
    ]
  }
}
```

## Sprite Credits

Sprites from "Full Link Sprite Sheet (SSBB) COMPLETE" by [the-screen-ko-plus on DeviantArt](https://www.deviantart.com/the-screen-ko-plus/art/Full-Link-Sprite-Sheet-SSBB-COMPLETE-1125548422).
