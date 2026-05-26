"""
╔══════════════════════════════════════════════════════════════╗
║           Digitaler Bilderrahmen — Hauptprogramm             ║
║                                                              ║
║  Funktionen:                                                 ║
║  • PIR Motion Sensor erkennt Bewegung (GPIO 4)               ║
║  • Mikrofon erkennt Geräusche (sounddevice)                  ║
║  • ODER-Logik: Bewegung ODER Geräusch → Monitor an           ║
║  • Aufwärmzeit beim Start (Sensor kalibriert sich)           ║
║  • Monitor geht nach X Sekunden ohne Aktivität aus           ║
║  • Slideshow pausiert im Schlafmodus                         ║
║  • Alle Logik läuft in Hintergrund-Threads                   ║
║  • Google Drive-Sync via rclone (alle 5 Minuten)             ║
║  • Chromium-Fenster zeigt die Slideshow (Vollbild möglich)   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
import threading
import subprocess
import logging
import json
import numpy as np
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from gpiozero import MotionSensor

# sounddevice für Mikrofon
try:
    import sounddevice as sd
    MIKROFON_VERFUEGBAR = True
except ImportError:
    MIKROFON_VERFUEGBAR = False
    print("WARNUNG: sounddevice nicht installiert → pip install sounddevice numpy")

# ──────────────────────────────────────────────────────────────
#  KONFIGURATION — hier anpassen
# ──────────────────────────────────────────────────────────────

GPIO_PIN        = 4      # GPIO-Pin wo OUT des PIR-Sensors angeschlossen ist
WARMUP_SEC      = 30     # Sekunden Aufwärmzeit (Sensor kalibriert sich)
TIMEOUT_SEC     = 30     # Sekunden ohne Aktivität bis Monitor ausgeht
CONFIRM_COUNT   = 3      # Wie viele Messungen positiv sein müssen (Anti-Falschalarm)
CHECK_INTERVAL  = 0.1    # Sekunden zwischen Sensor-Abfragen (0.1 = 10x pro Sekunde)

# Mikrofon-Einstellungen
MIC_SCHWELLWERT      = 500    # RMS-Lautstärke ab der Aktivität erkannt wird (0–32767)
MIC_SAMPLERATE       = 16000  # Hz — 16000 reicht für Lautstärke-Erkennung
MIC_BLOCKSIZE        = 1024   # Samples pro Block (~64ms bei 16kHz)
MIC_DEVICE           = None   # None = Standard-Gerät, oder Geräte-Index z.B. 1

# Google Drive — Ordnernamen anpassen nach: rclone lsd onedrive:
GDRIVE_REMOTE   = "gdrive:Bilder"
LOCAL_IMAGE_DIR = "/home/admin/Digitaler-Bilderrahmen/bilder"

# Log-Dateien
LOG_DATEI         = "/home/admin/Digitaler-Bilderrahmen/bilderrahmen.log"
ÄNDERUNGEN_LOG    = "/home/admin/Digitaler-Bilderrahmen/änderungen.log"
SYNC_INTERVAL     = 60

# Webserver & Chromium
WEB_DIR   = "/home/admin/Digitaler-Bilderrahmen"
WEB_PORT  = 8080
VOLLBILD  = False

# ──────────────────────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(threadName)-10s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DATEI)
    ]
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  GLOBALER ZUSTAND
# ──────────────────────────────────────────────────────────────

state_lock        = threading.Lock()
screen_on         = True
last_motion_time  = datetime.now()
motion_active     = False   # PIR aktiv
sound_active      = False   # Mikrofon aktiv
system_ready      = False
browser_proc      = None

status_datei  = os.path.join(WEB_DIR, "status.txt")
CONTROL_FILE  = os.path.join(WEB_DIR, "data/control.json")
SENSOR_STATUS = os.path.join(WEB_DIR, "data/sensor_status.json")

# ──────────────────────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ──────────────────────────────────────────────────────────────

def status_setzen(status: str):
    """Schreibt den aktuellen Status in status.txt (für index.html)."""
    try:
        with open(status_datei, "w") as f:
            f.write(status)
        log.info(f"Status → {status}")
    except Exception as e:
        log.warning(f"Status-Datei Fehler: {e}")


def sensor_status_schreiben():
    """
    Schreibt PIR- und Mikrofon-Status in data/sensor_status.json.
    Das PHP-Panel liest diese Datei für den Live-Status.
    """
    try:
        daten = {
            "zeitstempel":    datetime.now().strftime("%H:%M:%S"),
            "pir_aktiv":      motion_active,
            "mikrofon_aktiv": sound_active,
            "monitor_an":     screen_on,
            "system_bereit":  system_ready,
            "mic_schwellwert": MIC_SCHWELLWERT,
            "timeout_sek":    TIMEOUT_SEC,
        }
        os.makedirs(os.path.dirname(SENSOR_STATUS), exist_ok=True)
        with open(SENSOR_STATUS, "w") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Sensor-Status Fehler: {e}")


def aktivitaet_melden(quelle: str):
    """
    Wird von PIR-Thread UND Mikrofon-Thread aufgerufen.
    ODER-Logik: Egal welche Quelle → Monitor an, Timeout zurücksetzen.
    """
    global last_motion_time

    with state_lock:
        last_motion_time = datetime.now()

    status_setzen("active")
    monitor_an()

    sensor_status_schreiben()
    log.info(f"Aktivität erkannt [{quelle}] 👤🔊")


def lade_control():
    """Liest control.json und übernimmt Einstellungen."""
    global TIMEOUT_SEC, MIC_SCHWELLWERT

    try:
        with open(CONTROL_FILE, "r") as f:
            data = json.load(f)

        TIMEOUT_SEC     = data.get("timeout", 30)
        MIC_SCHWELLWERT = data.get("mic_schwellwert", 500)

        monitor_status = data.get("monitor", "on")
        if monitor_status == "off":
            monitor_aus()
        elif monitor_status == "on":
            monitor_an()

        log.info(f"Control geladen: {data}")

    except Exception as e:
        log.warning(f"Control Fehler: {e}")


def änderungen_loggen(neu: set, geloescht: set):
    """Schreibt Bild-Änderungen in eine separate Log-Datei."""
    if not neu and not geloescht:
        return

    zeitstempel = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(ÄNDERUNGEN_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'─' * 50}\n")
            f.write(f"  Zeitpunkt: {zeitstempel}\n")
            f.write(f"{'─' * 50}\n")
            if neu:
                for bild in sorted(neu):
                    f.write(f"  ✚ HINZUGEFÜGT:  {bild}\n")
            if geloescht:
                for bild in sorted(geloescht):
                    f.write(f"  ✖ ENTFERNT:     {bild}\n")

        log.info(f"Änderungen in Log geschrieben → {ÄNDERUNGEN_LOG}")
    except Exception as e:
        log.warning(f"Änderungs-Log Fehler: {e}")


# ──────────────────────────────────────────────────────────────
#  MONITOR & BROWSER STEUERUNG
# ──────────────────────────────────────────────────────────────

def monitor_an():
    """Monitor einschalten und Slideshow fortsetzen."""
    global screen_on

    with state_lock:
        bereits_an = screen_on

    if bereits_an:
        return

    log.info("▶  Monitor AN")
    os.system("vcgencmd display_power 1")
    status_setzen("active")

    with state_lock:
        screen_on = True

    sensor_status_schreiben()


def monitor_aus():
    """Monitor ausschalten und Slideshow pausieren."""
    global screen_on

    with state_lock:
        bereits_aus = not screen_on

    if bereits_aus:
        return

    log.info("◼  Monitor AUS — Schlafmodus")
    status_setzen("sleeping")
    time.sleep(1.5)
    os.system("vcgencmd display_power 0")

    with state_lock:
        screen_on = False

    sensor_status_schreiben()


def browser_starten():
    """Chromium-Fenster mit der Slideshow öffnen."""
    global browser_proc

    time.sleep(2)
    url = f"http://localhost:{WEB_PORT}"

    chromium_cmd = [
        "chromium-browser",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
        "--autoplay-policy=no-user-gesture-required",
        url
    ]

    if VOLLBILD:
        chromium_cmd += ["--kiosk", "--start-fullscreen"]
    else:
        chromium_cmd += ["--start-maximized"]

    try:
        browser_proc = subprocess.Popen(
            chromium_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        modus = "Vollbild" if VOLLBILD else "Fenster (maximiert)"
        log.info(f"Chromium gestartet — Modus: {modus}")
        log.info(f"Slideshow erreichbar unter: {url}")
    except FileNotFoundError:
        log.error("Chromium nicht gefunden! → sudo apt install chromium-browser")


def browser_stoppen():
    """Chromium-Fenster schließen."""
    global browser_proc
    if browser_proc and browser_proc.poll() is None:
        browser_proc.terminate()
        try:
            browser_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            browser_proc.kill()
        log.info("Chromium geschlossen")
    browser_proc = None


# ──────────────────────────────────────────────────────────────
#  THREAD 1: WEBSERVER
# ──────────────────────────────────────────────────────────────

def webserver_thread():
    os.chdir(WEB_DIR)

    class LeiserHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = HTTPServer(("", WEB_PORT), LeiserHandler)
    log.info(f"Webserver läuft auf http://localhost:{WEB_PORT}")
    server.serve_forever()


# ──────────────────────────────────────────────────────────────
#  THREAD 2: PIR-SENSOR
# ──────────────────────────────────────────────────────────────

def pir_thread():
    global motion_active, system_ready

    log.info(f"PIR-Sensor wird initialisiert (GPIO {GPIO_PIN})...")

    try:
        pir = MotionSensor(pin=GPIO_PIN, sample_rate=10, threshold=0.5)
    except Exception as e:
        log.error(f"PIR-Sensor Fehler: {e}")
        log.error("Prüfe: Ist das OUT-Kabel wirklich an GPIO 4 angeschlossen?")
        return

    # ── Aufwärmphase ──────────────────────────────────────────
    log.info(f"Aufwärmphase: {WARMUP_SEC} Sekunden...")
    status_setzen("warming_up")

    for verbleibend in range(WARMUP_SEC, 0, -5):
        log.info(f"  Sensor bereit in {verbleibend}s ...")
        time.sleep(5)

    log.info("Sensor kalibriert und bereit ✓")
    status_setzen("active")
    system_ready = True

    # ── Bewegungserkennung ────────────────────────────────────
    counter = 0

    while True:
        if pir.motion_detected:
            counter += 1

            if counter >= CONFIRM_COUNT:
                war_inaktiv = not motion_active

                with state_lock:
                    motion_active = True

                if war_inaktiv:
                    aktivitaet_melden("PIR")

        else:
            if motion_active:
                log.info("PIR: Keine Bewegung mehr.")

            counter = 0

            with state_lock:
                motion_active = False

            sensor_status_schreiben()

        time.sleep(CHECK_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  THREAD 3: MIKROFON
#  Misst kontinuierlich den RMS-Lautstärkepegel.
#  Überschreitet er MIC_SCHWELLWERT → aktivitaet_melden()
# ──────────────────────────────────────────────────────────────

def mikrofon_thread():
    global sound_active

    if not MIKROFON_VERFUEGBAR:
        log.error("Mikrofon-Thread: sounddevice nicht verfügbar, Thread beendet.")
        return

    log.info(f"Mikrofon-Thread gestartet (Schwellwert: {MIC_SCHWELLWERT})")

    # Warten bis System bereit
    while not system_ready:
        time.sleep(0.5)

    def audio_callback(indata, frames, time_info, status):
        """Wird von sounddevice für jeden Audio-Block aufgerufen."""
        global sound_active

        if status:
            log.warning(f"Audio-Status: {status}")

        # RMS-Lautstärke berechnen (0–32767 bei int16)
        rms = int(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))

        if rms > MIC_SCHWELLWERT:
            war_inaktiv = not sound_active
            sound_active = True

            if war_inaktiv:
                log.info(f"🔊 Geräusch erkannt (RMS: {rms} > {MIC_SCHWELLWERT})")
                aktivitaet_melden("Mikrofon")

            sensor_status_schreiben()

        else:
            if sound_active:
                log.info(f"Mikrofon: Stille (RMS: {rms})")
                sound_active = False
                sensor_status_schreiben()

    try:
        log.info(f"Mikrofon wird geöffnet (Gerät: {MIC_DEVICE or 'Standard'}, "
                 f"{MIC_SAMPLERATE} Hz, Blockgröße: {MIC_BLOCKSIZE})")

        with sd.InputStream(
            device=MIC_DEVICE,
            channels=1,
            samplerate=MIC_SAMPLERATE,
            blocksize=MIC_BLOCKSIZE,
            dtype='int16',
            callback=audio_callback
        ):
            log.info("Mikrofon aktiv ✓ — Lausche auf Geräusche...")
            # Thread läuft so lange wie das Programm
            while True:
                time.sleep(1)

    except sd.PortAudioError as e:
        log.error(f"Mikrofon Fehler: {e}")
        log.error("Prüfe: Ist ein Mikrofon angeschlossen? → python3 -c \"import sounddevice; print(sounddevice.query_devices())\"")
    except Exception as e:
        log.error(f"Unerwarteter Mikrofon-Fehler: {e}")


# ──────────────────────────────────────────────────────────────
#  THREAD 4: TIMEOUT-WÄCHTER
#  Kein PIR UND kein Mikrofon → nach TIMEOUT_SEC Monitor aus.
# ──────────────────────────────────────────────────────────────

def timeout_thread():
    letzte_warnung = -1

    while True:
        if not system_ready:
            time.sleep(1)
            continue

        with state_lock:
            lmt  = last_motion_time
            s_on = screen_on

        inaktiv_seit = datetime.now() - lmt
        inaktiv_sek  = int(inaktiv_seit.total_seconds())

        if inaktiv_seit > timedelta(seconds=TIMEOUT_SEC):
            if s_on:
                log.info(f"Keine Aktivität seit {TIMEOUT_SEC}s → Monitor aus.")
                # Status auf no_motion setzen damit Frontend den Countdown sieht
                status_setzen("no_motion")
                monitor_aus()

        elif s_on:
            verbleibend = TIMEOUT_SEC - inaktiv_sek
            if verbleibend % 10 == 0 and verbleibend != letzte_warnung and 0 < verbleibend < TIMEOUT_SEC:
                log.info(f"Keine Aktivität — Monitor aus in {verbleibend}s")
                letzte_warnung = verbleibend

        time.sleep(1)


# ──────────────────────────────────────────────────────────────
#  THREAD 5: GOOGLE DRIVE-SYNC
# ──────────────────────────────────────────────────────────────

def bilder_liste():
    """Gibt ein Set mit allen lokalen Bilddateinamen zurück."""
    if not os.path.isdir(LOCAL_IMAGE_DIR):
        return set()
    return set(
        f for f in os.listdir(LOCAL_IMAGE_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
    )


def gdrive_thread():
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

    while True:
        log.info("Google Drive-Sync wird gestartet...")
        bilder_vorher = bilder_liste()

        try:
            result = subprocess.run(
                [
                    "rclone", "sync",
                    GDRIVE_REMOTE,
                    LOCAL_IMAGE_DIR,
                    "--include", "*.jpg",
                    "--include", "*.jpeg",
                    "--include", "*.png",
                    "--include", "*.JPG",
                    "--include", "*.PNG",
                    "--include", "*.JPEG",
                    "--transfers", "2",
                    "--low-level-retries", "3",
                    "--delete-during",
                ],
                capture_output=True,
                text=True,
                timeout=180
            )

            if result.returncode == 0:
                bilder_nachher = bilder_liste()
                neu       = bilder_nachher - bilder_vorher
                geloescht = bilder_vorher  - bilder_nachher

                if neu:
                    log.info(f"  ✚ Neu hinzugefügt ({len(neu)}): {', '.join(sorted(neu))}")
                if geloescht:
                    log.info(f"  ✖ Entfernt ({len(geloescht)}): {', '.join(sorted(geloescht))}")
                if not neu and not geloescht:
                    log.info(f"  ↔ Keine Änderungen")

                änderungen_loggen(neu, geloescht)
                log.info(f"Google Drive-Sync abgeschlossen ✓  ({len(bilder_nachher)} Bilder lokal)")

            else:
                log.warning(f"rclone Fehler: {result.stderr.strip()}")

        except FileNotFoundError:
            log.error("rclone nicht gefunden! → sudo apt install rclone")
        except subprocess.TimeoutExpired:
            log.warning("Sync Timeout — nächster Versuch in 5 Min.")
        except Exception as e:
            log.error(f"Sync-Fehler: {e}")

        log.info(f"Nächster Sync in {SYNC_INTERVAL} Sekunden.")
        time.sleep(SYNC_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  THREAD 6: CONTROL-DATEI POLLING
# ──────────────────────────────────────────────────────────────

def control_thread():
    while True:
        lade_control()
        time.sleep(2)


# ──────────────────────────────────────────────────────────────
#  HAUPTPROGRAMM
# ──────────────────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("   Digitaler Bilderrahmen — Start")
    log.info(f"   GPIO Pin:         {GPIO_PIN}")
    log.info(f"   Aufwärmzeit:      {WARMUP_SEC}s")
    log.info(f"   Timeout:          {TIMEOUT_SEC}s")
    log.info(f"   Mikrofon:         {'verfügbar ✓' if MIKROFON_VERFUEGBAR else 'NICHT verfügbar ✗'}")
    log.info(f"   Mic-Schwellwert:  {MIC_SCHWELLWERT}")
    log.info(f"   Google Drive:     {GDRIVE_REMOTE}")
    log.info(f"   Vollbild:         {VOLLBILD}")
    log.info("=" * 55)

    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)
    os.makedirs(os.path.join(WEB_DIR, "data"), exist_ok=True)

    status_setzen("warming_up")
    sensor_status_schreiben()

    threads = [
        threading.Thread(target=webserver_thread, name="Webserver",  daemon=True),
        threading.Thread(target=pir_thread,       name="PIR-Sensor", daemon=True),
        threading.Thread(target=mikrofon_thread,  name="Mikrofon",   daemon=True),
        threading.Thread(target=timeout_thread,   name="Timeout",    daemon=True),
        threading.Thread(target=gdrive_thread,    name="GDrive",     daemon=True),
        threading.Thread(target=control_thread,   name="Control",    daemon=True),
    ]

    for t in threads:
        t.start()
        log.info(f"Thread gestartet: {t.name}")

    log.info("Chromium-Fenster wird geöffnet...")
    browser_starten()

    log.info("Warte auf Aufwärmphase des Sensors...")
    while not system_ready:
        time.sleep(1)

    log.info("System bereit! Bilderrahmen läuft.")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log.info("\nBeendet (Strg+C).")
        status_setzen("sleeping")
        browser_stoppen()
        monitor_aus()
        log.info("Auf Wiedersehen!")


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
