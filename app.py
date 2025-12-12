"""
App Flask ligera para controlar dos relés (aire y electricidad) con cuenta atrás
fiable y loops on/off. Frontend HTML/JS responsive y muy visual.
"""
import threading
import time
from flask import Flask, jsonify, render_template, request

try:
    import RPi.GPIO as GPIO

    HW = True
except ImportError:
    HW = False  # Permite probar en PC

app = Flask(__name__)

# Configuración GPIO
DEVICES = {
    "air": {"pin": 18, "active_high": True, "label": "Aire", "icon": "🌬️"},
    "power": {"pin": 23, "active_high": True, "label": "Electricidad", "icon": "⚡"},
}

if HW:
    GPIO.setmode(GPIO.BCM)
    for dev in DEVICES.values():
        initial = GPIO.LOW if dev["active_high"] else GPIO.HIGH
        GPIO.setup(dev["pin"], GPIO.OUT, initial=initial)

# Estado
STATE = {
    name: {"mode": "idle", "seconds_left": 0, "total": 0, "phase": "", "started_at": 0.0}
    for name in DEVICES
}
LOCK = threading.Lock()


def set_relay(device: str, closed: bool) -> None:
    """Activa/desactiva el relé según lógica del módulo."""
    if not HW:
        return
    dev = DEVICES[device]
    pin = dev["pin"]
    active_high = dev["active_high"]
    GPIO.output(pin, GPIO.HIGH if closed == active_high else GPIO.LOW)


def run_countdown(device: str, duration: int) -> None:
    with LOCK:
        STATE[device].update(
            mode="single",
            seconds_left=duration,
            total=duration,
            phase="on",
            started_at=time.time(),
        )
    set_relay(device, True)
    end_ts = time.time() + duration
    while True:
        now = time.time()
        with LOCK:
            if STATE[device]["mode"] != "single":
                break
            STATE[device]["seconds_left"] = max(0, int(end_ts - now))
        if now >= end_ts:
            break
        time.sleep(0.2)
    set_relay(device, False)
    with LOCK:
        STATE[device].update(mode="idle", seconds_left=0, total=0, phase="", started_at=0.0)


def run_loop(device: str, on_seconds: int, off_seconds: int, total_seconds: int) -> None:
    end_ts = time.time() + total_seconds
    with LOCK:
        STATE[device].update(
            mode="loop",
            total=total_seconds,
            seconds_left=total_seconds,
            phase="on",
            started_at=time.time(),
        )
    while True:
        now = time.time()
        with LOCK:
            if STATE[device]["mode"] != "loop":
                break
        # ON
        if on_seconds > 0:
            with LOCK:
                STATE[device]["phase"] = "on"
            set_relay(device, True)
            phase_end = min(end_ts, time.time() + on_seconds)
            while time.time() < phase_end:
                with LOCK:
                    if STATE[device]["mode"] != "loop":
                        break
                with LOCK:
                    STATE[device]["seconds_left"] = max(0, int(end_ts - time.time()))
                time.sleep(0.2)
        with LOCK:
            if STATE[device]["mode"] != "loop":
                break
        # OFF
        if off_seconds > 0:
            with LOCK:
                STATE[device]["phase"] = "off"
            set_relay(device, False)
            phase_end = min(end_ts, time.time() + off_seconds)
            while time.time() < phase_end:
                with LOCK:
                    if STATE[device]["mode"] != "loop":
                        break
                with LOCK:
                    STATE[device]["seconds_left"] = max(0, int(end_ts - time.time()))
                time.sleep(0.2)
        if time.time() >= end_ts:
            break
    set_relay(device, False)
    with LOCK:
        STATE[device].update(mode="idle", seconds_left=0, total=0, phase="", started_at=0.0)


@app.route("/")
def home():
    return render_template("index.html", devices=DEVICES)


@app.route("/api/status")
def api_status():
    payload = {}
    with LOCK:
        for name, st in STATE.items():
            total = st["total"]
            left = st["seconds_left"]
            percent = 0 if total == 0 else max(0, min(100, int(100 * (1 - left / total))))
            payload[name] = {
                "mode": st["mode"],
                "seconds_left": left,
                "total": total,
                "phase": st["phase"],
                "percent": percent,
            }
    return jsonify(payload)


@app.route("/api/single", methods=["POST"])
def api_single():
    data = request.get_json(force=True)
    device = data.get("device")
    seconds = int(data.get("seconds", 0))
    if device not in DEVICES or seconds <= 0:
        return jsonify({"ok": False, "msg": "Datos inválidos"}), 400
    with LOCK:
        if STATE[device]["mode"] != "idle":
            return jsonify({"ok": False, "msg": "Dispositivo ocupado"}), 409
    threading.Thread(target=run_countdown, args=(device, seconds), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/loop", methods=["POST"])
def api_loop():
    data = request.get_json(force=True)
    device = data.get("device")
    on_s = int(data.get("on_seconds", 0))
    off_s = int(data.get("off_seconds", 0))
    total_s = int(data.get("total_seconds", 0))
    if device not in DEVICES or on_s <= 0 or off_s <= 0 or total_s <= 0:
        return jsonify({"ok": False, "msg": "Datos inválidos"}), 400
    with LOCK:
        if STATE[device]["mode"] != "idle":
            return jsonify({"ok": False, "msg": "Dispositivo ocupado"}), 409
    threading.Thread(target=run_loop, args=(device, on_s, off_s, total_s), daemon=True).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Solo para pruebas locales; en producción usar gunicorn/waitress o similar
    app.run(host="0.0.0.0", port=666, debug=False)

