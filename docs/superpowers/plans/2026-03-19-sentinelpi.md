# SentinelPi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Raspberry Pi 5 security system with sensor monitoring, puzzle-based disarm, and a real-time web dashboard.

**Architecture:** Single Python process with two threads — main thread runs a state machine polling GPIO sensors via gpiozero, secondary thread runs a Flask+SocketIO web dashboard. Communication via thread-safe `queue.Queue`. SQLite for event logging.

**Tech Stack:** Python 3.13, gpiozero, Flask, Flask-SocketIO, SQLite

**Spec:** `docs/superpowers/specs/2026-03-19-sentinelpi-design.md`

---

## File Structure

```
/home/kekkoz/sentinelpi/
├── sentinelpi/
│   ├── __init__.py          # Package marker, version string
│   ├── config.py            # Load/save/validate config.json
│   ├── database.py          # SQLite init, event logging, queries
│   ├── actuators.py         # LED and buzzer control via gpiozero
│   ├── sensors.py           # Sensor wrappers via gpiozero
│   ├── challenge.py         # Puzzle logic (simon, rhythm, counting)
│   ├── core.py              # State machine, main loop, command queue
│   ├── simulator.py         # Simulation mode: random sensor triggers + keyboard input
│   └── web/
│       ├── __init__.py      # Package marker
│       ├── app.py           # Flask + SocketIO setup, routes, events
│       ├── templates/
│       │   └── index.html   # Dashboard SPA
│       └── static/
│           ├── style.css    # Dashboard styles
│           └── app.js       # SocketIO client, UI logic
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared fixtures, mock pin factory setup
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_actuators.py
│   ├── test_sensors.py
│   ├── test_challenge.py
│   ├── test_core.py
│   └── test_web.py
├── config.json              # Default configuration
├── run.py                   # Entry point with --simulate flag
└── requirements.txt         # Python dependencies
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `/home/kekkoz/sentinelpi/requirements.txt`
- Create: `/home/kekkoz/sentinelpi/config.json`
- Create: `/home/kekkoz/sentinelpi/sentinelpi/__init__.py`
- Create: `/home/kekkoz/sentinelpi/sentinelpi/web/__init__.py`
- Create: `/home/kekkoz/sentinelpi/tests/__init__.py`
- Create: `/home/kekkoz/sentinelpi/run.py`

- [ ] **Step 1: Create project directory and virtual environment**

```bash
mkdir -p /home/kekkoz/sentinelpi
cd /home/kekkoz/sentinelpi
python3 -m venv venv
```

- [ ] **Step 2: Create requirements.txt**

```
gpiozero==2.0.1
lgpio==0.6
flask==3.1.1
flask-socketio==5.5.1
pytest==8.3.5
```

Note: `lgpio` is the GPIO backend for gpiozero on Pi 5 (replaces RPi.GPIO which doesn't support Pi 5). On non-Pi machines in simulation mode, gpiozero uses a mock pin factory automatically.

- [ ] **Step 3: Install dependencies**

```bash
cd /home/kekkoz/sentinelpi
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Create config.json**

```json
{
  "pins": {
    "pir": 17,
    "light": 27,
    "sound": 22,
    "led_red": 5,
    "led_green": 6,
    "led_blue": 13,
    "buzzer": 19,
    "button_a": 16,
    "button_b": 26
  },
  "timing": {
    "alert_grace_seconds": 3,
    "challenge_timeout_seconds": 15,
    "alarm_auto_reset_seconds": 0,
    "disarmed_display_seconds": 3
  },
  "difficulty": {
    "difficulty_level": 1,
    "max_sequence_length": 8,
    "button_rhythm_tolerance_ms": 200
  },
  "sensors": {
    "pir_enabled": true,
    "light_enabled": true,
    "sound_enabled": true
  },
  "web": {
    "host": "0.0.0.0",
    "port": 5000
  }
}
```

- [ ] **Step 5: Create package init files**

`sentinelpi/__init__.py`:
```python
__version__ = "0.1.0"
```

`sentinelpi/web/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import os
os.environ["GPIOZERO_PIN_FACTORY"] = "mock"
```

This ensures the mock pin factory is set for ALL tests, so individual test files don't need to repeat it.

- [ ] **Step 6: Create run.py entry point (minimal)**

```python
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="SentinelPi security system")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode without real GPIO hardware",
    )
    args = parser.parse_args()

    if args.simulate:
        import os
        os.environ["GPIOZERO_PIN_FACTORY"] = "mock"

    print(f"SentinelPi v0.1.0 — {'SIMULATION' if args.simulate else 'HARDWARE'} mode")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Verify scaffold works**

```bash
cd /home/kekkoz/sentinelpi
source venv/bin/activate
python run.py --simulate
```

Expected output: `SentinelPi v0.1.0 — SIMULATION mode`

- [ ] **Step 8: Init git repo and commit**

```bash
cd /home/kekkoz/sentinelpi
git init
echo "venv/" > .gitignore
echo "*.pyc" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.db" >> .gitignore
git add .
git commit -m "chore: initial project scaffold"
```

---

## Task 2: Config Module

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/config.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

`tests/test_config.py`:
```python
import json
import os
import tempfile

import pytest

from sentinelpi.config import load_config, DEFAULT_CONFIG


def test_load_config_returns_default_when_file_missing():
    config = load_config("/nonexistent/path/config.json")
    assert config == DEFAULT_CONFIG


def test_load_config_reads_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        custom = {**DEFAULT_CONFIG, "web": {"host": "127.0.0.1", "port": 9999}}
        json.dump(custom, f)
        path = f.name
    try:
        config = load_config(path)
        assert config["web"]["port"] == 9999
    finally:
        os.unlink(path)


def test_load_config_merges_missing_keys():
    """If config file is missing some keys, defaults fill in."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"web": {"host": "127.0.0.1", "port": 9999}}, f)
        path = f.name
    try:
        config = load_config(path)
        assert config["web"]["port"] == 9999
        assert "pins" in config  # filled from defaults
        assert config["pins"]["pir"] == 17
    finally:
        os.unlink(path)


def test_default_config_has_all_required_sections():
    for section in ("pins", "timing", "difficulty", "sensors", "web"):
        assert section in DEFAULT_CONFIG


def test_difficulty_to_sequence_length():
    from sentinelpi.config import difficulty_to_sequence_length
    assert difficulty_to_sequence_length(1) == 3
    assert difficulty_to_sequence_length(5) == 7


def test_difficulty_to_sequence_length_clamped():
    from sentinelpi.config import difficulty_to_sequence_length
    assert difficulty_to_sequence_length(0) == 3  # min clamp
    assert difficulty_to_sequence_length(10) == 7  # max clamp
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'sentinelpi.config'`

- [ ] **Step 3: Implement config module**

`sentinelpi/config.py`:
```python
import json
import copy

DEFAULT_CONFIG = {
    "pins": {
        "pir": 17,
        "light": 27,
        "sound": 22,
        "led_red": 5,
        "led_green": 6,
        "led_blue": 13,
        "buzzer": 19,
        "button_a": 16,
        "button_b": 26,
    },
    "timing": {
        "alert_grace_seconds": 3,
        "challenge_timeout_seconds": 15,
        "alarm_auto_reset_seconds": 0,
        "disarmed_display_seconds": 3,
    },
    "difficulty": {
        "difficulty_level": 1,
        "max_sequence_length": 8,
        "button_rhythm_tolerance_ms": 200,
    },
    "sensors": {
        "pir_enabled": True,
        "light_enabled": True,
        "sound_enabled": True,
    },
    "web": {
        "host": "0.0.0.0",
        "port": 5000,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, filling missing keys from base."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str) -> dict:
    """Load config from JSON file, falling back to defaults for missing keys."""
    try:
        with open(path) as f:
            user_config = json.load(f)
        return _deep_merge(DEFAULT_CONFIG, user_config)
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(path: str, config: dict) -> None:
    """Save config dict to JSON file."""
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def difficulty_to_sequence_length(level: int) -> int:
    """Convert difficulty level (1-5) to base sequence length (3-7)."""
    clamped = max(1, min(5, level))
    return clamped + 2
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_config.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/config.py tests/test_config.py
git commit -m "feat: add config module with loading, merging, and difficulty mapping"
```

---

## Task 3: Database Module

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/database.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_database.py`

- [ ] **Step 1: Write failing tests**

`tests/test_database.py`:
```python
import os
import tempfile

import pytest

from sentinelpi.database import EventDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = EventDB(path)
    yield database
    database.close()
    os.unlink(path)


def test_log_event_and_retrieve(db):
    db.log_event("state_change", state_from="IDLE", state_to="ARMED")
    events = db.get_recent_events(limit=10)
    assert len(events) == 1
    assert events[0]["event_type"] == "state_change"
    assert events[0]["state_from"] == "IDLE"
    assert events[0]["state_to"] == "ARMED"


def test_log_sensor_trigger(db):
    db.log_event("sensor_trigger", state_from="ARMED", state_to="ALERT", sensor="pir")
    events = db.get_recent_events(limit=10)
    assert events[0]["sensor"] == "pir"


def test_log_event_with_details(db):
    db.log_event("challenge_result", details='{"puzzle": "simon", "result": "success"}')
    events = db.get_recent_events(limit=10)
    assert "simon" in events[0]["details"]


def test_get_recent_events_respects_limit(db):
    for i in range(20):
        db.log_event("state_change", state_from="IDLE", state_to="ARMED")
    events = db.get_recent_events(limit=5)
    assert len(events) == 5


def test_get_recent_events_newest_first(db):
    db.log_event("state_change", state_from="IDLE", state_to="ARMED")
    db.log_event("state_change", state_from="ARMED", state_to="ALERT")
    events = db.get_recent_events(limit=10)
    assert events[0]["state_to"] == "ALERT"  # newest first


def test_daily_alarm_count(db):
    db.log_event("state_change", state_from="CHALLENGE", state_to="ALARM")
    db.log_event("state_change", state_from="CHALLENGE", state_to="ALARM")
    db.log_event("state_change", state_from="IDLE", state_to="ARMED")  # not an alarm
    count = db.get_daily_alarm_count()
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_database.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'sentinelpi.database'`

- [ ] **Step 3: Implement database module**

`sentinelpi/database.py`:
```python
import sqlite3
import os


class EventDB:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                event_type TEXT NOT NULL,
                state_from TEXT,
                state_to TEXT,
                sensor TEXT,
                details TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        """)
        self.conn.commit()

    def log_event(self, event_type: str, state_from: str = None,
                  state_to: str = None, sensor: str = None, details: str = None):
        self.conn.execute(
            "INSERT INTO events (event_type, state_from, state_to, sensor, details) VALUES (?, ?, ?, ?, ?)",
            (event_type, state_from, state_to, sensor, details),
        )
        self.conn.commit()

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_daily_alarm_count(self) -> int:
        cursor = self.conn.execute("""
            SELECT COUNT(*) FROM events
            WHERE event_type = 'state_change' AND state_to = 'ALARM'
            AND date(timestamp) = date('now', 'localtime')
        """)
        return cursor.fetchone()[0]

    def close(self):
        self.conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_database.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/database.py tests/test_database.py
git commit -m "feat: add SQLite database module for event logging"
```

---

## Task 4: Actuators Module (LEDs + Buzzer)

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/actuators.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_actuators.py`

- [ ] **Step 1: Write failing tests**

Note: Tests use gpiozero's `MockFactory` so they run without real hardware.

`tests/test_actuators.py`:
```python
import pytest

from sentinelpi.actuators import Actuators


@pytest.fixture
def actuators():
    pins = {"led_red": 5, "led_green": 6, "led_blue": 13, "buzzer": 19}
    act = Actuators(pins)
    yield act
    act.cleanup()


def test_all_off(actuators):
    actuators.all_off()
    assert actuators.led_red.value == 0
    assert actuators.led_green.value == 0
    assert actuators.led_blue.value == 0
    assert actuators.buzzer.value == 0


def test_set_led(actuators):
    actuators.set_led("red", True)
    assert actuators.led_red.value == 1
    actuators.set_led("red", False)
    assert actuators.led_red.value == 0


def test_set_led_invalid_color(actuators):
    with pytest.raises(ValueError):
        actuators.set_led("purple", True)


def test_buzzer_on_off(actuators):
    actuators.buzzer_on()
    assert actuators.buzzer.value == 1
    actuators.buzzer_off()
    assert actuators.buzzer.value == 0


def test_set_state_idle(actuators):
    actuators.set_state("IDLE")
    # In IDLE, green breathes — we just check no crash and others are off
    assert actuators.led_red.value == 0
    assert actuators.led_blue.value == 0


def test_set_state_armed(actuators):
    actuators.set_state("ARMED")
    assert actuators.led_green.value == 1
    assert actuators.led_red.value == 0
    assert actuators.led_blue.value == 0


def test_set_state_alarm(actuators):
    actuators.set_state("ALARM")
    assert actuators.led_red.value == 1
    assert actuators.buzzer.value == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_actuators.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'sentinelpi.actuators'`

- [ ] **Step 3: Implement actuators module**

`sentinelpi/actuators.py`:
```python
from gpiozero import LED, Buzzer


class Actuators:
    def __init__(self, pins: dict):
        self.led_red = LED(pins["led_red"])
        self.led_green = LED(pins["led_green"])
        self.led_blue = LED(pins["led_blue"])
        self.buzzer = Buzzer(pins["buzzer"])
        self._leds = {
            "red": self.led_red,
            "green": self.led_green,
            "blue": self.led_blue,
        }

    def all_off(self):
        for led in self._leds.values():
            led.off()
        self.buzzer.off()

    def set_led(self, color: str, on: bool):
        if color not in self._leds:
            raise ValueError(f"Unknown LED color: {color}. Use: {list(self._leds.keys())}")
        if on:
            self._leds[color].on()
        else:
            self._leds[color].off()

    def buzzer_on(self):
        self.buzzer.on()

    def buzzer_off(self):
        self.buzzer.off()

    def set_state(self, state: str):
        """Set actuators to match the given system state."""
        self.all_off()
        if state == "IDLE":
            self.led_green.blink(on_time=1, off_time=1)
        elif state == "ARMED":
            self.led_green.on()
        elif state == "ALERT":
            self.led_blue.blink(on_time=0.3, off_time=0.3)
        elif state == "CHALLENGE":
            self.led_blue.on()
            self.buzzer.beep(on_time=0.1, off_time=0.9)  # soft countdown warning
        elif state == "DISARMED":
            self.led_green.blink(on_time=0.2, off_time=0.2)
            self.buzzer.beep(on_time=0.05, off_time=0.05, n=3)  # success tone
        elif state == "ALARM":
            self.led_red.on()
            self.buzzer.on()

    def cleanup(self):
        self.all_off()
        self.led_red.close()
        self.led_green.close()
        self.led_blue.close()
        self.buzzer.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_actuators.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/actuators.py tests/test_actuators.py
git commit -m "feat: add actuators module for LEDs and buzzer control"
```

---

## Task 5: Sensors Module

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/sensors.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_sensors.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sensors.py`:
```python
import pytest
from sentinelpi.sensors import SensorManager


@pytest.fixture
def sensor_mgr():
    pins = {"pir": 17, "light": 27, "sound": 22, "button_a": 16, "button_b": 26}
    sensor_config = {"pir_enabled": True, "light_enabled": True, "sound_enabled": True}
    mgr = SensorManager(pins, sensor_config)
    yield mgr
    mgr.cleanup()


def test_sensor_manager_creates_sensors(sensor_mgr):
    assert sensor_mgr.pir is not None
    assert sensor_mgr.light is not None
    assert sensor_mgr.sound is not None


def test_sensor_manager_creates_buttons(sensor_mgr):
    assert sensor_mgr.button_a is not None
    assert sensor_mgr.button_b is not None


def test_disabled_sensor_is_none():
    pins = {"pir": 17, "light": 27, "sound": 22, "button_a": 16, "button_b": 26}
    sensor_config = {"pir_enabled": False, "light_enabled": True, "sound_enabled": False}
    mgr = SensorManager(pins, sensor_config)
    assert mgr.pir is None
    assert mgr.light is not None
    assert mgr.sound is None
    mgr.cleanup()


def test_check_sensors_returns_none_when_no_trigger(sensor_mgr):
    triggered = sensor_mgr.check_sensors()
    assert triggered is None


def test_check_sensors_detects_pir(sensor_mgr):
    # Simulate PIR going HIGH
    sensor_mgr.pir.pin.drive_high()
    triggered = sensor_mgr.check_sensors()
    assert triggered == "pir"


def test_check_sensors_skips_disabled():
    pins = {"pir": 17, "light": 27, "sound": 22, "button_a": 16, "button_b": 26}
    sensor_config = {"pir_enabled": False, "light_enabled": True, "sound_enabled": True}
    mgr = SensorManager(pins, sensor_config)
    # Even if pin 17 were high, pir is disabled so no trigger
    triggered = mgr.check_sensors()
    assert triggered is None
    mgr.cleanup()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_sensors.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement sensors module**

`sentinelpi/sensors.py`:
```python
from gpiozero import DigitalInputDevice, Button


class SensorManager:
    def __init__(self, pins: dict, sensor_config: dict):
        self.pir = (
            DigitalInputDevice(pins["pir"], pull_up=False)
            if sensor_config.get("pir_enabled", True)
            else None
        )
        self.light = (
            DigitalInputDevice(pins["light"], pull_up=True)
            if sensor_config.get("light_enabled", True)
            else None
        )
        self.sound = (
            DigitalInputDevice(pins["sound"], pull_up=True)
            if sensor_config.get("sound_enabled", True)
            else None
        )
        self.button_a = Button(pins["button_a"], pull_up=True, bounce_time=0.05)
        self.button_b = Button(pins["button_b"], pull_up=True, bounce_time=0.05)

        self._sensors = []
        if self.pir:
            self._sensors.append(("pir", self.pir))
        if self.light:
            self._sensors.append(("light", self.light))
        if self.sound:
            self._sensors.append(("sound", self.sound))

    def check_sensors(self) -> str | None:
        """Check all enabled sensors. Returns name of first triggered sensor, or None."""
        for name, sensor in self._sensors:
            if sensor.value:
                return name
        return None

    def cleanup(self):
        for _, sensor in self._sensors:
            sensor.close()
        self.button_a.close()
        self.button_b.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_sensors.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/sensors.py tests/test_sensors.py
git commit -m "feat: add sensor manager with PIR, light, sound, and buttons"
```

---

## Task 6: Challenge Module (Puzzles)

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/challenge.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_challenge.py`

- [ ] **Step 1: Write failing tests**

`tests/test_challenge.py`:
```python
import pytest
from unittest.mock import MagicMock

from sentinelpi.challenge import (
    SimonSaysChallenge,
    CountingChallenge,
    ButtonRhythmChallenge,
    pick_challenge,
)


class TestSimonSays:
    def test_generate_sequence_length(self):
        ch = SimonSaysChallenge(sequence_length=4)
        assert len(ch.sequence) == 4

    def test_sequence_uses_valid_colors(self):
        ch = SimonSaysChallenge(sequence_length=5)
        for color in ch.sequence:
            assert color in ("red", "green", "blue")

    def test_correct_input_advances(self):
        ch = SimonSaysChallenge(sequence_length=3)
        ch.sequence = ["red", "green", "blue"]
        ch.current_color = "red"
        result = ch.submit_selection()  # confirm current color
        assert result == "next"  # advance to next in sequence

    def test_wrong_input_resets(self):
        ch = SimonSaysChallenge(sequence_length=3)
        ch.sequence = ["red", "green", "blue"]
        ch.current_color = "green"  # wrong — should be red
        result = ch.submit_selection()
        assert result == "wrong"

    def test_correct_full_sequence_wins(self):
        ch = SimonSaysChallenge(sequence_length=2)
        ch.sequence = ["red", "green"]
        ch.current_color = "red"
        ch.submit_selection()
        ch.current_color = "green"
        result = ch.submit_selection()
        assert result == "solved"


class TestCounting:
    def test_generate_target(self):
        ch = CountingChallenge(sequence_length=5)
        assert 3 <= ch.target <= 5

    def test_correct_count_wins(self):
        ch = CountingChallenge(sequence_length=5)
        ch.target = 4
        ch.press_count = 4
        result = ch.submit_count()
        assert result == "solved"

    def test_wrong_count_fails(self):
        ch = CountingChallenge(sequence_length=5)
        ch.target = 4
        ch.press_count = 3
        result = ch.submit_count()
        assert result == "wrong"

    def test_increment_press(self):
        ch = CountingChallenge(sequence_length=5)
        ch.press_a()
        ch.press_a()
        assert ch.press_count == 2


class TestPickChallenge:
    def test_pick_returns_valid_challenge(self):
        ch = pick_challenge(sequence_length=3)
        assert ch is not None
        assert hasattr(ch, "name")

    def test_pick_respects_sequence_length(self):
        for _ in range(20):
            ch = pick_challenge(sequence_length=5)
            if isinstance(ch, SimonSaysChallenge):
                assert len(ch.sequence) == 5
            elif isinstance(ch, CountingChallenge):
                assert 3 <= ch.target <= 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_challenge.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement challenge module**

`sentinelpi/challenge.py`:
```python
import random
import time


class SimonSaysChallenge:
    """LED sequence memory puzzle. User cycles colors with Button A, confirms with Button B."""
    name = "simon"

    def __init__(self, sequence_length: int):
        colors = ("red", "green", "blue")
        self.sequence = [random.choice(colors) for _ in range(sequence_length)]
        self.position = 0
        self.current_color = "red"  # starting color for cycling

    def cycle_color(self):
        """Button A pressed — cycle to next color."""
        colors = ("red", "green", "blue")
        idx = colors.index(self.current_color)
        self.current_color = colors[(idx + 1) % 3]
        return self.current_color

    def submit_selection(self) -> str:
        """Button B pressed — confirm current color selection.
        Returns: 'next' (correct, more to go), 'solved' (all correct), 'wrong' (restart)."""
        if self.current_color == self.sequence[self.position]:
            self.position += 1
            if self.position >= len(self.sequence):
                return "solved"
            return "next"
        else:
            self.position = 0
            return "wrong"


class CountingChallenge:
    """Count the beeps puzzle. Press Button A to count, Button B to confirm."""
    name = "counting"

    def __init__(self, sequence_length: int):
        self.target = random.randint(3, max(3, sequence_length))
        self.press_count = 0

    def press_a(self):
        """Button A pressed — increment count."""
        self.press_count += 1

    def submit_count(self) -> str:
        """Button B pressed — check if count matches target.
        Returns: 'solved' or 'wrong'."""
        if self.press_count == self.target:
            return "solved"
        self.press_count = 0
        return "wrong"


class ButtonRhythmChallenge:
    """Rhythm replication puzzle. Listen to pattern, replicate timing with Button A."""
    name = "rhythm"

    def __init__(self, sequence_length: int, tolerance_ms: int = 200):
        self.tolerance_ms = tolerance_ms
        # Generate rhythm: list of intervals in ms between beats
        self.pattern = [random.choice([300, 500, 800]) for _ in range(sequence_length - 1)]
        self.recording: list[float] = []
        self._last_press_time: float | None = None

    def press_a(self):
        """Button A pressed — record timestamp."""
        now = time.monotonic()
        if self._last_press_time is not None:
            interval_ms = (now - self._last_press_time) * 1000
            self.recording.append(interval_ms)
        self._last_press_time = now

    def check_rhythm(self) -> str:
        """Check if recorded rhythm matches pattern.
        Returns: 'solved' or 'wrong'."""
        if len(self.recording) != len(self.pattern):
            self.recording = []
            self._last_press_time = None
            return "wrong"
        for recorded, expected in zip(self.recording, self.pattern):
            if abs(recorded - expected) > self.tolerance_ms:
                self.recording = []
                self._last_press_time = None
                return "wrong"
        return "solved"


def pick_challenge(sequence_length: int, tolerance_ms: int = 200):
    """Randomly pick one of the available challenges."""
    choice = random.choice(["simon", "counting", "rhythm"])
    if choice == "simon":
        return SimonSaysChallenge(sequence_length)
    elif choice == "counting":
        return CountingChallenge(sequence_length)
    else:
        return ButtonRhythmChallenge(sequence_length, tolerance_ms)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_challenge.py -v
```

Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/challenge.py tests/test_challenge.py
git commit -m "feat: add challenge module with simon, counting, and rhythm puzzles"
```

---

## Task 7: Core State Machine

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/core.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_core.py`

- [ ] **Step 1: Write failing tests**

`tests/test_core.py`:
```python
import queue
import pytest

from sentinelpi.core import SentinelCore
from sentinelpi.config import DEFAULT_CONFIG


@pytest.fixture
def core():
    cmd_queue = queue.Queue()
    c = SentinelCore(DEFAULT_CONFIG, cmd_queue)
    yield c
    c.cleanup()


def test_initial_state_is_idle(core):
    assert core.state == "IDLE"


def test_arm_command(core):
    core.cmd_queue.put({"action": "arm"})
    core.process_commands()
    assert core.state == "ARMED"


def test_disarm_from_armed(core):
    core.cmd_queue.put({"action": "arm"})
    core.process_commands()
    core.cmd_queue.put({"action": "disarm"})
    core.process_commands()
    assert core.state == "IDLE"


def test_disarm_ignored_in_idle(core):
    core.cmd_queue.put({"action": "disarm"})
    core.process_commands()
    assert core.state == "IDLE"


def test_sensor_trigger_in_armed(core):
    core.state = "ARMED"
    core.on_sensor_triggered("pir")
    assert core.state == "ALERT"


def test_sensor_trigger_ignored_in_idle(core):
    core.state = "IDLE"
    core.on_sensor_triggered("pir")
    assert core.state == "IDLE"


def test_alert_to_challenge_after_grace(core):
    core.state = "ALERT"
    core.alert_start_time = 0  # long ago
    core.tick()
    assert core.state == "CHALLENGE"


def test_challenge_timeout_to_alarm(core):
    core.state = "CHALLENGE"
    core.challenge_start_time = 0  # long ago
    core.tick()
    assert core.state == "ALARM"


def test_challenge_solved(core):
    core.state = "CHALLENGE"
    core.on_challenge_solved()
    assert core.state == "DISARMED"


def test_disarmed_rearms_after_delay(core):
    core.state = "DISARMED"
    core.disarmed_start_time = 0  # long ago
    core.tick()
    assert core.state == "ARMED"


def test_reset_from_alarm(core):
    core.state = "ALARM"
    core.cmd_queue.put({"action": "reset"})
    core.process_commands()
    assert core.state == "IDLE"


def test_reset_ignored_outside_alarm(core):
    core.state = "ARMED"
    core.cmd_queue.put({"action": "reset"})
    core.process_commands()
    assert core.state == "ARMED"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_core.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement core module**

`sentinelpi/core.py`:
```python
import queue
import time
import logging

logger = logging.getLogger("sentinelpi.core")


class SentinelCore:
    STATES = ("IDLE", "ARMED", "ALERT", "CHALLENGE", "DISARMED", "ALARM")

    def __init__(self, config: dict, cmd_queue: queue.Queue):
        self.config = config
        self.cmd_queue = cmd_queue
        self.state = "IDLE"
        self.alert_start_time: float = 0
        self.challenge_start_time: float = 0
        self.disarmed_start_time: float = 0
        self._state_listeners: list = []

    def add_state_listener(self, callback):
        """Register a callback(old_state, new_state, extra_info) for state changes."""
        self._state_listeners.append(callback)

    def _set_state(self, new_state: str, **extra):
        old_state = self.state
        self.state = new_state
        logger.info(f"State: {old_state} -> {new_state}")
        for listener in self._state_listeners:
            listener(old_state, new_state, extra)

    def process_commands(self):
        """Drain the command queue and process each command."""
        while not self.cmd_queue.empty():
            try:
                cmd = self.cmd_queue.get_nowait()
            except queue.Empty:
                break
            action = cmd.get("action")
            if action == "arm" and self.state == "IDLE":
                self._set_state("ARMED")
            elif action == "disarm" and self.state == "ARMED":
                self._set_state("IDLE")
            elif action == "reset" and self.state == "ALARM":
                self._set_state("IDLE")

    def on_sensor_triggered(self, sensor_name: str):
        """Called when a sensor detects something while ARMED."""
        if self.state != "ARMED":
            return
        self.alert_start_time = time.monotonic()
        self._set_state("ALERT", sensor=sensor_name)

    def on_challenge_solved(self):
        """Called when the active puzzle is solved."""
        if self.state != "CHALLENGE":
            return
        self.disarmed_start_time = time.monotonic()
        self._set_state("DISARMED")

    def tick(self):
        """Called each main loop iteration to handle timed transitions."""
        now = time.monotonic()

        if self.state == "ALERT":
            elapsed = now - self.alert_start_time
            if elapsed >= self.config["timing"]["alert_grace_seconds"]:
                self.challenge_start_time = now
                self._set_state("CHALLENGE")

        elif self.state == "CHALLENGE":
            elapsed = now - self.challenge_start_time
            if elapsed >= self.config["timing"]["challenge_timeout_seconds"]:
                self._set_state("ALARM")

        elif self.state == "DISARMED":
            elapsed = now - self.disarmed_start_time
            if elapsed >= self.config["timing"]["disarmed_display_seconds"]:
                self._set_state("ARMED")

        elif self.state == "ALARM":
            auto_reset = self.config["timing"]["alarm_auto_reset_seconds"]
            if auto_reset > 0:
                # alarm_start_time would need tracking — skip for now, manual reset is default
                pass

    def cleanup(self):
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_core.py -v
```

Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/core.py tests/test_core.py
git commit -m "feat: add core state machine with all 6 states and transitions"
```

---

## Task 8: Web Dashboard — Backend

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/web/app.py`
- Create: `/home/kekkoz/sentinelpi/tests/test_web.py`

- [ ] **Step 1: Write failing tests**

`tests/test_web.py`:
```python
import json
import queue
import pytest

from sentinelpi.web.app import create_app


@pytest.fixture
def app():
    cmd_queue = queue.Queue()
    app = create_app(cmd_queue)
    app.config["TESTING"] = True
    return app, cmd_queue


@pytest.fixture
def client(app):
    flask_app, _ = app
    return flask_app.test_client()


def test_index_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"SentinelPi" in response.data


def test_api_state_returns_json(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "state" in data


def test_api_arm_enqueues_command(app):
    flask_app, cmd_queue = app
    client = flask_app.test_client()
    response = client.post("/api/arm")
    assert response.status_code == 200
    cmd = cmd_queue.get_nowait()
    assert cmd["action"] == "arm"


def test_api_disarm_enqueues_command(app):
    flask_app, cmd_queue = app
    client = flask_app.test_client()
    response = client.post("/api/disarm")
    assert response.status_code == 200
    cmd = cmd_queue.get_nowait()
    assert cmd["action"] == "disarm"


def test_api_reset_enqueues_command(app):
    flask_app, cmd_queue = app
    client = flask_app.test_client()
    response = client.post("/api/reset")
    assert response.status_code == 200
    cmd = cmd_queue.get_nowait()
    assert cmd["action"] == "reset"


def test_api_events_returns_list(client):
    response = client.get("/api/events")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_web.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement web backend**

`sentinelpi/web/app.py`:
```python
import queue
import json

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

# Module-level references set by create_app
_cmd_queue: queue.Queue = None
_state_ref: dict = None
_db_ref = None
_config_ref: dict = None
socketio = SocketIO()


def create_app(cmd_queue: queue.Queue, state_ref: dict = None, db=None, config: dict = None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "sentinelpi-dev"

    global _cmd_queue, _state_ref, _db_ref, _config_ref
    _cmd_queue = cmd_queue
    _state_ref = state_ref or {"state": "IDLE", "sensors": {}}
    _db_ref = db
    _config_ref = config

    socketio.init_app(app, async_mode="threading")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/state")
    def get_state():
        return jsonify(_state_ref)

    @app.route("/api/arm", methods=["POST"])
    def arm():
        _cmd_queue.put({"action": "arm"})
        return jsonify({"ok": True})

    @app.route("/api/disarm", methods=["POST"])
    def disarm():
        _cmd_queue.put({"action": "disarm"})
        return jsonify({"ok": True})

    @app.route("/api/reset", methods=["POST"])
    def reset():
        _cmd_queue.put({"action": "reset"})
        return jsonify({"ok": True})

    @app.route("/api/events")
    def get_events():
        if _db_ref:
            return jsonify(_db_ref.get_recent_events(limit=50))
        return jsonify([])

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(_config_ref or {})

    @app.route("/api/config", methods=["POST"])
    def update_config():
        updates = request.get_json()
        if updates and _config_ref:
            for section, values in updates.items():
                if section in _config_ref and isinstance(values, dict):
                    _config_ref[section].update(values)
            _cmd_queue.put({"action": "config_update", "config": _config_ref})
        return jsonify({"ok": True})

    return app


def emit_state_update(state_data: dict):
    """Emit state update to all connected WebSocket clients."""
    socketio.emit("state_update", state_data)


def emit_event(event_data: dict):
    """Emit a new event to all connected WebSocket clients."""
    socketio.emit("new_event", event_data)
```

- [ ] **Step 4: Create minimal index.html template**

`sentinelpi/web/templates/index.html`:
```html
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SentinelPi</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <h1>SentinelPi</h1>
    <p>Dashboard in costruzione...</p>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js"></script>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
```

Create empty static files:

`sentinelpi/web/static/style.css`:
```css
/* SentinelPi Dashboard Styles — Task 9 */
```

`sentinelpi/web/static/app.js`:
```javascript
// SentinelPi Dashboard Client — Task 9
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/test_web.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/web/ tests/test_web.py
git commit -m "feat: add Flask web backend with API routes and SocketIO"
```

---

## Task 9: Web Dashboard — Frontend

**Files:**
- Modify: `/home/kekkoz/sentinelpi/sentinelpi/web/templates/index.html`
- Modify: `/home/kekkoz/sentinelpi/sentinelpi/web/static/style.css`
- Modify: `/home/kekkoz/sentinelpi/sentinelpi/web/static/app.js`

- [ ] **Step 1: Implement the full dashboard HTML**

Replace `index.html` with the full dashboard. The HTML contains:
- Status panel with large colored circle and state name in Italian
- Sensor cards (Movimento, Luce, Suono) with enabled/disabled toggles and last trigger time
- Event log timeline
- Control bar (Arma/Disarma/Reset buttons)
- Config modal (grace period, challenge timeout, difficulty)

Key structure:
```html
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SentinelPi</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <header>
        <h1>SentinelPi</h1>
        <span id="state-badge" class="badge idle">Disattivo</span>
    </header>

    <main>
        <!-- Status Panel -->
        <section id="status-panel">
            <div id="status-circle" class="idle"></div>
            <p id="status-text">Disattivo</p>
            <p id="challenge-timer" class="hidden"></p>
        </section>

        <!-- Sensor Panel -->
        <section id="sensor-panel">
            <div class="sensor-card" id="sensor-pir">
                <h3>Movimento</h3>
                <span class="sensor-indicator"></span>
                <p class="last-trigger">—</p>
            </div>
            <div class="sensor-card" id="sensor-light">
                <h3>Luce</h3>
                <span class="sensor-indicator"></span>
                <p class="last-trigger">—</p>
            </div>
            <div class="sensor-card" id="sensor-sound">
                <h3>Suono</h3>
                <span class="sensor-indicator"></span>
                <p class="last-trigger">—</p>
            </div>
        </section>

        <!-- Event Log -->
        <section id="event-log">
            <h2>Eventi</h2>
            <ul id="event-list"></ul>
        </section>
    </main>

    <!-- Control Bar -->
    <nav id="control-bar">
        <button id="btn-arm" onclick="sendCommand('arm')">Arma</button>
        <button id="btn-disarm" onclick="sendCommand('disarm')">Disarma</button>
        <button id="btn-reset" onclick="sendCommand('reset')">Reset</button>
        <button id="btn-settings" onclick="toggleSettings()">⚙</button>
    </nav>

    <!-- Settings Modal -->
    <div id="settings-modal" class="hidden">
        <div class="modal-content">
            <h2>Configurazione</h2>
            <h3>Sensori</h3>
            <label class="toggle-label"><input type="checkbox" id="cfg-pir" checked> Movimento (PIR)</label>
            <label class="toggle-label"><input type="checkbox" id="cfg-light" checked> Luce</label>
            <label class="toggle-label"><input type="checkbox" id="cfg-sound" checked> Suono</label>
            <h3>Parametri</h3>
            <label>Periodo di grazia (s): <input type="range" id="cfg-grace" min="1" max="10" value="3"><span id="cfg-grace-val">3</span></label>
            <label>Timeout sfida (s): <input type="range" id="cfg-timeout" min="10" max="30" value="15"><span id="cfg-timeout-val">15</span></label>
            <label>Difficoltà: <input type="range" id="cfg-difficulty" min="1" max="5" value="1"><span id="cfg-difficulty-val">1</span></label>
            <button onclick="saveSettings()">Salva</button>
            <button onclick="toggleSettings()">Chiudi</button>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js"></script>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Implement style.css**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #0f172a; --surface: #1e293b; --text: #e2e8f0; --text-muted: #94a3b8;
    --green: #22c55e; --yellow: #eab308; --blue: #3b82f6; --red: #ef4444;
}

body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding-bottom: 80px; }

header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: var(--surface); }
header h1 { font-size: 1.3rem; }
.badge { padding: 4px 12px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; }
.badge.idle, .badge.armed, .badge.disarmed { background: var(--green); color: #000; }
.badge.alert { background: var(--yellow); color: #000; }
.badge.challenge { background: var(--blue); color: #fff; }
.badge.alarm { background: var(--red); color: #fff; }

#status-panel { text-align: center; padding: 32px 20px; }
#status-circle { width: 120px; height: 120px; border-radius: 50%; margin: 0 auto 16px; transition: background 0.3s; }
#status-circle.idle, #status-circle.armed, #status-circle.disarmed { background: var(--green); }
#status-circle.alert { background: var(--yellow); }
#status-circle.challenge { background: var(--blue); animation: pulse 1s infinite; }
#status-circle.alarm { background: var(--red); animation: pulse 0.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
#status-text { font-size: 1.5rem; font-weight: 700; }
#challenge-timer { font-size: 2rem; font-weight: 700; color: var(--blue); margin-top: 8px; }
.hidden { display: none !important; }

#sensor-panel { display: flex; gap: 12px; padding: 0 20px; justify-content: center; flex-wrap: wrap; }
.sensor-card { background: var(--surface); border-radius: 12px; padding: 16px; flex: 1; min-width: 100px; max-width: 160px; text-align: center; }
.sensor-card h3 { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px; }
.sensor-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: var(--text-muted); }
.sensor-indicator.active { background: var(--green); }
.last-trigger { font-size: 0.75rem; color: var(--text-muted); margin-top: 6px; }

#event-log { padding: 20px; }
#event-log h2 { font-size: 1rem; margin-bottom: 12px; color: var(--text-muted); }
#event-list { list-style: none; max-height: 300px; overflow-y: auto; }
#event-list li { padding: 8px 12px; border-left: 3px solid var(--text-muted); margin-bottom: 4px; font-size: 0.85rem; background: var(--surface); border-radius: 0 6px 6px 0; }
#event-list li.sensor_trigger { border-color: var(--yellow); }
#event-list li.state_change { border-color: var(--blue); }
#event-list li.challenge_result { border-color: var(--green); }

#control-bar { position: fixed; bottom: 0; left: 0; right: 0; display: flex; gap: 8px; padding: 12px 20px; background: var(--surface); border-top: 1px solid #334155; }
#control-bar button { flex: 1; padding: 12px; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }
#btn-arm { background: var(--green); color: #000; }
#btn-disarm { background: var(--text-muted); color: #000; }
#btn-reset { background: var(--red); color: #fff; }
#btn-settings { background: var(--surface); color: var(--text); border: 1px solid #475569 !important; flex: 0; padding: 12px 16px; }

#settings-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-content { background: var(--surface); border-radius: 16px; padding: 24px; width: 90%; max-width: 400px; }
.modal-content h2 { margin-bottom: 16px; }
.modal-content h3 { font-size: 0.9rem; color: var(--text-muted); margin: 16px 0 8px; }
.modal-content label { display: block; margin-bottom: 12px; font-size: 0.9rem; }
.modal-content input[type=range] { width: 100%; margin-top: 4px; }
.toggle-label { display: flex; align-items: center; gap: 8px; }
.toggle-label input[type=checkbox] { width: 18px; height: 18px; }
.modal-content button { width: 100%; padding: 10px; margin-top: 8px; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; background: var(--blue); color: #fff; font-weight: 600; }
```

- [ ] **Step 3: Implement app.js**

```javascript
const socket = io();
const STATE_NAMES = {
    IDLE: "Disattivo", ARMED: "Attivo", ALERT: "Allerta",
    CHALLENGE: "Sfida", DISARMED: "Disinnescato", ALARM: "Allarme"
};
const STATE_COLORS = {
    IDLE: "idle", ARMED: "armed", ALERT: "alert",
    CHALLENGE: "challenge", DISARMED: "disarmed", ALARM: "alarm"
};

// Send command to backend
function sendCommand(action) {
    fetch(`/api/${action}`, { method: "POST" });
}

// Toggle settings modal
function toggleSettings() {
    document.getElementById("settings-modal").classList.toggle("hidden");
}

// Update UI when state changes
socket.on("state_update", (data) => {
    const state = data.state;
    document.getElementById("status-circle").className = STATE_COLORS[state];
    document.getElementById("status-text").textContent = STATE_NAMES[state];
    document.getElementById("state-badge").className = "badge " + STATE_COLORS[state];
    document.getElementById("state-badge").textContent = STATE_NAMES[state];
});

// Add new event to log
socket.on("new_event", (event) => {
    const list = document.getElementById("event-list");
    const li = document.createElement("li");
    li.className = event.event_type;
    const time = event.timestamp ? event.timestamp.split(" ")[1] : "";
    li.textContent = `${time} — ${event.event_type}: ${event.state_from || ""} → ${event.state_to || ""} ${event.sensor ? "(" + event.sensor + ")" : ""}`;
    list.prepend(li);
});

// Load initial state and events
fetch("/api/state").then(r => r.json()).then(data => {
    const state = data.state || "IDLE";
    document.getElementById("status-circle").className = STATE_COLORS[state];
    document.getElementById("status-text").textContent = STATE_NAMES[state];
    document.getElementById("state-badge").className = "badge " + STATE_COLORS[state];
    document.getElementById("state-badge").textContent = STATE_NAMES[state];
});

fetch("/api/events").then(r => r.json()).then(events => {
    const list = document.getElementById("event-list");
    events.forEach(event => {
        const li = document.createElement("li");
        li.className = event.event_type;
        const time = event.timestamp ? event.timestamp.split(" ")[1] : "";
        li.textContent = `${time} — ${event.event_type}: ${event.state_from || ""} → ${event.state_to || ""} ${event.sensor ? "(" + event.sensor + ")" : ""}`;
        list.appendChild(li);
    });
});

// Range slider value display
document.querySelectorAll("input[type=range]").forEach(slider => {
    slider.addEventListener("input", () => {
        document.getElementById(slider.id + "-val").textContent = slider.value;
    });
});

// Save settings to backend
function saveSettings() {
    const config = {
        sensors: {
            pir_enabled: document.getElementById("cfg-pir").checked,
            light_enabled: document.getElementById("cfg-light").checked,
            sound_enabled: document.getElementById("cfg-sound").checked,
        },
        timing: {
            alert_grace_seconds: parseInt(document.getElementById("cfg-grace").value),
            challenge_timeout_seconds: parseInt(document.getElementById("cfg-timeout").value),
        },
        difficulty: {
            difficulty_level: parseInt(document.getElementById("cfg-difficulty").value),
        }
    };
    fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(config),
    });
    toggleSettings();
}

// Load config into settings modal
fetch("/api/config").then(r => r.json()).then(cfg => {
    if (cfg.sensors) {
        document.getElementById("cfg-pir").checked = cfg.sensors.pir_enabled;
        document.getElementById("cfg-light").checked = cfg.sensors.light_enabled;
        document.getElementById("cfg-sound").checked = cfg.sensors.sound_enabled;
    }
    if (cfg.timing) {
        document.getElementById("cfg-grace").value = cfg.timing.alert_grace_seconds;
        document.getElementById("cfg-grace-val").textContent = cfg.timing.alert_grace_seconds;
        document.getElementById("cfg-timeout").value = cfg.timing.challenge_timeout_seconds;
        document.getElementById("cfg-timeout-val").textContent = cfg.timing.challenge_timeout_seconds;
    }
    if (cfg.difficulty) {
        document.getElementById("cfg-difficulty").value = cfg.difficulty.difficulty_level;
        document.getElementById("cfg-difficulty-val").textContent = cfg.difficulty.difficulty_level;
    }
});

// Challenge countdown timer
let challengeInterval = null;
socket.on("state_update", (data) => {
    if (data.state === "CHALLENGE" && data.challenge_remaining) {
        document.getElementById("challenge-timer").classList.remove("hidden");
        clearInterval(challengeInterval);
        let remaining = data.challenge_remaining;
        document.getElementById("challenge-timer").textContent = remaining + "s";
        challengeInterval = setInterval(() => {
            remaining--;
            document.getElementById("challenge-timer").textContent = Math.max(0, remaining) + "s";
            if (remaining <= 0) clearInterval(challengeInterval);
        }, 1000);
    } else {
        document.getElementById("challenge-timer").classList.add("hidden");
        clearInterval(challengeInterval);
    }
});
```

- [ ] **Step 4: Test dashboard manually in simulation mode**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python run.py --simulate
```

Open browser to `http://localhost:5000` — verify page loads with status circle, sensor cards, event log, and control buttons.

- [ ] **Step 5: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/web/templates/ sentinelpi/web/static/
git commit -m "feat: add complete web dashboard with real-time UI"
```

---

## Task 10: Simulation Module

**Files:**
- Create: `/home/kekkoz/sentinelpi/sentinelpi/simulator.py`

This module makes simulation mode actually useful — random sensor triggers and keyboard input for buttons.

- [ ] **Step 1: Implement simulator module**

`sentinelpi/simulator.py`:
```python
import random
import sys
import select
import threading
import time
import logging

logger = logging.getLogger("sentinelpi.simulator")


class Simulator:
    """Provides simulated sensor triggers and keyboard button input for development without hardware."""

    def __init__(self, sensors, trigger_interval: float = 10.0):
        self.sensors = sensors
        self.trigger_interval = trigger_interval
        self._running = False
        self._threads: list[threading.Thread] = []

    def start(self):
        self._running = True
        # Thread for random sensor triggers
        t1 = threading.Thread(target=self._random_triggers, daemon=True)
        t1.start()
        self._threads.append(t1)
        # Thread for keyboard input
        t2 = threading.Thread(target=self._keyboard_input, daemon=True)
        t2.start()
        self._threads.append(t2)
        logger.info(f"Simulator started — random triggers every ~{self.trigger_interval}s, press 'a'/'b' + Enter for buttons")

    def stop(self):
        self._running = False

    def _random_triggers(self):
        sensor_names = []
        if self.sensors.pir:
            sensor_names.append(("pir", self.sensors.pir))
        if self.sensors.light:
            sensor_names.append(("light", self.sensors.light))
        if self.sensors.sound:
            sensor_names.append(("sound", self.sensors.sound))

        while self._running:
            time.sleep(self.trigger_interval + random.uniform(-3, 3))
            if not self._running or not sensor_names:
                break
            name, sensor = random.choice(sensor_names)
            logger.info(f"[SIM] Triggering sensor: {name}")
            sensor.pin.drive_high()
            time.sleep(0.2)  # keep it high briefly so check_sensors() catches it
            sensor.pin.drive_low()

    def _keyboard_input(self):
        """Read 'a' and 'b' keypresses from stdin to simulate button presses."""
        while self._running:
            try:
                if select.select([sys.stdin], [], [], 0.5)[0]:
                    key = sys.stdin.readline().strip().lower()
                    if key == "a" and self.sensors.button_a.when_pressed:
                        logger.info("[SIM] Button A pressed")
                        self.sensors.button_a.pin.drive_low()  # active-low
                        time.sleep(0.05)
                        self.sensors.button_a.pin.drive_high()
                    elif key == "b" and self.sensors.button_b.when_pressed:
                        logger.info("[SIM] Button B pressed")
                        self.sensors.button_b.pin.drive_low()
                        time.sleep(0.05)
                        self.sensors.button_b.pin.drive_high()
            except (EOFError, OSError):
                break
```

- [ ] **Step 2: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add sentinelpi/simulator.py
git commit -m "feat: add simulation module for dev without hardware"
```

---

## Task 11: Main Loop Integration

**Files:**
- Modify: `/home/kekkoz/sentinelpi/run.py`

- [ ] **Step 1: Implement the full run.py that wires everything together**

`run.py` — the main entry point that:
1. Loads config
2. Initializes database
3. Initializes sensors and actuators
4. Creates core state machine
5. Creates web app
6. Starts web server in background thread
7. Runs main loop: poll sensors, run state machine tick, handle button callbacks

```python
import argparse
import logging
import os
import queue
import signal
import sys
import threading
import time

from sentinelpi import __version__
from sentinelpi.config import load_config, difficulty_to_sequence_length
from sentinelpi.database import EventDB
from sentinelpi.core import SentinelCore
from sentinelpi.challenge import pick_challenge
from sentinelpi.web.app import create_app, socketio, emit_state_update, emit_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("sentinelpi")


def main():
    parser = argparse.ArgumentParser(description="SentinelPi security system")
    parser.add_argument("--simulate", action="store_true", help="Run without real GPIO")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    if args.simulate:
        os.environ["GPIOZERO_PIN_FACTORY"] = "mock"

    # Late imports so GPIOZERO_PIN_FACTORY is set before gpiozero loads
    from sentinelpi.actuators import Actuators
    from sentinelpi.sensors import SensorManager

    config = load_config(args.config)
    logger.info(f"SentinelPi v{__version__} — {'SIMULATION' if args.simulate else 'HARDWARE'} mode")

    # Initialize components
    from pathlib import Path
    project_dir = Path(__file__).resolve().parent
    db = EventDB(str(project_dir / "data" / "events.db"))
    cmd_queue = queue.Queue()
    core = SentinelCore(config, cmd_queue)
    actuators = Actuators(config["pins"])
    sensors = SensorManager(config["pins"], config["sensors"])

    # Shared state for web dashboard
    state_ref = {"state": "IDLE", "sensors": {}}

    # State change listener — update actuators, database, web
    active_challenge = [None]  # mutable container for closure

    def on_state_change(old_state, new_state, extra):
        state_ref["state"] = new_state
        actuators.set_state(new_state)
        db.log_event(
            "state_change",
            state_from=old_state,
            state_to=new_state,
            sensor=extra.get("sensor"),
        )
        update_data = dict(state_ref)
        if new_state == "CHALLENGE":
            update_data["challenge_remaining"] = config["timing"]["challenge_timeout_seconds"]
        emit_state_update(update_data)
        emit_event({
            "event_type": "state_change",
            "state_from": old_state,
            "state_to": new_state,
            "sensor": extra.get("sensor"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        # Start challenge when entering CHALLENGE state
        if new_state == "CHALLENGE":
            daily_alarms = db.get_daily_alarm_count()
            base_len = difficulty_to_sequence_length(config["difficulty"]["difficulty_level"])
            seq_len = min(base_len + daily_alarms, config["difficulty"]["max_sequence_length"])
            active_challenge[0] = pick_challenge(
                seq_len, config["difficulty"]["button_rhythm_tolerance_ms"]
            )
            logger.info(f"Challenge started: {active_challenge[0].name} (length={seq_len})")

    core.add_state_listener(on_state_change)

    # Button callbacks
    def on_button_a():
        if core.state == "CHALLENGE" and active_challenge[0]:
            ch = active_challenge[0]
            if hasattr(ch, "press_a"):
                ch.press_a()
            if hasattr(ch, "cycle_color"):
                ch.cycle_color()
        elif core.state in ("IDLE", "ARMED"):
            cmd_queue.put({"action": "arm" if core.state == "IDLE" else "disarm"})

    def on_button_b():
        if core.state == "CHALLENGE" and active_challenge[0]:
            ch = active_challenge[0]
            result = None
            if hasattr(ch, "submit_selection"):
                result = ch.submit_selection()
            elif hasattr(ch, "submit_count"):
                result = ch.submit_count()
            elif hasattr(ch, "check_rhythm"):
                result = ch.check_rhythm()
            if result == "solved":
                core.on_challenge_solved()
        elif core.state == "ALARM":
            # Hold detection would go here; for now single press resets
            cmd_queue.put({"action": "reset"})

    sensors.button_a.when_pressed = on_button_a
    sensors.button_b.when_pressed = on_button_b

    # Web server in background thread
    app = create_app(cmd_queue, state_ref, db, config)
    web_thread = threading.Thread(
        target=lambda: socketio.run(
            app,
            host=config["web"]["host"],
            port=config["web"]["port"],
            allow_unsafe_werkzeug=True,
            use_reloader=False,
        ),
        daemon=True,
    )
    web_thread.start()
    logger.info(f"Dashboard: http://{config['web']['host']}:{config['web']['port']}")

    # Set initial actuator state
    actuators.set_state("IDLE")

    # Start simulator if in simulation mode
    simulator = None
    if args.simulate:
        from sentinelpi.simulator import Simulator
        simulator = Simulator(sensors)
        simulator.start()

    # Graceful shutdown
    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Main loop
    try:
        while running:
            core.process_commands()

            # Check sensors only when ARMED
            if core.state == "ARMED":
                triggered = sensors.check_sensors()
                if triggered:
                    core.on_sensor_triggered(triggered)

            core.tick()
            time.sleep(0.05)  # 50ms loop — responsive enough
    finally:
        logger.info("Shutting down...")
        if simulator:
            simulator.stop()
        actuators.cleanup()
        sensors.cleanup()
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run in simulation mode to verify**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python run.py --simulate
```

Expected: System starts, logs show "SIMULATION mode", dashboard accessible at http://localhost:5000. Test arm/disarm buttons via dashboard.

- [ ] **Step 3: Commit**

```bash
cd /home/kekkoz/sentinelpi
git add run.py
git commit -m "feat: wire up main loop integrating all modules"
```

---

## Task 12: Run All Tests

- [ ] **Step 1: Run full test suite**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass (config: 6, database: 6, actuators: 7, sensors: 6, challenge: 11, core: 12, web: 6 — total ~54 tests)

- [ ] **Step 2: Fix any failures**

If any tests fail, fix them before proceeding.

- [ ] **Step 3: Commit any fixes**

```bash
cd /home/kekkoz/sentinelpi
git add -A
git commit -m "fix: resolve test failures from integration"
```

---

## Task 13: Manual End-to-End Test (Simulation)

- [ ] **Step 1: Start system in simulation mode**

```bash
cd /home/kekkoz/sentinelpi && source venv/bin/activate
python run.py --simulate
```

- [ ] **Step 2: Test via dashboard**

Open `http://localhost:5000` in browser. Verify:
1. Page loads with "Disattivo" status
2. Click "Arma" → status changes to "Attivo" (green)
3. Events appear in log
4. Click "Disarma" → back to "Disattivo"
5. Click "Reset" does nothing (only works in ALARM state)

- [ ] **Step 3: Document any issues found and fix them**

- [ ] **Step 4: Final commit**

```bash
cd /home/kekkoz/sentinelpi
git add -A
git commit -m "chore: final integration fixes and manual testing"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Project scaffold | — |
| 2 | Config module | 6 |
| 3 | Database module | 6 |
| 4 | Actuators (LEDs + buzzer) | 7 |
| 5 | Sensors (PIR, light, sound, buttons) | 6 |
| 6 | Challenge (3 puzzles) | 11 |
| 7 | Core state machine | 12 |
| 8 | Web backend (Flask API) | 6 |
| 9 | Web frontend (dashboard) | manual |
| 10 | Simulation module | — |
| 11 | Main loop integration | manual |
| 12 | Full test suite | all |
| 13 | End-to-end manual test | manual |

**Build order rationale**: Bottom-up (hardware abstractions → logic → web → simulation → integration). Each task produces a testable, committable unit. The simulation mode (Task 10) means you can develop and test tasks 1-11 without any hardware connected — perfect for starting before the kit arrives on Saturday.

**Known v1 limitations** (acceptable, documented for future):
- `alarm_auto_reset_seconds` is not implemented (manual reset only, which is the default)
- ALARM reset via button uses single press, not 3-second hold
- No GPIO error handling with graceful degradation (crashes on pin init failure)
