from airflow import DAG
from airflow.providers.http.hooks.http import HttpHook
from airflow.decorators import task
from airflow.utils.dates import days_ago
from airflow.providers.postgres.hooks.postgres import PostgresHook
import json
import requests

LATITUDE = "17.4065"  # Hyderabad latitude
LONGITUDE = "78.4772"  # Hyderabad longitude
POSTGRES_CONN_ID = "postgres_default"
API_CONN_ID = "open_meteo_api"

default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
    'retries': 1
}

with DAG(
    dag_id="weather_Pipeline",
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False
) as dag:

    @task()
    def extract_weather_data():
        """Extract weather data from Open-Meteo API using an Airflow connection."""

        # Use HttpHook to retrieve connection details
        http_hook = HttpHook(http_conn_id=API_CONN_ID, method='GET')

        # Build the API endpoint
        endpoint = f'/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true'

        # Make the request via the HttpHook
        response = http_hook.run(endpoint)

        # Check the response and return JSON if successful
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to fetch weather data: {response.status_code}")

    @task()
    def transform_weather_data(weather_data):
        """Transform the extracted weather data for loading."""

        current_weather = weather_data.get('current_weather', {})

        transformed_data = {
            'latitude': LATITUDE,
            'longitude': LONGITUDE,
            'temperature': current_weather.get('temperature'),
            'windspeed': current_weather.get('windspeed'),
            'winddirection': current_weather.get('winddirection'),
            'weathercode': current_weather.get('weathercode')
        }

        return transformed_data

    @task()
    def load_weather_data(transformed_data):
        """Load transformed data into PostgreSQL."""
        pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = pg_hook.get_conn()
        cursor = conn.cursor()

        # Create table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_data (
            latitude FLOAT,
            longitude FLOAT,
            temperature FLOAT,
            windspeed FLOAT,
            winddirection FLOAT,
            weathercode INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Insert transformed data into the table
        cursor.execute("""
        INSERT INTO weather_data (latitude, longitude, temperature, windspeed, winddirection, weathercode)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            transformed_data['latitude'],
            transformed_data['longitude'],
            transformed_data['temperature'],
            transformed_data['windspeed'],
            transformed_data['winddirection'],
            transformed_data['weathercode']
        ))

        conn.commit()
        cursor.close()

    # Define the ETL workflow
    weather_data = extract_weather_data()
    transformed_data = transform_weather_data(weather_data)
    load_weather_data(transformed_data)
