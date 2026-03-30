#!/bin/bash
# Send a command to Link Sprite Buddy
# Usage: ./sprite_cmd.sh <state> [tool_name]
# States: idle, walk, search, think, attack
# Example: ./sprite_cmd.sh search "nmap -sV"
if [ -n "$2" ]; then
    echo -n "$1:$2" | nc -u -w0 127.0.0.1 44444 2>/dev/null
else
    echo -n "$1" | nc -u -w0 127.0.0.1 44444 2>/dev/null
fi
