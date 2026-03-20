# SentinelPi — Design Spec

**Date**: 2026-03-19
**Status**: Approved
**Author**: kekkoz + Claude

## Overview

SentinelPi is a Raspberry Pi 5 security system with a playful twist. It monitors a zone using physical sensors (motion, light, sound) and reacts with LEDs and a buzzer. When triggered, instead of a simple PIN code, the user must solve a physical puzzle using buttons to disarm it. A web dashboard provides real-time monitoring, event logs, and configuration.

The project uses the Elegoo 37-in-1 sensor kit and runs as a standalone Python application, with a modular architecture that allows future integration with the existing Raspy voice assistant.

## Goals

1. **Learn GPIO/physical computing** — first hands-on project with sensors and actuators
2. **Immediate satisfaction** — sensor triggers a visible/audible reaction within the first session
3. **Fun and replayable** — puzzle mechanics make it engaging, not just utilitarian
4. **Leverage web skills** — real-time dashboard uses familiar web technologies
5. **Standalone first** — works independently, extensible for Raspy integration later

## Architecture

Three layers communicating vertically:

```
┌─────────────────────────────────────┐
│         Dashboard Web (Flask)       │
│  Stato sensori │ Log │ Config       │
└────────────┬────────────────────────┘
             │ WebSocket (real-time)
┌────────────▼────────────────────────┐
│          Core Engine (Python)       │
│  State Machine + Challenge Logic    │
└────────────┬────────────────────────┘
             │ GPIO (gpiozero)
┌────────────▼────────────────────────┐
│        Hardware Layer (sensors)     │
│  PIR │ Light │ Sound │ Buzzer │    │
│  LEDs │ Buttons │ Buzzer           │
└─────────────────────────────────────┘
```

**Single process** with threads: main thread runs the core engine and GPIO polling, a secondary thread runs the Flask/SocketIO web server (explicitly using `async_mode='threading'` to avoid conflicts with gpiozero). Communication between web and core engine via a `queue.Queue` (thread-safe): web thread enqueues commands (arm, disarm, reset, config changes), core thread dequeues and processes them each loop iteration. State updates flow back via SocketIO `emit()` calls from the core thread.

## Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.13 | Same as Raspy, familiar environment |
| GPIO | gpiozero | High-level, beginner-friendly, well-documented |
| Web server | Flask + Flask-SocketIO | Lightweight, familiar for web devs |
| Real-time | WebSocket (via SocketIO) | Push updates to dashboard instantly |
| Database | SQLite | Zero config, single file, good enough for event logs |
| Config | JSON file | Simple, human-readable, editable |

## State Machine

The core engine is a finite state machine with 6 states:

```
  [IDLE] ──(arm via web/button)──▶ [ARMED]
    ▲                              │    │
    │                    (disarm)──┘    │
    │                          (sensor triggered)
    │                                   ▼
    │                               [ALERT]
    │                            3 sec grace period
    │                                   │
    │                                   ▼
    │                             [CHALLENGE]
    │                          puzzle to solve (15s)
    │                           /               \
    │                     (solved)          (timeout)
    │                        /                     \
    │              [DISARMED]                    [ALARM]
    │            re-arms after 3s            buzzer + red LED
    │                  │                     log + web notif
    │                  ▼                          │
    │              [ARMED]                  (reset via web/btn)
    │                                             │
    └─────────────────────────────────────────────┘
```

### State Transitions (complete)

| From | To | Trigger |
|---|---|---|
| IDLE | ARMED | Arm button pressed or arm via web dashboard |
| ARMED | IDLE | Disarm button pressed or disarm via web dashboard |
| ARMED | ALERT | Any enabled sensor triggered |
| ALERT | CHALLENGE | Grace period (3s) elapsed |
| CHALLENGE | DISARMED | Puzzle solved correctly |
| CHALLENGE | ALARM | Timeout (15s) elapsed — no abort path, timer always runs |
| DISARMED | ARMED | Automatic after 3 seconds (system re-arms itself) |
| ALARM | IDLE | Manual reset via web dashboard or button combo (hold button 3s) |

### State Descriptions

- **IDLE**: System off. Green LED breathes slowly. Dashboard shows "Disattivo".
- **ARMED**: Monitoring active. Green LED solid. Sensors polled continuously. Dashboard shows "Attivo". Can be disarmed voluntarily via button or web.
- **ALERT**: Sensor triggered. Blue LED flashes. 3-second grace period before challenge starts. Allows the owner to reach the puzzle interface.
- **CHALLENGE**: Puzzle active. Blue LED solid. User has 15 seconds to solve. Timer shown on dashboard. Buzzer beeps softly as countdown warning. No abort — must solve or wait for timeout.
- **DISARMED**: Puzzle solved successfully. Green LED flashes in celebration. Buzzer plays success tone. Auto-transitions back to ARMED after 3 seconds (security system re-arms itself).
- **ALARM**: Puzzle failed or timeout. Red LED solid + buzzer continuous. Dashboard shows alert with event details. Requires manual reset: via web dashboard button or holding the physical button for 3 seconds.

## Hardware Mapping

| Component | GPIO Pin | Direction | Pull | Purpose |
|---|---|---|---|---|
| PIR motion sensor | GPIO17 | Input | pull-down | Detect movement (outputs HIGH on detection) |
| Photoresistor (digital) | GPIO27 | Input | pull-up | Detect sudden light changes (digital output via onboard comparator) |
| Sound sensor (digital) | GPIO22 | Input | pull-up | Detect loud noises (digital output via onboard comparator) |
| Red LED | GPIO5 | Output | — | ALARM state indicator |
| Green LED | GPIO6 | Output | — | ARMED/OK state indicator |
| Blue LED | GPIO13 | Output | — | CHALLENGE state indicator |
| Active buzzer | GPIO19 | Output | — | Audio alerts and feedback |
| Button A | GPIO16 | Input | pull-up | Puzzle input + arm/disarm (active-low) |
| Button B | GPIO26 | Input | pull-up | Puzzle input (active-low) |

**Note on analog sensors**: The Elegoo kit's photoresistor module has a **digital output pin** with an onboard potentiometer to set the threshold. The sound sensor module works the same way. We use these digital outputs, avoiding the need for an ADC.

**Decision on joystick**: The Elegoo joystick is an analog device (potentiometer-based). The Raspberry Pi has no ADC, so reading directional input reliably is not possible with digital GPIO alone (the resting position voltage sits near the threshold, causing phantom reads). **For v1, we skip the joystick entirely** and use two push buttons (Button A and Button B) for puzzle input. This is simpler, more reliable, and the Elegoo kit includes multiple button/switch modules. The joystick can be added in a future version with an ADS1115 ADC module.

**Note on future joystick support**: If an ADS1115 ADC is added later, the joystick X/Y axes would connect via I2C (SDA=GPIO2, SCL=GPIO3), not individual GPIO pins. The config would need I2C address entries instead of pin numbers.

## Challenge System (Puzzles)

When the system enters CHALLENGE state, one puzzle is randomly selected. All puzzles use only Button A, Button B, and the LEDs/buzzer — no joystick needed.

### Puzzle 1: Simon Says
- The 3 LEDs blink in a random sequence (e.g., red, blue, green, red)
- User maps: Button A = next color in cycle (red→green→blue→red), Button B = confirm selection
- Must reproduce the full sequence correctly
- Wrong input → sequence restarts from the beginning
- Difficulty scaling: longer sequences

### Puzzle 2: Button Rhythm
- Buzzer plays a rhythm pattern (e.g., beep-beep-pause-beep)
- User replicates the rhythm by pressing Button A with correct timing
- Tolerance window: ±200ms
- Difficulty scaling: longer patterns, tighter tolerance

### Puzzle 3: Counting Challenge
- Buzzer beeps N times (with LEDs flashing in sync)
- User must press Button A exactly N times, then confirm with Button B
- Too many or too few presses → fail
- Difficulty scaling: higher numbers, faster beep tempo

### Difficulty Scaling
- Base difficulty: sequence/count length 3
- Each alarm triggered in the same day adds +1 to the length
- Maximum length: 8
- `difficulty_level` in config stores a value 1-5; code derives base sequence length as `difficulty_level + 2` (so 1→3, 5→7)
- Daily alarm counter stored in SQLite, resets at midnight

## Web Dashboard

### Single-page application served by Flask

**Header**: SentinelPi logo/name + current state badge (color-coded)

**Main sections**:

1. **Status Panel** (top)
   - Large colored circle showing current state (green/yellow/blue/red)
   - State name in Italian
   - If in CHALLENGE: countdown timer and puzzle hint

2. **Sensor Panel** (middle)
   - 3 cards: Movimento, Luce, Suono
   - Each shows: enabled/disabled toggle, last trigger time, activity indicator
   - Real-time updates via WebSocket

3. **Event Log** (bottom)
   - Scrollable timeline of events with timestamps
   - Color-coded by event type (trigger, challenge, alarm, disarm)
   - Stored in SQLite, loaded on page open, new events pushed via WebSocket

4. **Control Bar** (fixed bottom)
   - Arma / Disarma / Reset buttons
   - Settings gear icon → opens config modal

**Config Modal**:
- Enable/disable individual sensors
- Alert grace period (1-10 seconds)
- Challenge timeout (10-30 seconds)
- Base puzzle difficulty (1-5, maps to base sequence length 3-7)

### Tech details
- Single HTML file with embedded CSS and JS (simple, no build tools)
- WebSocket via Socket.IO client library (CDN)
- Responsive: works on phone browser over local network
- No authentication for v1 (local network only)

## Project Structure

```
/home/kekkoz/sentinelpi/
├── sentinelpi/
│   ├── __init__.py
│   ├── core.py          # State machine, event loop, state transitions
│   ├── sensors.py       # Sensor wrappers using gpiozero
│   ├── actuators.py     # LED and buzzer control
│   ├── challenge.py     # Puzzle logic and difficulty scaling
│   ├── database.py      # SQLite schema, event logging, queries
│   └── web/
│       ├── app.py       # Flask + SocketIO routes and events
│       ├── templates/
│       │   └── index.html  # Dashboard SPA
│       └── static/
│           ├── style.css
│           └── app.js      # SocketIO client, UI logic
├── config.json          # Pin assignments, timeouts, difficulty settings
├── run.py               # Entry point, argument parsing
└── requirements.txt     # Python dependencies
```

## Configuration File (config.json)

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

## Database Schema (SQLite)

Single file: `sentinelpi/data/events.db`

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    event_type TEXT NOT NULL,  -- 'sensor_trigger', 'state_change', 'challenge_result', 'config_change'
    state_from TEXT,           -- state before event (e.g., 'ARMED')
    state_to TEXT,             -- state after event (e.g., 'ALERT')
    sensor TEXT,               -- which sensor triggered (e.g., 'pir', 'light', 'sound'), NULL if not sensor event
    details TEXT               -- JSON string for extra info (e.g., puzzle type, success/fail)
);

CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_type ON events(event_type);
```

**Daily alarm counter query** (for difficulty scaling):
```sql
SELECT COUNT(*) FROM events
WHERE event_type = 'state_change' AND state_to = 'ALARM'
AND date(timestamp) = date('now', 'localtime');
```

## Configuration Notes

- `alarm_auto_reset_seconds`: When set to `0` (default), ALARM state requires manual reset. If set to a positive value, ALARM auto-transitions to IDLE after that many seconds.
- UI convention: **interface text in Italian, code identifiers in English**.

## Simulation Mode

Running with `python run.py --simulate` enables a mode where:
- No real GPIO is accessed (no hardware needed)
- Sensors generate random trigger events at configurable intervals
- Button A/B inputs are simulated via keyboard ('a' and 'b' keys)
- Dashboard works normally
- Useful for developing and testing the web dashboard and state machine logic without the Pi or sensors connected

## Error Handling

- **Sensor read failures**: Log warning, skip that sensor for current poll cycle, retry next cycle
- **GPIO initialization failure**: If a pin fails to initialize, disable that sensor/actuator and log an error. System continues with remaining hardware.
- **Web server failure**: Core engine continues operating independently. Dashboard is a monitoring layer, not a control dependency.
- **SQLite failures**: Log to stderr as fallback. System operation is not dependent on logging.

## Testing Strategy

### Incremental hardware testing
Build and test in this order:
1. **Single LED** — blink test, confirm GPIO works
2. **Single sensor (PIR) + LED** — motion triggers LED
3. **State machine** — IDLE → ARMED → ALERT with real sensor
4. **Buzzer** — add audio feedback to states
5. **Buttons + challenge** — add puzzle mechanics
6. **Dashboard** — add web layer last
7. **Full integration** — all components together

### Simulation testing
- State machine logic testable entirely in simulation mode
- Dashboard testable without hardware
- Challenge logic testable with keyboard input

## Future Expansion (not in v1)

- Raspy voice integration ("Raspy, attiva l'allarme")
- USB camera: take photo when alarm triggers
- Telegram/push notifications
- Multiple zones with multiple sensor sets
- MQTT integration for IoT ecosystem
- Persistent statistics and graphs on dashboard
- Auto-start on boot via systemd service
- Joystick support with ADS1115 ADC module for richer puzzle input
