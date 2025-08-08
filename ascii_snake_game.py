#!/usr/bin/env python3
"""
ascii_snake_game.py

A self-contained, single-file terminal Snake game using curses.
- ASCII graphics with a border, a snake, and food at random positions
- Snake grows when eating food
- Game ends on wall or self-collision
- Score shown at the top
- Adjustable speed via command line: easy, medium, hard
- Pause/resume with Space; Quit with Q
- Colorful output using curses color pairs (ANSI colors used for a banner when possible)

Usage:
  python ascii_snake_game.py --difficulty easy
  python ascii_snake_game.py --difficulty hard
"""

import curses
import random
import time
import argparse
import sys

# Simple ANSI banner for colorful output before entering curses (if terminal supports)
def print_ansi_banner():
    try:
        # Bold green title
        print("\033[1;32mASCII SNAKE GAME\033[0m")
        print("\033[1;33mMove with Arrow Keys or WASD. Space to pause/resume. Q to quit.\033[0m")
        print()
    except Exception:
        # If terminal doesn't support ANSI codes, silently skip
        pass

# Determine initial direction delta from a key press
def key_to_delta(key):
    # Arrow keys
    if key == curses.KEY_UP:
        return (-1, 0)
    if key == curses.KEY_DOWN:
        return (1, 0)
    if key == curses.KEY_LEFT:
        return (0, -1)
    if key == curses.KEY_RIGHT:
        return (0, 1)
    # WASD (case-insensitive)
    if key in (ord('w'), ord('W')):
        return (-1, 0)
    if key in (ord('s'), ord('S')):
        return (1, 0)
    if key in (ord('a'), ord('A')):
        return (0, -1)
    if key in (ord('d'), ord('D')):
        return (0, 1)
    return None

# Place food on a random free cell not occupied by the snake
def place_food(snake, max_y, max_x):
    while True:
        y = random.randint(1, max_y - 2)
        x = random.randint(1, max_x - 2)
        if (y, x) not in snake:
            return (y, x)

def main(stdscr, delay, difficulty_label):
    # Initialize curses options
    curses.curs_set(0)          # Hide cursor
    stdscr.nodelay(True)        # Non-blocking input
    stdscr.keypad(True)         # Enable special keys
    curses.noecho()
    curses.start_color()
    curses.use_default_colors()

    # Color pairs: (pair_number, foreground, background)
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # Snake head
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # Snake body
    curses.init_pair(3, curses.COLOR_RED, -1)     # Food
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # Border/Status

    HEAD_ATTR = curses.color_pair(1) | curses.A_BOLD
    BODY_ATTR = curses.color_pair(2)
    FOOD_ATTR = curses.color_pair(3) | curses.A_BOLD
    BORDER_ATTR = curses.color_pair(4)

    HEAD_CHAR = 'O'
    BODY_CHAR = 'o'
    FOOD_CHAR = '*'

    # Determine playable area
    max_y, max_x = stdscr.getmaxyx()
    if max_y < 12 or max_x < 20:
        stdscr.clear()
        msg = "Terminal too small for Snake. Resize and try again."
        stdscr.addstr(0, 0, msg)
        stdscr.refresh()
        time.sleep(2.5)
        return

    # Top status line (score and controls)
    status_line_y = 0
    status_line_x = 0

    # Create a window for the playfield with a border
    # Reserve a few rows at the top for status text
    playfield_top = 2
    playfield_height = max_y - playfield_top - 1
    playfield_width = max_x - 2
    win = curses.newwin(playfield_height, playfield_width, playfield_top, 1)
    win.keypad(True)
    win.nodelay(True)

    # Initial snake setup (middle of the field)
    start_y = playfield_height // 2
    start_x = playfield_width // 2

    snake = [
        (start_y, start_x - 1),
        (start_y, start_x),
        (start_y, start_x + 1),
    ]
    direction = (0, 1)  # moving right initially

    food = place_food(snake, playfield_height, playfield_width)

    score = 0
    paused = False
    game_over = False

    # Draw initial static border
    win.border()

    # Main game loop
    while True:
        # Display score and status at the top line
        status = f" Score: {score}  |  Difficulty: {difficulty_label}  |  Space: Pause/Resume  |  Q: Quit "
        stdscr.attron(BORDER_ATTR)
        stdscr.addstr(status_line_y, status_line_x, status[:max_x-1])
        stdscr.attroff(BORDER_ATTR)
        stdscr.refresh()

        # Handle user input
        try:
            key = win.getch()
        except curses.error:
            key = -1  # No input

        if key != -1:
            if key in (ord('q'), ord('Q')):
                break  # Quit game
            if key == ord(' '):  # Pause/Resume
                paused = not paused
                if paused:
                    # Show paused message
                    win.addstr(playfield_height // 2, (playfield_width // 2) - 4, "PAUSED", curses.A_BOLD | curses.A_BLINK)
                    win.refresh()
                else:
                    # Clear paused message
                    win.addstr(playfield_height // 2, (playfield_width // 2) - 4, "      ")
                    win.refresh()
                continue  # Skip movement while toggling pause

            # Movement input
            new_dir = key_to_delta(key)
            if new_dir:
                # Prevent 180-degree turn
                if (new_dir[0] != -direction[0] or new_dir[1] != -direction[1]):
                    direction = new_dir

        if not paused and not game_over:
            # Compute new head
            head_y, head_x = snake[-1]
            dy, dx = direction
            new_head = (head_y + dy, head_x + dx)

            # Collision with wall
            if (new_head[0] <= 0 or new_head[0] >= playfield_height - 1 or
                new_head[1] <= 0 or new_head[1] >= playfield_width - 1):
                game_over = True
            # Collision with self
            elif new_head in snake:
                game_over = True
            else:
                # Move forward
                snake.append(new_head)

                # Check for food
                if new_head == food:
                    score += 1
                    food = place_food(snake, playfield_height, playfield_width)
                else:
                    # Remove tail
                    tail_y, tail_x = snake.pop(0)

        # Rendering
        win.clear()
        win.border()

        # Draw food
        fy, fx = food
        win.addch(fy, fx, FOOD_CHAR, FOOD_ATTR)

        # Draw snake
        for idx, (sy, sx) in enumerate(snake):
            if idx == len(snake) - 1:
                win.addch(sy, sx, HEAD_CHAR, HEAD_ATTR)
            else:
                win.addch(sy, sx, BODY_CHAR, BODY_ATTR)

        win.refresh()

        if game_over:
            # Show game over message
            msg = " GAME OVER - Press Q to quit "
            win.addstr(playfield_height // 2, max(0, (playfield_width - len(msg)) // 2), msg,
                       curses.A_BOLD | curses.A_BLINK | curses.color_pair(3))
            win.refresh()
            # Wait for user to quit (only quit is allowed)
            while True:
                ch = stdscr.getch()
                if ch in (ord('q'), ord('Q')):
                    return
                time.sleep(0.05)

        # Delay depending on difficulty to control speed
        time.sleep(delay)

if __name__ == "__main__":
    # Argument parsing for difficulty
    parser = argparse.ArgumentParser(description="ASCII Snake Game (terminal, curses).")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"],
                        default="medium", help="Game speed: easy, medium, or hard.")
    args = parser.parse_args()

    # Map difficulty to delay (seconds per tick)
    DIFFICULTY_DELAY = {
        "easy": 0.15,
        "medium": 0.10,
        "hard": 0.07,
    }
    delay = DIFFICULTY_DELAY[args.difficulty]

    # Optional ANSI banner before curses (works in most terminals)
    print_ansi_banner()

    # Start curses application
    try:
        curses.wrapper(main, delay, args.difficulty)
    except KeyboardInterrupt:
        pass  # Graceful exit on Ctrl+C
    except Exception as e:
        # If something goes wrong, reset terminal and print the error
        print(f"Error: {e}", file=sys.stderr)
