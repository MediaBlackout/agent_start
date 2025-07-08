import json
import os
import gettext
import logging
from typing import Union, Dict, Any, Optional, List
from datetime import datetime
from io import BytesIO

# Data visualization
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import plotly.io as pio

# TTS & Voice
from gtts import gTTS

# HTML rendering
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from markupsafe import Markup
from bs4 import BeautifulSoup

# i18n
from babel.dates import format_datetime
from babel.numbers import format_decimal

# Accessibility & export
from weasyprint import HTML

# Static paths
TEMPLATE_DIR = "templates"
STATIC_DIR = "static"
LOCALES_DIR = "locales"

# Configuration
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml']),
    cache_size=50
)

gettext.bindtextdomain('messages', LOCALES_DIR)
gettext.textdomain('messages')
_ = gettext.gettext

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalizationHelper:
    def __init__(self, locale='en_US'):
        self.locale = locale

    def localize_date(self, dt: datetime) -> str:
        return format_datetime(dt, locale=self.locale)

    def localize_number(self, value: float, digits: int = 1) -> str:
        return format_decimal(value, format=f"#,##0.{ '0' * digits }", locale=self.locale)


class TemplateRenderer:
    def __init__(self, theme='default'):
        self.theme = theme

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        try:
            full_path = os.path.join(self.theme, f"{template_name}.html")
            template = env.get_template(full_path)
            return template.render(**context)
        except TemplateNotFound as e:
            logger.error(f"Template not found: {template_name} - {e}")
            return "<p>Template Error</p>"


class JSONFormatter:
    def format_rest(self, data: dict, meta: dict = None) -> dict:
        response = {
            "data": data,
            "_links": {
                "self": {"href": "/weather"},
                "forecast": {"href": "/weather/forecast"},
                "alerts": {"href": "/weather/alerts"}
            },
            "meta": meta or {}
        }
        return response

    def format_graphql(self, data: dict) -> dict:
        return {"data": data}

    def format_error(self, message: str, code: int) -> dict:
        return {
            "error": {
                "code": code,
                "message": message
            }
        }

    def format_websocket(self, action: str, payload: dict) -> str:
        return json.dumps({
            "type": action,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        })


class ChartGenerator:
    def generate_temperature_chart(self, hourly_data: List[dict], theme='light') -> str:
        times = [d['time'] for d in hourly_data]
        temps = [d['temperature'] for d in hourly_data]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=times, y=temps, name="Temp", line=dict(color='royalblue')))
        fig.update_layout(title="Hourly Temperature", template="plotly_dark" if theme == 'dark' else 'plotly')
        return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

    def generate_rainfall_bar(self, daily_data: List[dict]) -> str:
        dates = [d['date'] for d in daily_data]
        rain = [d['precipitation'] for d in daily_data]
        fig = go.Figure([go.Bar(x=dates, y=rain)])
        fig.update_layout(title="Daily Precipitation")
        return pio.to_html(fig, full_html=False)


class VoiceFormatter:
    def generate_tts(self, text: str, lang='en') -> BytesIO:
        tts = gTTS(text=text, lang=lang)
        buffer = BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer

    def generate_ssml(self, text: str) -> str:
        return f"<speak><prosody rate='medium'>{text}</prosody></speak>"


class TextFormatter:
    def __init__(self, locale='en'):
        self.locale = locale

    def format_plain(self, weather: Dict, level='standard') -> str:
        desc = weather.get("description", "")
        temp = weather.get("temperature", "?")
        city = weather.get("location", {}).get("city", "")
        output = ""

        if level == 'brief':
            output = _(f"{city}: {desc}, {temp}°")
        elif level == 'detailed':
            wind = weather.get("wind_speed", "--")
            humidity = weather.get("humidity", "--")
            uv = weather.get("uv_index", "--")
            output = _(
                f"Weather in {city}: {desc}. Temperature is {temp}°C. "
                f"Wind is {wind} km/h, humidity {humidity}%, UV Index: {uv}."
            )
        else:  # standard
            output = _(f"{city}: {desc}, {temp}° and moderately breezy.")
        return output

    def format_with_emoji(self, weather: Dict) -> str:
        temp = weather.get("temperature", 0)
        emoji = '❄️' if temp < 5 else '☀️' if temp > 25 else '🌤'
        return f"{self.format_plain(weather)} {emoji}"


class HTMLFormatter:
    def __init__(self, theme='default'):
        self.renderer = TemplateRenderer(theme)

    def format_dashboard(self, weather: Dict, forecast: List[Dict], chart_html: str) -> str:
        context = {
            "weather": weather,
            "forecast": forecast,
            "chart": Markup(chart_html),
            "generated": datetime.utcnow().isoformat()
        }
        return self.renderer.render("dashboard", context)

    def generate_pdf_report(self, html_content: str) -> bytes:
        html = HTML(string=html_content)
        return html.write_pdf()


class ResponseFormatter:
    def __init__(self, locale='en_US', theme='default'):
        self.loc_helper = LocalizationHelper(locale)
        self.json_formatter = JSONFormatter()
        self.chart_gen = ChartGenerator()
        self.voice_formatter = VoiceFormatter()
        self.text_formatter = TextFormatter(locale)
        self.html_formatter = HTMLFormatter(theme)
        self.locale = locale

    def format_all(self, context: Dict[str, Any]) -> Dict[str, Union[str, dict, bytes]]:
        weather = context.get("weather", {})
        forecast = context.get("forecast", {})

        chart_html = self.chart_gen.generate_temperature_chart(
            forecast.get("hourly", []))

        response = {
            "json": self.json_formatter.format_rest(weather),
            "text": self.text_formatter.format_plain(weather),
            "text_emoji": self.text_formatter.format_with_emoji(weather),
            "html": self.html_formatter.format_dashboard(weather, forecast.get("daily", []), chart_html),
            "tts_audio": self.voice_formatter.generate_tts(self.text_formatter.format_plain(weather)),
            "ssml": self.voice_formatter.generate_ssml(self.text_formatter.format_plain(weather))
        }

        return response


if __name__ == "__main__":
    import example_data  # hypothetical module
    formatter = ResponseFormatter(locale='en_US', theme='dark')
    output_all = formatter.format_all(example_data.get_weather_data())

    print(json.dumps(output_all['json'], indent=2))
    with open("weather_dashboard.html", "w", encoding="utf-8") as f:
        f.write(output_all["html"])
    with open("weather_report.mp3", "wb") as f:
        f.write(output_all["tts_audio"].read())
