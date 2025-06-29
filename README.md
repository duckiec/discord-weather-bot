
# Discord Weather Bot

Weather info in Discord using Open-Meteo.

## Setup

```bash
pip install -r requirements.txt
````

Create a `.env` file:

```
DISCORD_TOKEN=your_token
APPLICATION_ID=your_app_id
GEOCODINGAPIKEY=your_openweathermap_key
```

Run it:

```bash
python main.py
```

## Commands

* `/weather [city] [forecast_days] [rnd]`
  → Get weather for a city
  → `forecast_days`: 1–5 (default 3)
  → `rnd`: round decimals (1–5, default 2)

* `/settings`

  * `set [key] [value]` – change config
  * `get [key]` – show a setting
  * `list` – list all settings

## Features

* Auto status with random city temps
* Caches data for speed
* Shows:

  * current weather
  * temp, humidity
  * wind speed/direction
  * rain/snow
  * 1–5 day forecast


