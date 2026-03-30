#!/bin/bash
# Send a command to Link Sprite Buddy
# Usage: ./sprite_cmd.sh <state>
# States: idle, walk, search, think, attack
echo -n "$1" | nc -u -w0 127.0.0.1 44444 2>/dev/null
