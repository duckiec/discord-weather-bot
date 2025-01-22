# Discord Weather Bot

A Discord bot that provides weather information and forecasts using the Open-Meteo API.

## Setup

1. Clone the repository

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with the following variables:
```
DISCORD_TOKEN=your_discord_bot_token
APPLICATION_ID=your_application_id
GEOCODINGAPIKEY=your_openweathermap_api_key
```

4. Create a `commands` directory if it doesn't exist:
```bash
mkdir commands
```

## Running the Bot

1. Make sure all files are in place
2. Run the bot:
```bash
python main.py
```

## Features

- `/weather [city] [forecast_days] [rnd]` - Get weather information for a city
  - `city`: Name of the city
  - `forecast_days`: Number of forecast days (1-5, default: 3)
  - `rnd`: Decimal places for rounding (1-5, default: 2)

- Automatic status updates showing temperatures from random cities
- Cached weather data for better performance
- Detailed weather information including:
  - Current conditions
  - Temperature
  - Humidity
  - Wind speed and direction
  - Precipitation
  - Daily forecasts

