# General
Some useful scripts simplifying bureaucracy, especially when living in Munich, Germany.

# termin_api.py
Small tool to show availability of appointments in different Departments of Munich.

Available departments are:
- [Ausländerbehörde](https://www.muenchen.de/rathaus/Stadtverwaltung/Kreisverwaltungsreferat/Auslaenderwesen.html) (foreign nationals affairs, residence permits, work visas etc.)
- [Bürgerbüro](https://www.muenchen.de/rathaus/Stadtverwaltung/Kreisverwaltungsreferat/Buergerbuero.html) (civil affairs, residence registration etc.)
- [Führerscheinstelle](https://www.muenchen.de/rathaus/Stadtverwaltung/Kreisverwaltungsreferat/Verkehr/Fuehrerschein.html) (driver license affairs)
- [Kfz-Zulassungstelle](https://www.muenchen.de/rathaus/Stadtverwaltung/Kreisverwaltungsreferat/Verkehr/KFZ-Zulassung.html) (motor vehicles affairs, registration, license plate and so on)
- [Versicherungsamt](https://www.muenchen.de/rathaus/Stadtverwaltung/Kreisverwaltungsreferat/Versicherungsamt.html) (Pension-related stuff, i.e. getting information about your contribution, necessary for NE)


Please note the script **does not perform appointment booking** (see [#4](https://github.com/okainov/munich-scripts/issues/4)), it just tells you current status and allows you to subscribe to a notifier for one week.

## Telegram bot

There is a Telegram bot at [@MunichTerminBot](https://t.me/MunichTerminBot) using `termin_api.py` functionality. The bot is written using [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) library. Source code is also in this repo, `tg_bot.py`.

### Development

By default bot runs as webhook configured for personal web server. For local development it's easier to use polling. In order to get it, just set `DEBUG = True` in one of first lines of the script.

### Bot deployment

Bot is hosted on personal web server, running in Docker and automatic deploy from `master` branch of this repo is set, no action should be required.

#### Manual deployment

Pre-requisites:

 - `TG_TOKEN` environment variable is set in `.env` file

 If you want to enable Elastic statistics, then additionally set following variables to non-empty value:

 - `ELASTIC_HOST` - hostname where ELK stack is deployed
 - `ELASTIC_USER` - ElasticSearch username
 - `ELASTIC_PASS` - ElasticSearch password


Commands for manual deploy

    git pull
    docker-compose build
    docker-compose up -d
    
Shortly after deploy make sure everything is running

    docker-compose logs -f

## Script usage

### Current appointment search API

The Munich appointment search uses the current public appointment API. Search for a service by its full or partial
name from the project directory:

    python3 appointment_api.py "Entwässerungsplanvorbesprechung - Vor Ort"

The default search window is 180 days. It can be changed with `--start YYYY-MM-DD` and `--end YYYY-MM-DD`.
If a search phrase matches multiple services, the command prints their exact names; run it again with the
service name you want. Results are availability only; booking remains on Munich's official site.

To check passport appointments at Belgradstraße, complete the CAPTCHA through Munich's official appointment
interface and pass its token. The client does not solve or bypass the CAPTCHA:

    python3 appointment_api.py "Reisepass" --office "Belgradstraße" --captcha-token "<token>"

The client uses Python's standard HTTP library. Install `tzdata` on Windows so appointment times are converted
using Munich's daylight-saving rules; Linux systems generally provide this time-zone database already.

The legacy bot interface in `termin_api.py` now adapts the new catalog and availability API to the result format
used by the existing notification code.
