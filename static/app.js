const cardsContainer = document.getElementById("cards");
const tmpl = document.getElementById("card-template");
const stopBtn = document.getElementById("stop-all");

const state = {};

function pad(v) { return v.toString(); }

function createCard(key, meta) {
  const node = tmpl.content.cloneNode(true);
  const card = node.querySelector(".card");
  const icon = card.querySelector(".icon");
  const label = card.querySelector(".label");
  icon.textContent = meta.icon;
  label.textContent = meta.label;

  // Inputs
  const minVal = card.querySelector(".min-val");
  const secVal = card.querySelector(".sec-val");
  const onMinVal = card.querySelector(".on-min-val");
  const onSecVal = card.querySelector(".on-sec-val");
  const offMinVal = card.querySelector(".off-min-val");
  const offSecVal = card.querySelector(".off-sec-val");
  const totalHourVal = card.querySelector(".total-hour-val");
  const totalMinVal = card.querySelector(".total-min-val");

  state[key] = {
    mins: 0,
    secs: 0,
    onMin: 0,
    onSec: 0,
    offMin: 0,
    offSec: 0,
    totHour: 0,
    totMin: 0,
    els: {
      indicator: card.querySelector(".indicator"),
      counter: card.querySelector(".counter"),
      fill: card.querySelector(".fill"),
      statusBox: card.querySelector(".status"),
      mode: card.querySelector(".mode"),
      startSingle: card.querySelector(".start-single"),
      startLoop: card.querySelector(".start-loop"),
    },
  };

  function renderInputs() {
    minVal.textContent = pad(state[key].mins);
    secVal.textContent = pad(state[key].secs);
    onMinVal.textContent = pad(state[key].onMin);
    onSecVal.textContent = pad(state[key].onSec);
    offMinVal.textContent = pad(state[key].offMin);
    offSecVal.textContent = pad(state[key].offSec);
    totalHourVal.textContent = pad(state[key].totHour);
    totalMinVal.textContent = pad(state[key].totMin);
  }
  renderInputs();

  const adj = (prop, delta, max = null) => {
    state[key][prop] = Math.max(0, state[key][prop] + delta);
    if (max !== null) state[key][prop] = state[key][prop] % (max + 1);
    renderInputs();
  };

  card.querySelector(".min-up").onclick = () => adj("mins", 1);
  card.querySelector(".min-down").onclick = () => adj("mins", -1);
  card.querySelector(".sec-up").onclick = () => adj("secs", 1, 59);
  card.querySelector(".sec-down").onclick = () => adj("secs", -1, 59);

  card.querySelector(".on-min-up").onclick = () => adj("onMin", 1);
  card.querySelector(".on-min-down").onclick = () => adj("onMin", -1);
  card.querySelector(".on-sec-up").onclick = () => adj("onSec", 1, 59);
  card.querySelector(".on-sec-down").onclick = () => adj("onSec", -1, 59);

  card.querySelector(".off-min-up").onclick = () => adj("offMin", 1);
  card.querySelector(".off-min-down").onclick = () => adj("offMin", -1);
  card.querySelector(".off-sec-up").onclick = () => adj("offSec", 1, 59);
  card.querySelector(".off-sec-down").onclick = () => adj("offSec", -1, 59);

  card.querySelector(".total-hour-up").onclick = () => adj("totHour", 1);
  card.querySelector(".total-hour-down").onclick = () => adj("totHour", -1);
  card.querySelector(".total-min-up").onclick = () => adj("totMin", 1, 59);
  card.querySelector(".total-min-down").onclick = () => adj("totMin", -1, 59);

  // Start single
  card.querySelector(".start-single").onclick = async () => {
    const total = state[key].mins * 60 + state[key].secs;
    if (total <= 0) return;
    await fetch("/api/single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device: key, seconds: total }),
    });
  };

  // Start loop
  card.querySelector(".start-loop").onclick = async () => {
    const onS = state[key].onMin * 60 + state[key].onSec;
    const offS = state[key].offMin * 60 + state[key].offSec;
    const totS = state[key].totHour * 3600 + state[key].totMin * 60;
    if (onS <= 0 || offS <= 0 || totS <= 0) return;
    await fetch("/api/loop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device: key, on_seconds: onS, off_seconds: offS, total_seconds: totS }),
    });
  };

  cardsContainer.appendChild(card);
}

Object.entries(DEVICES).forEach(([k, v]) => createCard(k, v));

stopBtn.onclick = async () => {
  try {
    await fetch("/api/stop", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
};

function renderClock() {
  const el = document.getElementById("clock");
  const now = new Date();
  el.textContent = now.toLocaleTimeString();
}
setInterval(renderClock, 1000);
renderClock();

async function poll() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    for (const [key, st] of Object.entries(data)) {
      const s = state[key];
      if (!s) continue;
      const { indicator, counter, fill, statusBox, mode, startSingle, startLoop } = s.els;
      const active = st.mode !== "idle";
      const pending = st.mode === "pending_loop";
      const closed = (!pending) && (st.mode === "single" || (st.mode === "loop" && st.phase === "on"));

      statusBox.classList.toggle("on", closed);
      statusBox.classList.toggle("off", !closed);
      statusBox.classList.toggle("pending", pending);
      const phaseLeft = st.phase_left || 0;
      indicator.textContent = pending
        ? `Preparando loop (${phaseLeft}s)`
        : closed
          ? `Relé cerrado (${phaseLeft}s fase)`
          : `Relé abierto (${phaseLeft}s fase)`;

      counter.textContent = active ? st.seconds_left : "";
      fill.style.width = `${st.percent || 0}%`;
      mode.textContent = active
        ? `Modo: ${st.mode}${st.phase ? " (" + st.phase + ")" : ""}`
        : "Modo: inactivo";

      startSingle.disabled = active;
      startLoop.disabled = active;
    }
  } catch (e) {
    console.error(e);
  }
}

setInterval(poll, 300);
poll();

