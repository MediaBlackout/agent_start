#!/usr/bin/env python3
"""
Flashy Slot Machine - Single-file, colorful, animated terminal game.

Controls
- Space or Enter: spin
- +/- : increase or decrease bet
- A : toggle auto-play (prompt for number of spins or 'u' for until credits run out)
- S : toggle sound
- H : help
- Q : quit

Features
- 3 reels, 3 rows (3x3 grid). Center row is the active payline.
- Colorful ASCII header, animated reels that slow and stop sequentially, win highlight, celebratory big-win animation.
- Cross-platform single-key input (Windows msvcrt, Unix termios/tty) with fallback to input().
- Optional ANSI on Windows via colorama or VT mode; degrades gracefully without colors.
- No external dependencies required; Python 3.8+ compatible.

CLI
- --credits N  : starting credits (default 100)
- --bet N      : starting bet (default 1)
- --demo N     : run N auto-spins then exit (for testing)
- --no-color   : disable color output
- --verbose    : extra info on some operations

Payout rules (exact)
- Center row three '7'  => bet * 50
- Center row three '★'  => bet * 25
- Center row three 'BAR'=> bet * 10
- Center row any other three-of-a-kind => bet * 5
- Center row two-of-a-kind (adjacent pairs: left+center or center+right) => bet * 2
- Center symbol is '🍒' => bet * 1 (even if not matched)
- Otherwise => 0

Copyright
- Public domain / CC0-like usage. No warranty.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import random
import shutil
import signal
from typing import List, Tuple, Optional, Iterable, Dict

# ----------------------------- ANSI and Color Utilities -----------------------------
ESC = "\033["

class Ansi:
    RESET = "\033[0m"
    BOLD = ESC + "1m"
    DIM = ESC + "2m"
    ITALIC = ESC + "3m"
    UNDER = ESC + "4m"
    BLINK = ESC + "5m"
    INVERT = ESC + "7m"

    COLORS = {
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenta": 35,
        "cyan": 36,
        "white": 37,
        "bright_black": 90,
        "bright_red": 91,
        "bright_green": 92,
        "bright_yellow": 93,
        "bright_blue": 94,
        "bright_magenta": 95,
        "bright_cyan": 96,
        "bright_white": 97,
    }

    @staticmethod
    def fg(code: int) -> str:
        return f"\033[{code}m"

    @staticmethod
    def move_up(n: int) -> str:
        return f"\033[{n}A" if n > 0 else ""

    @staticmethod
    def move_down(n: int) -> str:
        return f"\033[{n}B" if n > 0 else ""

    @staticmethod
    def move_right(n: int) -> str:
        return f"\033[{n}C" if n > 0 else ""

    @staticmethod
    def move_left(n: int) -> str:
        return f"\033[{n}D" if n > 0 else ""

    @staticmethod
    def clear_eol() -> str:
        return "\033[K"

    @staticmethod
    def hide_cursor() -> str:
        return "\033[?25l"

    @staticmethod
    def show_cursor() -> str:
        return "\033[?25h"

COLOR_ENABLED = True
VERBOSE = False


def _enable_windows_ansi() -> None:
    """Try to enable ANSI on Windows. Prefer colorama if installed; else use ctypes VT mode."""
    global COLOR_ENABLED
    if os.name != "nt":
        return
    # Try colorama
    try:
        import colorama  # type: ignore
        colorama.just_fix_windows_console()
        return
    except Exception:
        pass
    # Try enabling VT mode via ctypes
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            new_mode = mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        # If fails, we'll still run without colors
        COLOR_ENABLED = False


def supports_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return True  # We'll attempt enable VT or colorama
    return True


def color(text: str, name: Optional[str] = None, *, bold: bool = False, blink: bool = False, invert: bool = False) -> str:
    if not COLOR_ENABLED or not name:
        return text
    code = Ansi.COLORS.get(name)
    if code is None:
        return text
    parts = []
    if bold:
        parts.append(Ansi.BOLD)
    if blink:
        parts.append(Ansi.BLINK)
    if invert:
        parts.append(Ansi.INVERT)
    parts.append(Ansi.fg(code))
    parts.append(text)
    parts.append(Ansi.RESET)
    return "".join(parts)


def center_text(text: str, width: int) -> str:
    if width <= 0:
        return text
    if len(text) >= width:
        return text
    pad = (width - len(text)) // 2
    return " " * pad + text


def beep(freq: int = 880, duration_ms: int = 120) -> None:
    """Attempt to beep cross-platform. On Windows, try winsound.Beep; otherwise ASCII bell."""
    try:
        if os.name == "nt":
            import winsound  # type: ignore
            winsound.Beep(freq, duration_ms)
        else:
            # ASCII bell; many terminals ignore, but it's harmless
            print("\a", end="", flush=True)
    except Exception:
        print("\a", end="", flush=True)

# ----------------------------- Input Handling -----------------------------
class InputHandler:
    """Cross-platform single-key input with optional timeout and fallback to line input."""
    def __init__(self) -> None:
        self._win = (os.name == "nt")
        self._raw_ok = False
        self._using_line_fallback = False
        self._setup()

    def _setup(self) -> None:
        if self._win:
            try:
                import msvcrt  # noqa: F401
                self._raw_ok = True
            except Exception:
                self._using_line_fallback = True
        else:
            # Try termios/tty
            try:
                import termios  # noqa: F401
                import tty  # noqa: F401
                import select  # noqa: F401
                self._raw_ok = True
            except Exception:
                self._using_line_fallback = True

    def get_key(self, timeout: Optional[float] = None, blocking: bool = True) -> Optional[str]:
        """Return a single key as a string, or None on timeout when not blocking.
        Works in raw mode if available. On fallback, uses input() with prompt when blocking.
        """
        if self._using_line_fallback:
            if not blocking:
                # Can't non-blocking in fallback
                return None
            try:
                s = input()
                return s[:1] if s else "\n"
            except EOFError:
                return None

        if self._win:
            try:
                import msvcrt
                if not blocking and timeout is not None:
                    end = time.time() + timeout
                    while time.time() < end:
                        if msvcrt.kbhit():
                            ch = msvcrt.getch()
                            try:
                                return ch.decode("utf-8", errors="ignore")
                            except Exception:
                                return ""
                        time.sleep(0.01)
                    return None
                # blocking
                if timeout is None:
                    while True:
                        if msvcrt.kbhit():
                            ch = msvcrt.getch()
                            try:
                                return ch.decode("utf-8", errors="ignore")
                            except Exception:
                                return ""
                        time.sleep(0.01)
                else:
                    end = time.time() + timeout
                    while time.time() < end:
                        if msvcrt.kbhit():
                            ch = msvcrt.getch()
                            try:
                                return ch.decode("utf-8", errors="ignore")
                            except Exception:
                                return ""
                        time.sleep(0.01)
                    return None
            except Exception:
                # Fallback line input
                if not blocking:
                    return None
                try:
                    s = input()
                    return s[:1] if s else "\n"
                except EOFError:
                    return None
        else:
            # POSIX raw single-char with select
            import termios
            import tty
            import select
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                if not blocking and timeout is not None:
                    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
                    if rlist:
                        ch = os.read(fd, 1)
                        return ch.decode("utf-8", errors="ignore")
                    return None
                if timeout is None:
                    # blocking until a char
                    while True:
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist:
                            ch = os.read(fd, 1)
                            return ch.decode("utf-8", errors="ignore")
                else:
                    end = time.time() + timeout
                    while time.time() < end:
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist:
                            ch = os.read(fd, 1)
                            return ch.decode("utf-8", errors="ignore")
                    return None
            except Exception:
                # fallback to line input
                try:
                    s = input()
                    return s[:1] if s else "\n"
                except EOFError:
                    return None
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

    def request_line(self, prompt: str) -> Optional[str]:
        """Prompt the user for a full line input, regardless of raw mode availability."""
        try:
            return input(prompt)
        except EOFError:
            return None

# ----------------------------- Symbols and Paytable -----------------------------
# Symbol set with weights (higher = more common)
SYMBOL_WEIGHTS: Dict[str, int] = {
    "7": 2,
    "★": 4,
    "BAR": 6,
    "🍒": 8,
    "A": 12,
    "K": 12,
    "Q": 12,
}

# Map symbols to display colors
SYMBOL_COLORS: Dict[str, str] = {
    "7": "bright_red",
    "★": "bright_yellow",
    "BAR": "bright_magenta",
    "🍒": "red",
    "A": "bright_blue",
    "K": "bright_green",
    "Q": "bright_cyan",
}

SYMBOLS: List[str] = list(SYMBOL_WEIGHTS.keys())
WEIGHTS: List[int] = [SYMBOL_WEIGHTS[s] for s in SYMBOLS]

DEFAULT_CREDITS = 100
DEFAULT_BET = 1

# Animation tuning constants
ANIM_MIN_DELAY = 0.02
ANIM_MAX_DELAY = 0.12
REEL_STOP_FRAMES_BASE = 22
REEL_STOP_FRAMES_STEP = 8

# Big win threshold multiplier
BIG_WIN_MULT = 25  # payout >= bet * 25 triggers big celebration

# RNG
RNG = random.SystemRandom()

# ----------------------------- Reel -----------------------------
class Reel:
    """Represents a reel capable of producing weighted random symbols for top/mid/bottom."""
    def __init__(self, symbols: List[str], weights: List[int]) -> None:
        if not symbols or len(symbols) != len(weights):
            raise ValueError("Invalid symbols/weights")
        self.symbols = symbols
        self.weights = weights

    def spin_once(self) -> Tuple[str, str, str]:
        # For simplicity, independently sample top/middle/bottom respecting weights.
        # This is not a physical strip, but good enough for animation.
        top = RNG.choices(self.symbols, weights=self.weights, k=1)[0]
        mid = RNG.choices(self.symbols, weights=self.weights, k=1)[0]
        bot = RNG.choices(self.symbols, weights=self.weights, k=1)[0]
        return (top, mid, bot)

    def frame(self) -> Tuple[str, str, str]:
        """Generate a transient frame for animation (random triple)."""
        return self.spin_once()

# ----------------------------- Renderer -----------------------------
class Renderer:
    def __init__(self, *, no_color: bool = False) -> None:
        global COLOR_ENABLED
        COLOR_ENABLED = COLOR_ENABLED and supports_color() and (not no_color)
        if os.name == "nt":
            _enable_windows_ansi()
        self.term_width = shutil.get_terminal_size((80, 24)).columns
        self.header_lines = 0
        self.reel_block_lines = 0
        self.status_lines = 0
        self.help_visible = False

    def update_terminal_size(self) -> None:
        self.term_width = shutil.get_terminal_size((80, 24)).columns

    def draw_header(self) -> None:
        self.update_terminal_size()
        logo = [
            r"  ______ _           _           ____ _ _       _   __  __ _           _           ",
            r" |  ____| |         | |         / ___| (_)     | | |  \/  (_)         | |          ",
            r" | |__  | | __ _  __| | ___  ___\___ \ |_  __ _| | | \  / |_ _ __   __| | ___ _ __ ",
            r" |  __| | |/ _` |/ _` |/ _ \/ __|___) | | |/ _` | | | |\/| | | '_ \ / _` |/ _ \ '__|",
            r" | |____| | (_| | (_| |  __/\__ \____/| | | (_| | | | |  | | | | | | (_| |  __/ |   ",
            r" |______|_|\__,_|\__,_|\___||___/     |_|_|\__,_|_| |_|  |_|_|_| |_|\__,_|\___|_|   ",
        ]
        color_seq = ["bright_magenta", "bright_cyan", "bright_green", "bright_yellow", "bright_red", "bright_blue"]
        for i, line in enumerate(logo):
            c = color(line, color_seq[i % len(color_seq)], bold=True)
            print(center_text(c, self.term_width))
        controls = "[Space/Enter]=Spin  [+/-]=Bet  A=Auto  S=Sound  H=Help  Q=Quit"
        print(center_text(color(controls, "bright_white", bold=True), self.term_width))
        self.header_lines = len(logo) + 1

    def _cell(self, sym: str, highlight: bool = False) -> str:
        # Prepare a fixed-width cell content like [sym], padded to width 3 inside
        inner = sym.center(3)
        txt = f"[{inner}]"
        col = SYMBOL_COLORS.get(sym, "white")
        if highlight:
            return color(txt, col, bold=True, invert=True)
        else:
            return color(txt, col, bold=True)

    def _draw_box(self, grid: List[List[str]], highlight_positions: Optional[List[Tuple[int, int]]] = None) -> None:
        if highlight_positions is None:
            highlight_positions = []
        # Build lines
        # Compute width: 3 cells of [xxx] with a space between => each cell 5 chars => 5*3 + 2 spaces + borders
        # We'll include a margin padding.
        rows = []
        top_border = "+" + "-" * (6 * 3 + 2) + "+"  # approximate
        rows.append(top_border)
        for r in range(3):
            line_cells = []
            for c in range(3):
                hl = (r, c) in highlight_positions
                line_cells.append(self._cell(grid[r][c], highlight=hl))
            row_text = " " + " ".join(line_cells) + " "
            rows.append("|" + row_text + "|")
        rows.append(top_border)
        for line in rows:
            print(center_text(line, self.term_width))
        self.reel_block_lines = len(rows)

    def draw_status(self, credits: int, bet: int, last_win: int, spins: int, high_win: int, sound_on: bool, auto: Optional[int]) -> None:
        status = f"Credits: {credits}   Bet: {bet}   Last Win: {last_win}   Spins: {spins}   High Win: {high_win}   Sound: {'ON' if sound_on else 'OFF'}   Auto: {auto if auto is not None else 'OFF'}"
        print(center_text(color(status, "bright_white", bold=True), self.term_width))
        self.status_lines = 1

    def draw_help(self) -> None:
        help_text = [
            "Controls:",
            "  - Space/Enter: Spin",
            "  - +/- : Increase/Decrease bet",
            "  - A : Toggle auto-play (enter number of spins or 'u' for until credits run out)",
            "  - S : Toggle sound",
            "  - H : Toggle this help",
            "  - Q : Quit",
            "Payouts:",
            "  - 777: bet x 50",
            "  - ★★★: bet x 25",
            "  - BAR BAR BAR: bet x 10",
            "  - Any other three-of-a-kind: bet x 5",
            "  - Any adjacent two-of-a-kind (L+C or C+R): bet x 2",
            "  - Cherry in center: bet x 1",
        ]
        for line in help_text:
            print(center_text(color(line, "bright_white"), self.term_width))
        self.help_visible = True

    def clear_help(self) -> None:
        if self.help_visible:
            # Move cursor up lines of help and clear them
            lines = 12
            sys.stdout.write(Ansi.move_up(lines))
            for _ in range(lines):
                sys.stdout.write(Ansi.clear_eol() + "\n")
            sys.stdout.flush()
            self.help_visible = False

    def _move_up_reel_block(self) -> None:
        total = self.reel_block_lines + self.status_lines
        if total > 0:
            sys.stdout.write(Ansi.move_up(total))
            sys.stdout.flush()

    def animate_spin(self, reels: List[Reel], final_cols: List[Tuple[str, str, str]]) -> None:
        # Create sequential stopping frames for each reel
        stop_frames = [
            REEL_STOP_FRAMES_BASE + REEL_STOP_FRAMES_STEP * i + RNG.randint(-2, 2)
            for i in range(3)
        ]
        max_frames = max(stop_frames)
        # Initialize current grid frames with random frames
        grid = [[" ", " ", " "] for _ in range(3)]
        # First draw initial empty box to reserve space
        self._draw_box([[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]])
        # Animation loop
        for frame in range(max_frames + 1):
            # Update per reel
            columns = []
            for col_idx in range(3):
                if frame < stop_frames[col_idx]:
                    columns.append(reels[col_idx].frame())
                else:
                    columns.append(final_cols[col_idx])
            # Build grid from columns
            for r in range(3):
                for c in range(3):
                    grid[r][c] = columns[c][r]
            # Redraw in place
            self._move_up_reel_block()
            self._draw_box(grid)
            # easing delay based on proportion to furthest stop
            progress = min(frame / max(1, max_frames), 1.0)
            delay = ANIM_MIN_DELAY + (ANIM_MAX_DELAY - ANIM_MIN_DELAY) * (progress ** 1.2)
            time.sleep(delay)

    def highlight_and_message(self, grid: List[List[str]], highlight_positions: List[Tuple[int, int]], message: str, big: bool = False) -> None:
        # Blink the highlight a few times and show message line below status
        blinks = 5 if big else 3
        for i in range(blinks):
            # On/Off blink effect via invert toggle
            hl = highlight_positions if (i % 2 == 0) else []
            self._move_up_reel_block()
            self._draw_box(grid, hl)
            time.sleep(0.08)
        # Print message line
        msg_col = "bright_yellow" if not big else "bright_red"
        print(center_text(color(message, msg_col, bold=True), self.term_width))
        self.status_lines = 1  # we printed one status-like line

# ----------------------------- Slot Machine Logic -----------------------------
class SlotMachine:
    def __init__(self, credits: int = DEFAULT_CREDITS, bet: int = DEFAULT_BET, *, no_color: bool = False, verbose: bool = False) -> None:
        global VERBOSE
        VERBOSE = verbose
        self.credits = max(0, int(credits))
        self.bet = max(1, int(bet))
        self.reels = [Reel(SYMBOLS, WEIGHTS) for _ in range(3)]
        self.renderer = Renderer(no_color=no_color)
        self.input = InputHandler()
        self.spins = 0
        self.last_win = 0
        self.high_win = 0
        self.auto_remaining: Optional[int] = None
        self.sound_on = True
        self.quit = False
        self._hide_cursor = False

    def _require_bet_affordable(self) -> None:
        if self.bet > self.credits:
            # Reduce bet to max affordable (but at least 1)
            self.bet = max(1, self.credits)

    def _grid_from_cols(self, cols: List[Tuple[str, str, str]]) -> List[List[str]]:
        # Convert column tuples to grid (rows x cols)
        grid = [[cols[0][0], cols[1][0], cols[2][0]],
                [cols[0][1], cols[1][1], cols[2][1]],
                [cols[0][2], cols[1][2], cols[2][2]]]
        return grid

    def compute_payout(self, center_row: List[str], bet: int) -> Tuple[int, List[Tuple[int, int]]]:
        """Compute payout based on center row. Returns (payout, highlight_positions)."""
        l, c, r = center_row
        payout = 0
        highlight: List[Tuple[int, int]] = []
        # Three of a kind special cases
        if l == c == r:
            if l == "7":
                payout = bet * 50
            elif l == "★":
                payout = bet * 25
            elif l == "BAR":
                payout = bet * 10
            else:
                payout = bet * 5
            highlight = [(1, 0), (1, 1), (1, 2)]
            return payout, highlight
        # Two of a kind (adjacent only: L+C or C+R)
        two_kind = 0
        if l == c:
            two_kind = bet * 2
            highlight = [(1, 0), (1, 1)]
        elif c == r:
            two_kind = bet * 2
            highlight = [(1, 1), (1, 2)]
        # Cherry center small win
        cherry_win = bet if c == "🍒" else 0
        # Choose maximum payout among applicable rules (avoid double counting)
        payout = max(two_kind, cherry_win)
        if payout == cherry_win and cherry_win > 0:
            highlight = [(1, 1)]
        return payout, highlight

    def _celebrate(self, amount: int) -> None:
        if amount <= 0:
            return
        if amount >= self.bet * BIG_WIN_MULT and self.sound_on:
            # a couple of beeps
            beep(1046, 120)
            time.sleep(0.03)
            beep(1318, 150)

    def _spin_once(self) -> Tuple[List[List[str]], int, List[Tuple[int, int]]]:
        # Deduct bet
        self._require_bet_affordable()
        if self.bet <= 0 or self.bet > self.credits:
            return self._grid_from_cols([self.reels[0].frame(), self.reels[1].frame(), self.reels[2].frame()]), 0, []
        self.credits -= self.bet
        # Determine final columns for 3 reels
        final_cols = [self.reels[0].spin_once(), self.reels[1].spin_once(), self.reels[2].spin_once()]
        # Animate
        self.renderer.animate_spin(self.reels, final_cols)
        # Build final grid
        grid = self._grid_from_cols(final_cols)
        center_row = [grid[1][0], grid[1][1], grid[1][2]]
        payout, highlight = self.compute_payout(center_row, self.bet)
        self.credits += payout
        self.last_win = payout
        self.high_win = max(self.high_win, payout)
        self.spins += 1
        return grid, payout, highlight

    def _toggle_auto(self) -> None:
        if self.auto_remaining is None:
            line = self.input.request_line("Enter auto-spins count (e.g., 20) or 'u' for until credits: ")
            if line is None:
                return
            line = line.strip().lower()
            if line == 'u':
                self.auto_remaining = 10**9  # effectively until credits run out
            else:
                try:
                    n = int(line)
                    if n > 0:
                        self.auto_remaining = n
                except Exception:
                    pass
        else:
            self.auto_remaining = None

    def _adjust_bet(self, delta: int) -> None:
        self.bet = max(1, self.bet + delta)
        self._require_bet_affordable()

    def _print_static(self) -> None:
        print(Ansi.hide_cursor(), end="")
        self._hide_cursor = True
        self.renderer.draw_header()

    def _cleanup(self) -> None:
        if self._hide_cursor:
            print(Ansi.show_cursor(), end="")
            self._hide_cursor = False
        sys.stdout.flush()

    def run(self, *, demo_spins: Optional[int] = None) -> None:
        # Handle Ctrl-C gracefully
        def _sigint_handler(signum, frame):
            self.quit = True
        try:
            signal.signal(signal.SIGINT, _sigint_handler)
        except Exception:
            pass

        self._print_static()
        grid = [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]]
        self.renderer._draw_box(grid)
        self.renderer.draw_status(self.credits, self.bet, self.last_win, self.spins, self.high_win, self.sound_on, self.auto_remaining)

        if demo_spins is not None and demo_spins > 0:
            self.auto_remaining = demo_spins

        while not self.quit:
            # Update status line if needed (e.g., after toggles)
            self.renderer.draw_status(self.credits, self.bet, self.last_win, self.spins, self.high_win, self.sound_on, self.auto_remaining)

            # Auto-play logic
            want_spin = False
            if self.auto_remaining is not None:
                if self.credits >= self.bet and self.auto_remaining > 0:
                    want_spin = True
                    self.auto_remaining -= 1
                else:
                    self.auto_remaining = None
            else:
                # Wait for key
                key = self.input.get_key(timeout=0.15, blocking=False)
                if key:
                    k = key
                    if k in ('\r', '\n', ' '):
                        want_spin = True
                    elif k in ('q', 'Q'):
                        self.quit = True
                    elif k == '+':
                        self._adjust_bet(+1)
                    elif k == '-':
                        self._adjust_bet(-1)
                    elif k in ('a', 'A'):
                        self._toggle_auto()
                    elif k in ('s', 'S'):
                        self.sound_on = not self.sound_on
                    elif k in ('h', 'H'):
                        if self.renderer.help_visible:
                            self.renderer.clear_help()
                        else:
                            self.renderer.draw_help()

            if want_spin:
                if self.bet <= 0 or self.bet > self.credits:
                    # Cannot afford; beep softly and continue
                    if self.sound_on:
                        beep(600, 80)
                    continue
                grid, payout, highlight = self._spin_once()
                big = payout >= self.bet * BIG_WIN_MULT
                # Show highlight and message
                if payout > 0:
                    msg = f"YOU WIN {payout} credits!"
                    self.renderer.highlight_and_message(grid, highlight, msg, big=big)
                    if self.sound_on:
                        # small chime
                        if big:
                            self._celebrate(payout)
                        else:
                            beep(988, 80)
                    # Redraw status after message
                    self.renderer.draw_status(self.credits, self.bet, self.last_win, self.spins, self.high_win, self.sound_on, self.auto_remaining)
                else:
                    # Draw final grid without highlight and a small pause
                    self.renderer._move_up_reel_block()
                    self.renderer._draw_box(grid)
                    if self.sound_on:
                        time.sleep(0.05)
                # Short delay between auto spins
                if self.auto_remaining is not None:
                    time.sleep(0.25)

            # End if no credits
            if self.credits <= 0 and (self.auto_remaining is not None):
                self.auto_remaining = None

            # In demo mode, exit when finished
            if demo_spins is not None and (self.auto_remaining is None) and (not want_spin):
                break

        # Print summary
        print()
        summary = f"Thanks for playing! Spins: {self.spins}  Credits: {self.credits}  High Win: {self.high_win}"
        print(center_text(color(summary, "bright_white", bold=True), self.renderer.term_width))
        self._cleanup()

# ----------------------------- Main Entry -----------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Flashy Slot Machine - colorful terminal game")
    ap.add_argument("--credits", type=int, default=DEFAULT_CREDITS, help="Starting credits (default 100)")
    ap.add_argument("--bet", type=int, default=DEFAULT_BET, help="Starting bet (default 1)")
    ap.add_argument("--demo", type=int, default=None, help="Run N auto-spins then exit")
    ap.add_argument("--no-color", action="store_true", help="Disable color output")
    ap.add_argument("--verbose", action="store_true", help="Verbose output")
    return ap.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    credits = args.credits
    bet = args.bet
    no_color = args.no_color
    verbose = args.verbose
    demo = args.demo

    if credits < 0:
        credits = DEFAULT_CREDITS
    if bet <= 0:
        bet = DEFAULT_BET

    game = SlotMachine(credits=credits, bet=bet, no_color=no_color, verbose=verbose)
    try:
        game.run(demo_spins=demo)
    except KeyboardInterrupt:
        # Ensure cleanup
        game._cleanup()
        print("\nInterrupted. Bye!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
