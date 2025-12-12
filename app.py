"""
App Streamlit para controlar dos relés con Raspberry Pi 4 (ej. aire y electricidad).
- Cada relé tiene modo simple (cuenta atrás) y modo loop on/off con duración total.
- Durante actividad: fondo rojo, contador grande y barra amarilla 0‑100% según progreso.
- Inactivo: fondo verde indicando relé abierto.
"""
import threading
import time
import streamlit as st

try:
    import RPi.GPIO as GPIO
    HW = True
except ImportError:
    HW = False  # Permite probar en PC


# Configuración de GPIO por dispositivo
DEVICES = {
    "air": {"pin": 18, "active_high": True, "icon": "🌬️ Aire"},
    "power": {"pin": 23, "active_high": True, "icon": "⚡ Electricidad"},
}

if HW:
    GPIO.setmode(GPIO.BCM)
    for dev in DEVICES.values():
        initial = GPIO.LOW if dev["active_high"] else GPIO.HIGH
        GPIO.setup(dev["pin"], GPIO.OUT, initial=initial)

# Estado por dispositivo
STATE = {
    name: {"mode": "idle", "seconds_left": 0, "total": 0, "phase": ""}
    for name in DEVICES
}
LOCK = threading.Lock()


def set_valve(device: str, closed: bool) -> None:
    """Activa/desactiva el relé según la lógica del módulo."""
    if not HW:
        return
    dev = DEVICES[device]
    pin = dev["pin"]
    active_high = dev["active_high"]
    GPIO.output(pin, GPIO.HIGH if closed == active_high else GPIO.LOW)


def run_countdown(device: str, duration: int) -> None:
    """Cuenta atrás en hilo separado."""
    with LOCK:
        STATE[device].update(mode="single", seconds_left=duration, total=duration, phase="")
    set_valve(device, True)  # cerrar
    start = time.time()
    while True:
        with LOCK:
            if STATE[device]["mode"] != "single":
                break
            remaining = max(0, duration - int(time.time() - start))
            STATE[device]["seconds_left"] = remaining
        if remaining <= 0:
            break
        time.sleep(0.2)
    set_valve(device, False)  # abrir
    with LOCK:
        STATE[device].update(mode="idle", seconds_left=0, total=0, phase="")


def _tick(device: str, end_ts: float) -> None:
    with LOCK:
        STATE[device]["seconds_left"] = max(0, int(end_ts - time.time()))


def run_loop(device: str, on_seconds: int, off_seconds: int, total_seconds: int) -> None:
    """Ejecuta un ciclo on/off hasta agotar total_seconds; termina con relé abierto."""
    end_ts = time.time() + total_seconds
    with LOCK:
        STATE[device].update(
            mode="loop", total=total_seconds, seconds_left=total_seconds, phase="on"
        )
    while time.time() < end_ts:
        with LOCK:
            if STATE[device]["mode"] != "loop":
                break
        # Fase ON (cerrado)
        if on_seconds > 0:
            with LOCK:
                STATE[device]["phase"] = "on"
            set_valve(device, True)
            phase_end = min(end_ts, time.time() + on_seconds)
            while time.time() < phase_end:
                with LOCK:
                    if STATE[device]["mode"] != "loop":
                        break
                _tick(device, end_ts)
                time.sleep(0.2)
        with LOCK:
            if STATE[device]["mode"] != "loop" or time.time() >= end_ts:
                break
        # Fase OFF (abierto)
        if off_seconds > 0:
            with LOCK:
                STATE[device]["phase"] = "off"
            set_valve(device, False)
            phase_end = min(end_ts, time.time() + off_seconds)
            while time.time() < phase_end:
                with LOCK:
                    if STATE[device]["mode"] != "loop":
                        break
                _tick(device, end_ts)
                time.sleep(0.2)
    # Finalizar asegurando abierto
    set_valve(device, False)
    with LOCK:
        STATE[device].update(mode="idle", seconds_left=0, total=0, phase="")


def ensure_session_defaults(prefix: str) -> None:
    """Inicializa valores de tiempo en sesión para cada dispositivo."""
    keys = [
        f"{prefix}_mins",
        f"{prefix}_secs",
        f"{prefix}_loop_on_min",
        f"{prefix}_loop_on_sec",
        f"{prefix}_loop_off_min",
        f"{prefix}_loop_off_sec",
        f"{prefix}_loop_hours",
        f"{prefix}_loop_minutes",
    ]
    for k in keys:
        if k not in st.session_state:
            st.session_state[k] = 0


def render_device(device: str, icon_label: str) -> None:
    """Renderiza controles y estado para un dispositivo."""
    ensure_session_defaults(device)
    st.markdown(f"## {icon_label}")

    # Reloj local
    st.markdown(
        f"<h3 style='text-align:center;'>{time.strftime('%H:%M:%S')}</h3>",
        unsafe_allow_html=True,
    )

    # --- Modo simple ---
    st.subheader("Disparo único (cuenta atrás)")
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.write("Minutos")
        if st.button("▲", key=f"{device}_min_up"):
            st.session_state[f"{device}_mins"] += 1
        if st.button("▼", key=f"{device}_min_down"):
            st.session_state[f"{device}_mins"] = max(0, st.session_state[f"{device}_mins"] - 1)

    with col2:
        st.write("Segundos")
        if st.button("▲", key=f"{device}_sec_up"):
            st.session_state[f"{device}_secs"] = (st.session_state[f"{device}_secs"] + 1) % 60
        if st.button("▼", key=f"{device}_sec_down"):
            st.session_state[f"{device}_secs"] = (st.session_state[f"{device}_secs"] - 1) % 60

    total_single = st.session_state[f"{device}_mins"] * 60 + st.session_state[f"{device}_secs"]
    st.markdown(
        f"<h4 style='text-align:center;'>Tiempo: "
        f"{st.session_state[f'{device}_mins']:02d}:{st.session_state[f'{device}_secs']:02d} "
        f"({total_single}s)</h4>",
        unsafe_allow_html=True,
    )

    with LOCK:
        busy = STATE[device]["mode"] != "idle"
    btn_single = st.button(
        "Iniciar cuenta atrás",
        key=f"{device}_single_start",
        disabled=(total_single <= 0 or busy),
    )
    if btn_single and total_single > 0 and not busy:
        threading.Thread(
            target=run_countdown, args=(device, total_single), daemon=True
        ).start()

    # --- Modo loop ---
    st.subheader("Loop encendido/apagado")
    l1, l2 = st.columns(2, gap="large")
    with l1:
        st.write("Encendido (cerrado)")
        if st.button("▲", key=f"{device}_on_min_up"):
            st.session_state[f"{device}_loop_on_min"] += 1
        if st.button("▼", key=f"{device}_on_min_down"):
            st.session_state[f"{device}_loop_on_min"] = max(
                0, st.session_state[f"{device}_loop_on_min"] - 1
            )
        if st.button("▲", key=f"{device}_on_sec_up"):
            st.session_state[f"{device}_loop_on_sec"] = (
                st.session_state[f"{device}_loop_on_sec"] + 1
            ) % 60
        if st.button("▼", key=f"{device}_on_sec_down"):
            st.session_state[f"{device}_loop_on_sec"] = (
                st.session_state[f"{device}_loop_on_sec"] - 1
            ) % 60
        st.markdown(
            f"<b>{st.session_state[f'{device}_loop_on_min']:02d}:"
            f"{st.session_state[f'{device}_loop_on_sec']:02d}</b>",
            unsafe_allow_html=True,
        )

    with l2:
        st.write("Apagado (abierto)")
        if st.button("▲", key=f"{device}_off_min_up"):
            st.session_state[f"{device}_loop_off_min"] += 1
        if st.button("▼", key=f"{device}_off_min_down"):
            st.session_state[f"{device}_loop_off_min"] = max(
                0, st.session_state[f"{device}_loop_off_min"] - 1
            )
        if st.button("▲", key=f"{device}_off_sec_up"):
            st.session_state[f"{device}_loop_off_sec"] = (
                st.session_state[f"{device}_loop_off_sec"] + 1
            ) % 60
        if st.button("▼", key=f"{device}_off_sec_down"):
            st.session_state[f"{device}_loop_off_sec"] = (
                st.session_state[f"{device}_loop_off_sec"] - 1
            ) % 60
        st.markdown(
            f"<b>{st.session_state[f'{device}_loop_off_min']:02d}:"
            f"{st.session_state[f'{device}_loop_off_sec']:02d}</b>",
            unsafe_allow_html=True,
        )

    t1, t2 = st.columns(2, gap="large")
    with t1:
        st.write("Duración total (horas)")
        if st.button("▲", key=f"{device}_loop_hours_up"):
            st.session_state[f"{device}_loop_hours"] += 1
        if st.button("▼", key=f"{device}_loop_hours_down"):
            st.session_state[f"{device}_loop_hours"] = max(
                0, st.session_state[f"{device}_loop_hours"] - 1
            )
        st.markdown(f"<b>{st.session_state[f'{device}_loop_hours']:02d}</b>", unsafe_allow_html=True)

    with t2:
        st.write("Duración total (minutos)")
        if st.button("▲", key=f"{device}_loop_minutes_up"):
            st.session_state[f"{device}_loop_minutes"] = (
                st.session_state[f"{device}_loop_minutes"] + 1
            ) % 60
        if st.button("▼", key=f"{device}_loop_minutes_down"):
            st.session_state[f"{device}_loop_minutes"] = (
                st.session_state[f"{device}_loop_minutes"] - 1
            ) % 60
        st.markdown(
            f"<b>{st.session_state[f'{device}_loop_minutes']:02d}</b>", unsafe_allow_html=True
        )

    loop_on_total = (
        st.session_state[f"{device}_loop_on_min"] * 60 + st.session_state[f"{device}_loop_on_sec"]
    )
    loop_off_total = (
        st.session_state[f"{device}_loop_off_min"] * 60
        + st.session_state[f"{device}_loop_off_sec"]
    )
    loop_total = (
        st.session_state[f"{device}_loop_hours"] * 3600
        + st.session_state[f"{device}_loop_minutes"] * 60
    )

    st.markdown(
        f"<h4 style='text-align:center;'>Loop ON {loop_on_total}s / OFF {loop_off_total}s "
        f"- Total {loop_total}s</h4>",
        unsafe_allow_html=True,
    )

    with LOCK:
        busy = STATE[device]["mode"] != "idle"
    btn_loop = st.button(
        "Iniciar loop",
        key=f"{device}_loop_start",
        disabled=(
            loop_on_total <= 0
            or loop_off_total <= 0
            or loop_total <= 0
            or busy
        ),
    )
    if btn_loop and not busy and loop_on_total > 0 and loop_off_total > 0 and loop_total > 0:
        threading.Thread(
            target=run_loop, args=(device, loop_on_total, loop_off_total, loop_total), daemon=True
        ).start()

    # --- Estado visual ---
    with LOCK:
        dev_state = STATE[device].copy()
    active = dev_state["mode"] != "idle"
    seconds_left = dev_state["seconds_left"]
    percent = 0 if dev_state["total"] == 0 else 100 * (1 - seconds_left / dev_state["total"])

    valve_closed = False
    if dev_state["mode"] == "single":
        valve_closed = True
    elif dev_state["mode"] == "loop":
        valve_closed = dev_state["phase"] == "on"

    bg = "#e7040f" if valve_closed else "#19a974"
    indicator = "Relé cerrado" if valve_closed else "Relé abierto"
    counter = f"{seconds_left}" if active else ""

    bar_html = f"""
    <div style="width:90vw;height:40px;background:#ddd;border-radius:8px;overflow:hidden;margin:10px auto;">
      <div style="height:100%;width:{percent:.0f}%;background:#ffeb3b;transition:width 0.2s linear;"></div>
    </div>
    """

    st.markdown(
        f"""
        <div style="background:{bg};color:white;padding:20px;text-align:center;border-radius:12px;">
          <div style="font-size:28px;margin-bottom:10px;">{indicator}</div>
          <div style="font-size:96px;margin:10px 0;">{counter}</div>
          {bar_html}
          <div style="font-size:18px;">Modo: {dev_state['mode']} {('('+dev_state['phase']+')') if dev_state['phase'] else ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- UI principal ---
st.set_page_config(page_title="Control de relés", layout="centered")

# Render para cada dispositivo
render_device("air", DEVICES["air"]["icon"])
st.markdown("---")
render_device("power", DEVICES["power"]["icon"])

# Auto-refresco ligero para que los contadores avancen sin interacción
st.experimental_autorefresh(interval=300, key="auto")

