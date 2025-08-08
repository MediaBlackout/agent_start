# time_party.py
import time
import datetime
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.live import Live
from rich.style import Style
import random

# Configure your console
console = Console()

# Define some colors and styles
colors = ["red", "green", "blue", "yellow", "magenta", "cyan", "white", "bright_red", "bright_green", "bright_blue", "bright_magenta"]
glow_styles = [
    Style(color=random.choice(colors), bold=True, blink=False),
    Style(color=random.choice(colors), bold=True, blink=True),
    Style(color=random.choice(colors), reverse=True),
]

def get_styled_time():
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %d %B %Y")

    # Random color every frame
    color1 = random.choice(colors)
    color2 = random.choice(colors)
    color3 = random.choice(colors)

    time_text = Text(f"{time_str}", style=Style(color=color1, bold=True, blink=True))
    date_text = Text(f"{date_str}", style=Style(color=color2, italic=True))

    panel = Panel(
        Align.center(
            Text.assemble(
                "\n", 
                time_text, 
                "\n\n", 
                date_text,
                "\n"
            ),
            vertical="middle"
        ),
        title="🕒 TIME PARTY 🕒",
        subtitle="Ctrl+C to exit",
        border_style=color3,
        padding=(1, 4),
    )
    return panel

def run_time_party():
    try:
        with Live(get_styled_time(), refresh_per_second=2, screen=True) as live:
            while True:
                time.sleep(0.5)
                live.update(get_styled_time())
    except KeyboardInterrupt:
        console.clear()
        console.print("🎉 Thanks for partying with the clock! 🎉", style="bold magenta")

if __name__ == "__main__":
    run_time_party()
