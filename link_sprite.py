#!/usr/bin/env python3
"""
Link Sprite Buddy — an animated Link (SSBB) desktop companion.

A pixel-art Link from Super Smash Bros. Brawl that lives on your desktop.
He patrols back and forth, attacks with his sword, and reacts to
Claude Code activity via hooks.

Controls:
  Left-click drag  — pick up and move Link
  Double-click     — Sword Slash!
  Right-click      — context menu (change state, quit)

States:
  idle    — standing with sword+shield
  walk    — running patrol with sword drawn
  search  — sword thrust (triggered by Grep/Glob/Agent tools)
  think   — standing idle (triggered by Read/Edit/Write tools)
  attack  — sword thrust (triggered by Bash tool)

Claude Code Integration:
  UDP port 44444 — send state commands:
    echo "search" | nc -u -w0 localhost 44444
    echo "attack" | nc -u -w0 localhost 44444
    echo "think"  | nc -u -w0 localhost 44444

  Configure hooks in .claude/projects/<project>/settings.json:
    {
      "hooks": {
        "PreToolUse": [
          {"matcher": "Grep|Glob|Agent", "hooks": [{"type": "command", "command": "./sprite_cmd.sh search"}]},
          {"matcher": "Bash",            "hooks": [{"type": "command", "command": "./sprite_cmd.sh attack"}]},
          {"matcher": "Read|Edit|Write", "hooks": [{"type": "command", "command": "./sprite_cmd.sh think"}]}
        ]
      }
    }
"""

import sys, os, math, random, socket, threading, time

# XWayland required for always-on-top + mouse events on Wayland
if "WAYLAND_DISPLAY" in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt5.QtWidgets import QApplication, QWidget, QMenu
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import (QPainter, QColor, QPixmap, QPen, QBrush, QFont,
                          QTransform, QImage, QCursor)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.path.join(SCRIPT_DIR, "sprites")

# Display settings
SCALE = 4       # pixel art scale factor
MAX_H = 260     # max display height for any frame
WW = 550        # widget width
WH = 270        # widget height
SOX = 10        # sprite X margin
SOY = 10        # sprite Y margin
UDP_PORT = 44444


def load_frame(name):
    """Load a sprite PNG and scale up with nearest-neighbor."""
    path = os.path.join(FRAMES_DIR, f"{name}.png")
    img = QImage(path)
    if img.isNull():
        return None
    sw = img.width() * SCALE
    sh = img.height() * SCALE
    if sh > MAX_H:
        ratio = MAX_H / sh
        sw = int(sw * ratio)
        sh = MAX_H
    return QPixmap.fromImage(
        img.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.FastTransformation))


# Animation sequences — frame names map to PNG files in sprites/
ANIMS = {
    "idle": [
        "idle_0", "idle_0", "idle_0", "idle_0", "idle_0", "idle_0",
        "idle_1", "idle_1", "idle_0", "idle_0", "idle_0", "idle_0",
    ],
    "walk": [
        "run_0", "run_1", "run_2", "run_3",
        "run_4", "run_5", "run_6", "run_7",
    ],
    "search": [
        "atk_0", "atk_1", "atk_2", "atk_3",
        "atk_4", "atk_5", "atk_6", "atk_7",
    ],
    "think": [
        "idle_0", "idle_0", "idle_0", "idle_0",
        "idle_1", "idle_1", "idle_0", "idle_0",
    ],
    "attack": [
        "atk_0", "atk_1", "atk_2", "atk_3",
        "atk_4", "atk_5", "atk_6", "atk_7",
    ],
}

# Milliseconds per animation frame
FRAME_MS = {
    "idle": 200,
    "walk": 100,
    "search": 120,
    "think": 280,
    "attack": 85,
}


class SpriteCache:
    """Pre-loads and caches all needed sprite frames."""

    def __init__(self):
        self._cache = {}
        needed = set()
        for frames in ANIMS.values():
            for name in frames:
                needed.add(name)
        for name in needed:
            pix = load_frame(name)
            if pix:
                self._cache[name] = pix
            else:
                print(f"[!] Missing sprite: {name}.png")
        print(f"[Link] Loaded {len(self._cache)} sprite frames")

    def get(self, name):
        return self._cache.get(name)


class LinkSprite(QWidget):
    """Main desktop sprite widget."""

    STATES = ("idle", "walk", "search", "think", "attack")

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WW, WH)
        self.setCursor(QCursor(Qt.OpenHandCursor))

        self.sprites = SpriteCache()

        scr = QApplication.primaryScreen().geometry()
        self.scr_w = scr.width()
        self.scr_h = scr.height()

        # State
        self.state = "idle"
        self.anim_frame = 0
        self.frame_accum = 0.0
        self.facing_right = True

        # Position (float for smooth interpolation)
        self.pos_x = float(self.scr_w // 2)
        self.pos_y = float(self.scr_h - WH - 10)
        self.walk_target = self.pos_x
        self.walk_speed = 200.0  # pixels/sec

        # Timers for state duration
        self.state_timer = 0.0
        self.forced_state = None
        self.forced_ttl = 0.0

        # Drag state
        self.dragging = False
        self.drag_offset = QPoint()
        self.last_tick = time.monotonic()

        # 60fps render loop
        self.tick_timer = QTimer()
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(16)

        # Auto behavior every 4 seconds
        self.behavior_timer = QTimer()
        self.behavior_timer.timeout.connect(self.auto_behave)
        self.behavior_timer.start(4000)

        # UDP command listener
        threading.Thread(target=self._udp_listen, daemon=True).start()

        self.move(int(self.pos_x), int(self.pos_y))
        self.show()

    # ── UDP listener ──

    def _udp_listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for port in (UDP_PORT, UDP_PORT + 1):
            try:
                sock.bind(("127.0.0.1", port))
                print(f"[Link] Listening on UDP port {port}")
                break
            except OSError:
                continue
        else:
            print("[Link] Could not bind UDP port")
            return
        while True:
            data, _ = sock.recvfrom(256)
            cmd = data.decode("utf-8", errors="ignore").strip().lower()
            if cmd in self.STATES:
                ttl = {"search": 8, "think": 6, "attack": 4, "walk": 5, "idle": 3}
                self.forced_state = cmd
                self.forced_ttl = float(ttl.get(cmd, 4))
                self.anim_frame = 0

    # ── Auto behavior ──

    def auto_behave(self):
        if self.forced_ttl > 0 or self.dragging:
            return
        r = random.random()
        if r < 0.50:
            self.state = "walk"
            margin = WW + 30
            self.walk_target = float(random.randint(margin, self.scr_w - margin))
        elif r < 0.62:
            self.state = "idle"
            self.state_timer = 3.0
        elif r < 0.74:
            self.state = "search"
            self.state_timer = 5.0
        elif r < 0.86:
            self.state = "think"
            self.state_timer = 4.0
        else:
            self.state = "attack"
            self.state_timer = 2.5
            self.anim_frame = 0

    # ── Main loop ──

    def tick(self):
        now = time.monotonic()
        dt = min(now - self.last_tick, 0.1)
        self.last_tick = now

        if self.dragging:
            self.update()
            return

        # Forced state countdown
        if self.forced_ttl > 0:
            self.state = self.forced_state
            self.forced_ttl -= dt
            if self.forced_ttl <= 0:
                self.forced_state = None
                self.forced_ttl = 0
                self.state = "idle"

        # State timer
        if self.state_timer > 0:
            self.state_timer -= dt
            if self.state_timer <= 0 and self.forced_ttl <= 0:
                self.state = "idle"
                self.state_timer = 0

        # Smooth movement
        if self.state == "walk":
            dist = self.walk_target - self.pos_x
            if abs(dist) < 5:
                self.state = "idle"
                self.state_timer = 2.0
            else:
                direction = 1.0 if dist > 0 else -1.0
                self.facing_right = direction > 0
                step = direction * self.walk_speed * dt
                if abs(step) > abs(dist):
                    step = dist
                self.pos_x += step
                self.move(int(self.pos_x), int(self.pos_y))

        # Advance animation frame
        frame_dur = FRAME_MS.get(self.state, 200) / 1000.0
        self.frame_accum += dt
        while self.frame_accum >= frame_dur:
            self.frame_accum -= frame_dur
            self.anim_frame += 1

        self.update()

    # ── Rendering ──

    def paintEvent(self, event):
        anim = ANIMS.get(self.state, ANIMS["idle"])
        name = anim[self.anim_frame % len(anim)]
        pix = self.sprites.get(name)
        if not pix:
            return

        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)

        # Bottom-align so feet stay at same Y regardless of frame size
        draw_y = SOY + (WH - SOY * 2 - pix.height())

        if self.facing_right:
            sprite_x = SOX
            p.drawPixmap(sprite_x, draw_y, pix)
            text_x = sprite_x + pix.width() + 15
        else:
            sprite_x = WW - SOX - pix.width()
            p.drawPixmap(sprite_x, draw_y,
                         pix.transformed(QTransform().scale(-1, 1)))
            text_x = sprite_x - 160

        # State-specific overlays
        if self.state == "search":
            self._draw_search(p, text_x, draw_y)
        elif self.state == "think":
            self._draw_think(p, text_x, draw_y)
        elif self.state == "attack":
            self._draw_attack(p, text_x, draw_y)

        p.end()

    def _draw_search(self, p, tx, dy):
        f = self.anim_frame
        if f % 10 < 7:
            p.setPen(QPen(QColor(100, 200, 255)))
            p.setFont(QFont("Monospace", 11, QFont.Bold))
            cmds = ["nmap -sV", "gobuster", "ffuf ...",
                    "sqlmap .", "grep -r", "enum4lin", "hydra.."]
            p.drawText(tx, dy + 40, cmds[(f // 10) % len(cmds)])

    def _draw_think(self, p, tx, dy):
        f = self.anim_frame
        phase = (f // 5) % 6
        if phase >= 1:
            p.setBrush(QBrush(QColor(255, 255, 255, 200)))
            p.setPen(QPen(QColor(120, 120, 135), 1))
            p.drawEllipse(tx - 20, dy + 10, 14, 14)
        if phase >= 2:
            p.drawEllipse(tx - 5, dy - 5, 18, 16)
        if phase >= 3:
            p.setBrush(QBrush(QColor(255, 255, 255, 230)))
            p.setPen(QPen(QColor(100, 105, 120), 2))
            p.drawRoundedRect(tx - 10, dy - 30, 155, 48, 12, 12)
            p.setPen(QPen(QColor(50, 55, 75)))
            p.setFont(QFont("Monospace", 11, QFont.Bold))
            thoughts = ["0xDEADBEEF", "CVE-2025-??", "RCE found!",
                        "IDOR vuln?", "SSRF chain", "SQLi blind"]
            p.drawText(tx - 2, dy - 6, thoughts[(f // 10) % len(thoughts)])

    def _draw_attack(self, p, tx, dy):
        f = self.anim_frame
        total = len(ANIMS["attack"])
        phase = f % total
        if 2 <= phase <= 6:
            for _ in range(5):
                sx = tx + random.randint(-20, 30)
                sy = dy + random.randint(10, 80)
                p.fillRect(sx, sy, 6, 6, QColor(255, 255, 210, 240))
            p.setPen(QPen(QColor(255, 50, 50)))
            p.setFont(QFont("Monospace", 16, QFont.Bold))
            yells = ["HYAAA!", "PWNED!", "H4CK!!", "ROOT!!", "TRIFORCE"]
            p.drawText(tx, dy + 50, yells[(f // total) % len(yells)])

    # ── Mouse interaction ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            self.state = "idle"
            self.forced_ttl = 0
            self.state_timer = 0
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_pos = event.globalPos() - self.drag_offset
            self.move(new_pos)
            self.pos_x = float(new_pos.x())
            self.pos_y = float(new_pos.y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(QCursor(Qt.OpenHandCursor))
            pos = self.pos()
            self.pos_x = float(pos.x())
            self.pos_y = float(pos.y())

    def mouseDoubleClickEvent(self, event):
        self.dragging = False
        self.setCursor(QCursor(Qt.OpenHandCursor))
        self.forced_state = "attack"
        self.forced_ttl = 3.0
        self.anim_frame = 0

    def _show_menu(self, pos):
        menu = QMenu()
        labels = {
            "idle": "Idle",
            "walk": "Patrol",
            "search": "Navi Scan",
            "think": "Meditate",
            "attack": "Sword Slash!",
        }
        for state in self.STATES:
            action = menu.addAction(f"  {labels[state]}")
            action.triggered.connect(
                lambda _, s=state: self._set_state(s))
        menu.addSeparator()
        menu.addAction("  Quit").triggered.connect(QApplication.quit)
        menu.exec_(pos)

    def _set_state(self, state):
        self.forced_state = state
        self.forced_ttl = 6.0
        self.anim_frame = 0
        if state == "walk":
            margin = WW + 30
            self.walk_target = float(
                random.randint(margin, self.scr_w - margin))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Link Sprite Buddy")
    LinkSprite()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
