<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bilderrahmen Steuerung</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=IBM+Plex+Sans:wght@300;400&display=swap" rel="stylesheet">
<style>
/* ── Reset & Basis ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #0e0e10;
  --surface:   #16161a;
  --border:    #2a2a32;
  --gold:      #c8a96e;
  --gold-dim:  rgba(200,169,110,0.15);
  --green:     #4ade80;
  --red:       #f87171;
  --amber:     #fbbf24;
  --text:      #e8e3d8;
  --muted:     #6b6860;
  --mono:      'IBM Plex Mono', monospace;
  --sans:      'IBM Plex Sans', sans-serif;
}

html, body {
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-weight: 300;
}

/* ── Layout ────────────────────────────────────────────────── */
.seite {
  max-width: 680px;
  margin: 0 auto;
  padding: 48px 24px 80px;
}

/* ── Kopfzeile ─────────────────────────────────────────────── */
.kopf {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 20px;
  margin-bottom: 40px;
}
.kopf-titel {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--gold);
}
.kopf-zeit {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.08em;
}

/* ── Abschnitt ─────────────────────────────────────────────── */
.abschnitt {
  margin-bottom: 36px;
}
.abschnitt-label {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 12px;
}

/* ── Live-Status Karten ────────────────────────────────────── */
.status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.status-karte {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.4s;
}
.status-karte.aktiv {
  border-color: var(--green);
}
.status-karte.aktiv::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(74,222,128,0.04);
  pointer-events: none;
}
.status-karte-icon {
  font-size: 22px;
  margin-bottom: 10px;
  display: block;
}
.status-karte-name {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 6px;
}
.status-karte-wert {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
}
.indikator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted);
  flex-shrink: 0;
  transition: background 0.3s, box-shadow 0.3s;
}
.indikator.aktiv {
  background: var(--green);
  box-shadow: 0 0 0 3px rgba(74,222,128,0.2);
  animation: puls 1.5s ease-in-out infinite;
}
.indikator.inaktiv {
  background: var(--red);
}
@keyframes puls {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

/* Monitor-Status (volle Breite) */
.status-monitor {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: border-color 0.4s;
}
.status-monitor.an {
  border-color: rgba(200,169,110,0.4);
}
.status-monitor-label {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  color: var(--muted);
}
.status-monitor-wert {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Lautstärke-Balken */
.mic-pegel-wrap {
  margin-top: 8px;
  height: 2px;
  background: var(--border);
  border-radius: 1px;
  overflow: hidden;
}
.mic-pegel-balken {
  height: 100%;
  width: 0%;
  background: var(--green);
  border-radius: 1px;
  transition: width 0.15s ease-out, background 0.2s;
}
.mic-pegel-balken.laut {
  background: var(--amber);
}
.mic-pegel-balken.sehr-laut {
  background: var(--red);
}

/* System-Bereit Banner */
.system-banner {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--muted);
  border-radius: 4px;
  padding: 12px 16px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--muted);
  margin-bottom: 12px;
  transition: border-left-color 0.4s, color 0.4s;
}
.system-banner.bereit {
  border-left-color: var(--green);
  color: var(--green);
}
.system-banner.aufwaermen {
  border-left-color: var(--amber);
  color: var(--amber);
}

/* Letzte Aktualisierung */
.letztes-update {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--muted);
  text-align: right;
  margin-top: 8px;
  letter-spacing: 0.1em;
}

/* ── Steuerung Formular ─────────────────────────────────────── */
.formular {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Monitor-Buttons */
.monitor-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.btn {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 14px 20px;
  cursor: pointer;
  transition: all 0.2s;
  background: transparent;
  color: var(--text);
}
.btn:hover {
  border-color: var(--gold);
  color: var(--gold);
  background: var(--gold-dim);
}
.btn-an {
  border-color: rgba(74,222,128,0.3);
  color: var(--green);
}
.btn-an:hover {
  border-color: var(--green);
  background: rgba(74,222,128,0.08);
  color: var(--green);
}
.btn-aus {
  border-color: rgba(248,113,113,0.3);
  color: var(--red);
}
.btn-aus:hover {
  border-color: var(--red);
  background: rgba(248,113,113,0.08);
  color: var(--red);
}

/* Eingabefelder */
.feld-gruppe {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.feld-label {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: var(--muted);
}
.feld-zeile {
  display: flex;
  align-items: center;
  gap: 12px;
}
.feld-input {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  padding: 10px 14px;
  width: 120px;
  transition: border-color 0.2s;
  appearance: none;
  -webkit-appearance: none;
}
.feld-input:focus {
  outline: none;
  border-color: var(--gold);
}
.feld-einheit {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.15em;
}
.feld-hinweis {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
}

/* Slider für Mikrofon-Schwellwert */
.slider-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.slider {
  -webkit-appearance: none;
  width: 100%;
  height: 2px;
  border-radius: 1px;
  background: var(--border);
  outline: none;
  cursor: pointer;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--gold);
  cursor: pointer;
  border: none;
  transition: transform 0.15s;
}
.slider::-webkit-slider-thumb:hover {
  transform: scale(1.3);
}
.slider-werte {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 9px;
  color: var(--muted);
}

/* Speichern-Button */
.btn-speichern {
  background: var(--gold-dim);
  border: 1px solid rgba(200,169,110,0.4);
  color: var(--gold);
  padding: 14px;
  font-size: 10px;
  letter-spacing: 0.25em;
  border-radius: 3px;
  cursor: pointer;
  font-family: var(--mono);
  font-weight: 500;
  text-transform: uppercase;
  transition: all 0.2s;
  width: 100%;
}
.btn-speichern:hover {
  background: rgba(200,169,110,0.25);
  border-color: var(--gold);
}

/* Trennlinie */
hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}

/* Erfolgs-Meldung */
.meldung {
  display: none;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--green);
  text-align: center;
  padding: 10px;
}
.meldung.sichtbar { display: block; }
</style>
</head>
<body>

<div class="seite">

  <!-- ── Kopfzeile ────────────────────────────────────────── -->
  <div class="kopf">
    <span class="kopf-titel">Bilderrahmen // Steuerung</span>
    <span class="kopf-zeit" id="kopf-zeit">--:--</span>
  </div>

  <!-- ══════════════════════════════════════════════════════ -->
  <!-- ABSCHNITT 1: LIVE-STATUS                              -->
  <!-- ══════════════════════════════════════════════════════ -->
  <div class="abschnitt">
    <div class="abschnitt-label">Live-Status</div>

    <!-- System-Bereit Banner -->
    <div class="system-banner aufwaermen" id="system-banner">
      ○ &nbsp; SYSTEM INITIALISIERT...
    </div>

    <!-- PIR + Mikrofon Karten -->
    <div class="status-grid">

      <!-- PIR -->
      <div class="status-karte" id="karte-pir">
        <span class="status-karte-icon">👁</span>
        <div class="status-karte-name">PIR Bewegungssensor</div>
        <div class="status-karte-wert">
          <span class="indikator" id="dot-pir"></span>
          <span id="text-pir">Warte...</span>
        </div>
      </div>

      <!-- Mikrofon -->
      <div class="status-karte" id="karte-mic">
        <span class="status-karte-icon">🎙</span>
        <div class="status-karte-name">Mikrofon</div>
        <div class="status-karte-wert">
          <span class="indikator" id="dot-mic"></span>
          <span id="text-mic">Warte...</span>
        </div>
        <div class="mic-pegel-wrap">
          <div class="mic-pegel-balken" id="mic-pegel"></div>
        </div>
      </div>

    </div>

    <!-- Monitor-Status -->
    <div class="status-monitor" id="status-monitor">
      <span class="status-monitor-label">Monitor</span>
      <div class="status-monitor-wert">
        <span class="indikator" id="dot-monitor"></span>
        <span id="text-monitor">—</span>
      </div>
    </div>

    <div class="letztes-update" id="letztes-update">Zuletzt: —</div>
  </div>

  <hr>
  <br>

  <!-- ══════════════════════════════════════════════════════ -->
  <!-- ABSCHNITT 2: STEUERUNG                                -->
  <!-- ══════════════════════════════════════════════════════ -->
  <div class="abschnitt">
    <div class="abschnitt-label">Steuerung</div>

    <form class="formular" action="save.php" method="POST" id="steuer-form">

      <!-- Monitor AN/AUS (sofort, ohne Speichern) -->
      <div class="feld-gruppe">
        <div class="feld-label">Monitor</div>
        <div class="monitor-buttons">
          <button type="submit" name="monitor" value="on"  class="btn btn-an">
            ▶ &nbsp; AN
          </button>
          <button type="submit" name="monitor" value="off" class="btn btn-aus">
            ◼ &nbsp; AUS
          </button>
        </div>
      </div>

      <!-- Verstecktes Feld damit Monitor-Wert erhalten bleibt beim Speichern -->
      <input type="hidden" name="monitor" value="on" id="monitor-hidden">

      <!-- Timeout -->
      <div class="feld-gruppe">
        <div class="feld-label">Timeout — Inaktivität</div>
        <div class="feld-zeile">
          <input class="feld-input"
                 type="number"
                 name="timeout"
                 id="timeout-input"
                 value="30"
                 min="5"
                 max="3600">
          <span class="feld-einheit">Sekunden</span>
        </div>
        <div class="feld-hinweis">
          Nach dieser Zeit ohne Bewegung oder Geräusch geht der Monitor aus.
        </div>
      </div>

      <!-- Mikrofon-Schwellwert -->
      <div class="feld-gruppe">
        <div class="feld-label">Mikrofon-Empfindlichkeit</div>
        <div class="slider-wrap">
          <input class="slider"
                 type="range"
                 name="mic_schwellwert"
                 id="mic-slider"
                 min="100"
                 max="5000"
                 step="50"
                 value="500">
          <div class="slider-werte">
            <span>Sehr empfindlich (100)</span>
            <span id="slider-anzeige">Schwellwert: 500</span>
            <span>Grob (5000)</span>
          </div>
        </div>
        <div class="feld-hinweis">
          Niedrig = reagiert auf leise Geräusche. Hoch = nur bei lauten Geräuschen.
          Empfohlen: 300–800.
        </div>
      </div>

      <!-- Speichern -->
      <button type="button" class="btn-speichern" id="btn-speichern">
        Einstellungen speichern
      </button>

      <div class="meldung" id="meldung">✓ &nbsp; Gespeichert</div>

    </form>
  </div>

</div><!-- /seite -->

<script>
// ── Uhr ───────────────────────────────────────────────────────
function uhrzeitAktualisieren() {
  const n = new Date();
  const h = String(n.getHours()).padStart(2,'0');
  const m = String(n.getMinutes()).padStart(2,'0');
  const s = String(n.getSeconds()).padStart(2,'0');
  document.getElementById('kopf-zeit').textContent = `${h}:${m}:${s}`;
}
uhrzeitAktualisieren();
setInterval(uhrzeitAktualisieren, 1000);

// ── Slider Live-Anzeige ────────────────────────────────────────
const slider     = document.getElementById('mic-slider');
const sliderAnz  = document.getElementById('slider-anzeige');

slider.addEventListener('input', () => {
  sliderAnz.textContent = `Schwellwert: ${slider.value}`;
});

// ── Monitor-Buttons: hidden field synchronisieren ─────────────
document.querySelectorAll('.btn-an, .btn-aus').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('monitor-hidden').value = btn.value;
  });
});

// ── Speichern per AJAX ─────────────────────────────────────────
document.getElementById('btn-speichern').addEventListener('click', async () => {
  const form   = document.getElementById('steuer-form');
  const daten  = new FormData(form);

  try {
    await fetch('save.php', { method: 'POST', body: daten });
    const meld = document.getElementById('meldung');
    meld.classList.add('sichtbar');
    setTimeout(() => meld.classList.remove('sichtbar'), 2500);
  } catch(e) {
    alert('Fehler beim Speichern: ' + e);
  }
});

// ── Live-Status Polling ────────────────────────────────────────
let letzterSchwellwert = 500;

async function statusAktualisieren() {
  try {
    const res  = await fetch('status_api.php?t=' + Date.now());
    const data = await res.json();

    // System-Bereit Banner
    const banner = document.getElementById('system-banner');
    if (data.system_bereit) {
      banner.className = 'system-banner bereit';
      banner.textContent = '● \u00a0 SYSTEM BEREIT';
    } else {
      banner.className = 'system-banner aufwaermen';
      banner.textContent = '○ \u00a0 SENSOR KALIBRIERT SICH...';
    }

    // PIR
    const kartePir = document.getElementById('karte-pir');
    const dotPir   = document.getElementById('dot-pir');
    const textPir  = document.getElementById('text-pir');
    if (data.pir_aktiv) {
      kartePir.classList.add('aktiv');
      dotPir.className = 'indikator aktiv';
      textPir.textContent = 'Bewegung erkannt';
    } else {
      kartePir.classList.remove('aktiv');
      dotPir.className = 'indikator inaktiv';
      textPir.textContent = 'Keine Bewegung';
    }

    // Mikrofon
    const karteMic = document.getElementById('karte-mic');
    const dotMic   = document.getElementById('dot-mic');
    const textMic  = document.getElementById('text-mic');
    if (data.mikrofon_aktiv) {
      karteMic.classList.add('aktiv');
      dotMic.className = 'indikator aktiv';
      textMic.textContent = 'Geräusch erkannt';
    } else {
      karteMic.classList.remove('aktiv');
      dotMic.className = 'indikator inaktiv';
      textMic.textContent = 'Stille';
    }

    // Mikrofon-Pegel simulieren (aktiv → 60-90%, inaktiv → 5-15%)
    const pegel    = document.getElementById('mic-pegel');
    const pegelPct = data.mikrofon_aktiv
      ? 60 + Math.random() * 30
      : 3  + Math.random() * 12;
    pegel.style.width = pegelPct + '%';
    pegel.className = 'mic-pegel-balken'
      + (pegelPct > 80 ? ' sehr-laut' : pegelPct > 60 ? ' laut' : '');

    // Monitor
    const statusMonitor = document.getElementById('status-monitor');
    const dotMonitor    = document.getElementById('dot-monitor');
    const textMonitor   = document.getElementById('text-monitor');
    if (data.monitor_an) {
      statusMonitor.classList.add('an');
      dotMonitor.className = 'indikator aktiv';
      dotMonitor.style.background = 'var(--gold)';
      dotMonitor.style.boxShadow  = '0 0 0 3px rgba(200,169,110,0.2)';
      dotMonitor.style.animation  = 'none';
      textMonitor.textContent = 'AN';
    } else {
      statusMonitor.classList.remove('an');
      dotMonitor.className = 'indikator inaktiv';
      dotMonitor.style.background = '';
      dotMonitor.style.boxShadow  = '';
      dotMonitor.style.animation  = '';
      textMonitor.textContent = 'AUS — Schlafmodus';
    }

    // Timeout-Eingabe und Slider synchronisieren (wenn sich geändert)
    const timeoutInput = document.getElementById('timeout-input');
    if (document.activeElement !== timeoutInput) {
      timeoutInput.value = data.timeout_sek;
    }

    if (data.mic_schwellwert && data.mic_schwellwert !== letzterSchwellwert) {
      letzterSchwellwert = data.mic_schwellwert;
      if (document.activeElement !== slider) {
        slider.value = data.mic_schwellwert;
        sliderAnz.textContent = `Schwellwert: ${data.mic_schwellwert}`;
      }
    }

    // Zeitstempel
    document.getElementById('letztes-update').textContent =
      `Zuletzt: ${data.zeitstempel}`;

  } catch(e) {
    document.getElementById('letztes-update').textContent =
      'Verbindungsfehler — Python-Server läuft?';
  }
}

statusAktualisieren();
setInterval(statusAktualisieren, 2000);
</script>
</body>
</html>
