import numpy as np
import pandas as pd
import pytz
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import linregress, zscore
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.arima.model import ARIMA
from geopy.distance import geodesic
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import json
import csv
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
import io
import os
import threading
import warnings

warnings.filterwarnings("ignore")

# --------------------------- Constants & Utilities -------------------------- #

METRIC_UNITS = {
    'temperature': 'C',
    'wind_speed': 'm/s',
    'pressure': 'hPa',
    'precipitation': 'mm',
    'visibility': 'km'
}

IMPERIAL_UNITS = {
    'temperature': 'F',
    'wind_speed': 'mph',
    'pressure': 'inHg',
    'precipitation': 'inch',
    'visibility': 'miles'
}

def c_to_f(celsius):
    return (celsius * 9 / 5) + 32

def f_to_c(fahrenheit):
    return (fahrenheit - 32) * 5 / 9

def mps_to_mph(mps):
    return mps * 2.237

def mph_to_mps(mph):
    return mph / 2.237

def hpa_to_inhg(hpa):
    return hpa * 0.02953

def inhg_to_hpa(inhg):
    return inhg / 0.02953

def km_to_miles(km):
    return km * 0.621371

def miles_to_km(miles):
    return miles / 0.621371

def convert_units(df, to_metric=True):
    if to_metric:
        df['temperature'] = df['temperature'].apply(lambda x: f_to_c(x))
        df['wind_speed'] = df['wind_speed'].apply(lambda x: mph_to_mps(x))
        df['pressure'] = df['pressure'].apply(lambda x: inhg_to_hpa(x))
        df['visibility'] = df['visibility'].apply(lambda x: miles_to_km(x))
    else:
        df['temperature'] = df['temperature'].apply(lambda x: c_to_f(x))
        df['wind_speed'] = df['wind_speed'].apply(lambda x: mps_to_mph(x))
        df['pressure'] = df['pressure'].apply(lambda x: hpa_to_inhg(x))
        df['visibility'] = df['visibility'].apply(lambda x: km_to_miles(x))
    return df

# --------------------------- Core Meteorological Calculations --------------------------- #

def calculate_dew_point(temp_c, humidity):
    b = 17.62
    c = 243.12
    gamma = np.log(humidity / 100) + (b * temp_c) / (c + temp_c)
    return (c * gamma) / (b - gamma)

def calculate_heat_index(temp_f, humidity):
    hi = -42.379 + 2.04901523*temp_f + 10.14333127*humidity - 0.22475541*temp_f*humidity \
         - 0.00683783*temp_f**2 - 0.05481717*humidity**2 \
         + 0.00122874*temp_f**2*humidity + 0.00085282*temp_f*humidity**2 \
         - 0.00000199*temp_f**2*humidity**2
    return hi

def calculate_wind_chill(temp_f, wind_speed_mph):
    if temp_f <= 50 and wind_speed_mph > 3:
        wc = 35.74 + 0.6215*temp_f - 35.75*(wind_speed_mph**0.16) + \
             0.4275*temp_f*(wind_speed_mph**0.16)
        return wc
    return temp_f

# --------------------------- Quality Control & Validation --------------------------- #

class QualityControl:
    def __init__(self, df):
        self.df = df.copy()

    def detect_sensor_drift(self):
        drift_flags = []
        for col in ['temperature', 'humidity', 'pressure']:
            series = self.df[col]
            slope, _, _, _, _ = linregress(range(len(series)), series)
            drift_flags.append(abs(slope) > 0.01)
        return any(drift_flags)

    def detect_missing_data(self):
        return self.df.isnull().sum().to_dict()

    def impute_missing(self):
        self.df.interpolate(method='linear', inplace=True)

    def detect_outliers(self):
        z_scores = np.abs(zscore(self.df.select_dtypes(include=[np.number])))
        return np.where(z_scores > 3, True, False)

    def cross_validate_stations(self, df2):
        common = ['temperature', 'humidity']
        for col in common:
            if abs(self.df[col].mean() - df2[col].mean()) > 2:
                print(f'Cross validation warning for {col}')
                
# --------------------------- Advanced Analytics --------------------------- #

class WeatherAnalytics:
    def __init__(self, df):
        self.df = df.copy()

    def seasonal_trend(self, column):
        self.df['month'] = pd.to_datetime(self.df['timestamp']).dt.month
        return self.df.groupby('month')[column].mean()

    def detect_anomalies(self):
        model = IsolationForest(contamination=0.05)
        numeric_df = self.df.select_dtypes(include=[np.number])
        anomalies = model.fit_predict(numeric_df)
        self.df["anomaly"] = anomalies
        return self.df[self.df["anomaly"] == -1]

    def historical_comparison(self, hist_df):
        comparison = {}
        for col in ['temperature', 'humidity', 'wind_speed']:
            current_avg = self.df[col].mean()
            hist_avg = hist_df[col].mean()
            comparison[col] = {"current": current_avg, "historical": hist_avg}
        return comparison

    def forecast(self, column, periods=5):
        ts = pd.Series(self.df[column].values, index=pd.to_datetime(self.df['timestamp']))
        model = ARIMA(ts, order=(1,1,1))
        model_fit = model.fit()
        forecast = model_fit.forecast(steps=periods)
        return forecast

# --------------------------- Alert Engine --------------------------- #

class AlertEngine:
    def __init__(self, df):
        self.df = df

    def threshold_alerts(self, threshold_dict):
        alerts = []
        for i, row in self.df.iterrows():
            for key, val in threshold_dict.items():
                if row[key] > val:
                    alerts.append((row['timestamp'], key, row[key], 'THRESHOLD_BREACH'))
        return alerts

    def rate_of_change_alert(self, column, threshold):
        diffs = self.df[column].diff()
        alerts = []
        for i, diff in enumerate(diffs):
            if abs(diff) > threshold:
                alerts.append((self.df.loc[i, 'timestamp'], column, self.df.loc[i, column],
                               'RAPID_CHANGE'))
        return alerts

# --------------------------- Data Exporters --------------------------- #

class Exporter:
    @staticmethod
    def to_json(df, path):
        schema = {"type": "object", "properties": {col: {"type": "number"} for col in df.columns}}
        with open(path, 'w') as f:
            json.dump(df.to_dict(orient='records'), f, indent=4)

    @staticmethod
    def to_csv(df, path):
        df.to_csv(path, index=False)

    @staticmethod
    def to_pdf(df, path):
        c = canvas.Canvas(path, pagesize=letter)
        text = c.beginText(40, 750)
        text.setFont("Helvetica", 10)

        for col in df.columns[:6]:
            text.textLine(f"{col} Head: {df[col].head().tolist()}")

        c.drawText(text)
        c.showPage()
        c.save()

    @staticmethod
    def plot_timeseries(df, column, path='plot.png'):
        fig, ax = plt.subplots()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.plot(pd.to_datetime(df['timestamp']), df[column])
        plt.title(f'{column} over time')
        plt.savefig(path)

# --------------------------- Specialized Processors --------------------------- #

class WeatherProcessor(ABC):
    def __init__(self, df):
        self.df = df

    @abstractmethod
    def process(self):
        pass

class MarineWeatherProcessor(WeatherProcessor):
    def process(self):
        self.df['wave_estimate'] = np.random.rand(len(self.df)) * 3
        return self.df

class AviationWeatherProcessor(WeatherProcessor):
    def process(self):
        self.df['flight_ceiling_ok'] = self.df['cloud_base'] > 500
        return self.df

# Additional types (AgriculturalWeatherProcessor, etc.) follow same pattern

# --------------------------- Main Data Processor Class --------------------------- #

class DataProcessor:
    def __init__(self, raw_df):
        self.df = raw_df.copy()

    def run_all(self):
        print("Running quality checks...")
        qc = QualityControl(self.df)
        missing = qc.detect_missing_data()
        qc.impute_missing()
        outliers = qc.detect_outliers()

        print("Running analytics...")
        analytics = WeatherAnalytics(self.df)
        anomalies = analytics.detect_anomalies()
        forecast_temp = analytics.forecast('temperature')

        print("Running alerts...")
        alert_engine = AlertEngine(self.df)
        thresh_alerts = alert_engine.threshold_alerts({'temperature': 35, 'wind_speed': 15})

        print("Exporting data...")
        Exporter.to_json(self.df, 'output/weather.json')
        Exporter.to_csv(self.df, 'output/weather.csv')
        Exporter.to_pdf(self.df, 'output/weather.pdf')
        Exporter.plot_timeseries(self.df, 'temperature')

        return {
            "anomalies": anomalies,
            "forecast": forecast_temp,
            "alerts": thresh_alerts
        }

# --------------------------- Example Usage Simulation --------------------------- #

if __name__ == "__main__":
    timestamps = pd.date_range(start="2024-01-01", periods=100, freq='H')
    data = {
        'timestamp': timestamps,
        'temperature': np.random.normal(15, 5, 100),
        'humidity': np.random.normal(70, 10, 100),
        'wind_speed': np.random.normal(5, 2, 100),
        'pressure': np.random.normal(1013, 5, 100),
        'visibility': np.random.normal(10, 1, 100),
        'cloud_base': np.random.normal(1500, 500, 100)
    }
    df = pd.DataFrame(data)

    os.makedirs("output", exist_ok=True)

    processor = DataProcessor(df)
    results = processor.run_all()

    print("\n--- Summary ---")
    print(f"Detected Alerts: {len(results['alerts'])}")
    print(f"Anomalies Found: {len(results['anomalies'])}")
    print("Forecast (next values):\n", results['forecast'])
