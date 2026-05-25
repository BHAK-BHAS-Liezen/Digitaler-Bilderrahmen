"""
╔══════════════════════════════════════════════════════════════╗
║           Digitaler Bilderrahmen — Hauptprogramm             ║
║                                                              ║
║  Funktionen:                                                 ║
║  • PIR Motion Sensor erkennt Bewegung (GPIO 4)               ║
║  • Aufwärmzeit beim Start (Sensor kalibriert sich)           ║
║  • Monitor geht nach X Sekunden ohne Bewegung aus            ║
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
import json #verbindung mit json
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from gpiozero import MotionSensor

# ──────────────────────────────────────────────────────────────
#  KONFIGURATION — hier anpassen
# ──────────────────────────────────────────────────────────────

GPIO_PIN       = 4      # GPIO-Pin wo OUT des PIR-Sensors angeschlossen ist
WARMUP_SEC     = 30     # Sekunden Aufwärmzeit (Sensor kalibriert sich)
TIMEOUT_SEC    = 30     # Sekunden ohne Bewegung bis Monitor ausgeht
CONFIRM_COUNT  = 3      # Wie viele Messungen positiv sein müssen (Anti-Falschalarm)
CHECK_INTERVAL = 0.1    # Sekunden zwischen Sensor-Abfragen (0.1 = 10x pro Sekunde)

# Google Drive — Ordnernamen anpassen nach: rclone lsd onedrive:
GDRIVE_REMOTE   = "gdrive:Bilder"        # Google Drive Ordner "Bilder"
LOCAL_IMAGE_DIR = "/home/admin/Digitaler-Bilderrahmen/bilder"
# Log-Dateien
LOG_DATEI         = "/home/admin/Digitaler-Bilderrahmen/bilderrahmen.log"
ÄNDERUNGEN_LOG    = "/home/admin/Digitaler-Bilderrahmen/änderungen.log"
SYNC_INTERVAL     = 60                   # Sync alle 60 Sekunden

# Webserver & Chromium
WEB_DIR   = "/home/admin/Digitaler-Bilderrahmen"   # Ordner mit index.html
WEB_PORT  = 8080                         # Port des lokalen Webservers
# True  = Vollbild (kein Fensterrahmen, kein Cursor) → für fertigen Bilderrahmen
# False = normales Fenster → zum Testen
VOLLBILD  = False

# ──────────────────────────────────────────────────────────────
#  LOGGING — Ausgabe in Konsole UND Datei
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(threadName)-10s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/home/admin/Digitaler-Bilderrahmen/bilderrahmen.log")    ]
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  GLOBALER ZUSTAND
# ──────────────────────────────────────────────────────────────

state_lock       = threading.Lock()
screen_on        = True
last_motion_time = datetime.now()
motion_active    = False
system_ready     = False
browser_proc     = None           # Chromium-Prozess
status_datei     = os.path.join(WEB_DIR, "status.txt")
CONTROL_FILE = os.path.join(WEB_DIR, "data/control.json")

# ──────────────────────────────────────────────────────────────
#  HILFSFUNKTION: Status-Datei schreiben
#  Die index.html liest diese Datei und reagiert darauf:
#  "active"     → Slideshow läuft normal
#  "sleeping"   → Schlafmodus anzeigen, Slideshow pausieren
#  "warming_up" → Aufwärm-Animation anzeigen
# ──────────────────────────────────────────────────────────────

def status_setzen(status: str):
    try:
        with open(status_datei, "w") as f:
            f.write(status)
        log.info(f"Status → {status}")
    except Exception as e:
        log.warning(f"Status-Datei Fehler: {e}")

def lade_control(): #für verbindung mit php und json


    global TIMEOUT_SEC

    try:
        with open(CONTROL_FILE, "r") as f:
            data = json.load(f)

        TIMEOUT_SEC = data.get("timeout", 30)

        monitor_status = data.get("monitor", "on")


        if monitor_status == "off":
            monitor_aus()

        elif monitor_status == "on":
            monitor_an()

        elif monitor_status == "auto":

            # Sensoren übernehmen Steuerung
            pass
        


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


def monitor_aus():
    """Monitor ausschalten und Slideshow pausieren."""
    global screen_on

    with state_lock:
        bereits_aus = not screen_on

    if bereits_aus:
        return

    log.info("◼  Monitor AUS — Schlafmodus")

    # Erst Schlafmodus in der UI anzeigen, dann Monitor aus
    status_setzen("sleeping")
    time.sleep(1.5)
    os.system("vcgencmd display_power 0")

    with state_lock:
        screen_on = False


def browser_starten():
    """Chromium-Fenster mit der Slideshow öffnen."""
    global browser_proc

    # Warten bis Webserver bereit ist
    time.sleep(2)

    url = f"http://localhost:{WEB_PORT}"

    # Chromium-Parameter zusammenbauen
    chromium_cmd = [
        "chromium-browser",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
        "--autoplay-policy=no-user-gesture-required",
        url
    ]

    # Im Vollbild-Modus zusätzliche Parameter
    if VOLLBILD:
        chromium_cmd += [
            "--kiosk",          # Echter Vollbild-Modus, kein Schließen möglich
            "--start-fullscreen"
        ]
    else:
        chromium_cmd += [
            "--start-maximized"  # Normales Fenster, maximiert
        ]

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
#  Stellt index.html und die Bilder lokal bereit.
#  Chromium öffnet http://localhost:8080
# ──────────────────────────────────────────────────────────────

def webserver_thread():
    os.chdir(WEB_DIR)

    # HTTP-Logging deaktivieren (zu viel Output)
    class LeiserHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = HTTPServer(("", WEB_PORT), LeiserHandler)
    log.info(f"Webserver läuft auf http://localhost:{WEB_PORT}")
    server.serve_forever()


# ──────────────────────────────────────────────────────────────
#  THREAD 2: PIR-SENSOR
#  Läuft dauerhaft im Hintergrund.
#  Wartet erst die Aufwärmzeit ab, dann startet die Erkennung.
# ──────────────────────────────────────────────────────────────

def pir_thread():
    global last_motion_time, motion_active, system_ready

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

    # ── Bewegungserkennung (Endlosschleife) ───────────────────
    counter = 0

    while True:
        if pir.motion_detected:
            counter += 1

            with open(CONTROL_FILE, "r") as f:
                data = json.load(f)

            if data.get("monitor") != "auto":
                time.sleep(CHECK_INTERVAL)
                continue

            if counter >= CONFIRM_COUNT:
                with state_lock:
                    last_motion_time = datetime.now()
                    war_inaktiv = not motion_active
                    motion_active = True

                if war_inaktiv:
                    log.info("Bewegung erkannt 👤")
                    status_setzen("active")
                    monitor_an()

        else:
            if motion_active:
                log.info("Keine Bewegung mehr erkannt.")
                status_setzen("no_motion")

            counter = 0
            with state_lock:
                motion_active = False

        time.sleep(CHECK_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  THREAD 3: TIMEOUT-WÄCHTER
#  Prüft jede Sekunde: Wie lange keine Bewegung?
#  Nach TIMEOUT_SEC Sekunden → Monitor aus.
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


        with open(CONTROL_FILE, "r") as f:
            data = json.load(f)

        if data.get("monitor") != "auto":
            time.sleep(1)
            continue

        if inaktiv_seit > timedelta(seconds=TIMEOUT_SEC):
            if s_on:
                log.info(f"Keine Bewegung seit {TIMEOUT_SEC}s → Monitor aus.")
                monitor_aus()

        elif s_on:
            verbleibend = TIMEOUT_SEC - inaktiv_sek
            if verbleibend % 10 == 0 and verbleibend != letzte_warnung and 0 < verbleibend < TIMEOUT_SEC:
                log.info(f"Keine Bewegung — Monitor aus in {verbleibend}s")
                letzte_warnung = verbleibend

        time.sleep(1)


# ──────────────────────────────────────────────────────────────
#  HILFSFUNKTION: Aktuelle Bildliste holen
# ──────────────────────────────────────────────────────────────

def bilder_liste():
    """Gibt ein Set mit allen lokalen Bilddateinamen zurück."""
    if not os.path.isdir(LOCAL_IMAGE_DIR):
        return set()
    return set(
        f for f in os.listdir(LOCAL_IMAGE_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
    )


# ──────────────────────────────────────────────────────────────
#  THREAD 4: GOOGLE DRIVE-SYNC
#  Synchronisiert Bilder alle SYNC_INTERVAL Sekunden.
#  → Neue Bilder werden hinzugefügt
#  → Gelöschte Bilder werden lokal entfernt (rclone sync)
#  → Änderungen werden im Log angezeigt
# ──────────────────────────────────────────────────────────────

def gdrive_thread():
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

    while True:
        log.info("Google Drive-Sync wird gestartet...")

        # Bildliste VOR dem Sync merken
        bilder_vorher = bilder_liste()

        try:
            result = subprocess.run(
                [
                    "rclone", "sync",          # sync = neue hinzufügen UND gelöschte entfernen
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
                    "--delete-during",         # gelöschte Bilder sofort lokal entfernen
                ],
                capture_output=True,
                text=True,
                timeout=180
            )

            if result.returncode == 0:
                # Bildliste NACH dem Sync
                bilder_nachher = bilder_liste()

                # Vergleichen was sich geändert hat
                neu       = bilder_nachher - bilder_vorher
                geloescht = bilder_vorher  - bilder_nachher

                if neu:
                    log.info(f"  ✚ Neu hinzugefügt ({len(neu)}): {', '.join(sorted(neu))}")
                if geloescht:
                    log.info(f"  ✖ Entfernt ({len(geloescht)}): {', '.join(sorted(geloescht))}")
                if not neu and not geloescht:
                    log.info(f"  ↔ Keine Änderungen")

                # Änderungen in separate Log-Datei schreiben
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
#  HAUPTPROGRAMM
# ──────────────────────────────────────────────────────────────
#für verbindung mit php und json
def control_thread():

    while True:

        lade_control()

        time.sleep(2)


def main():
    log.info("=" * 55)
    log.info("   Digitaler Bilderrahmen — Start")
    log.info(f"   GPIO Pin:     {GPIO_PIN}")
    log.info(f"   Aufwärmzeit:  {WARMUP_SEC}s")
    log.info(f"   Timeout:      {TIMEOUT_SEC}s")
    log.info(f"   Google Drive: {GDRIVE_REMOTE}")
    log.info(f"   Vollbild:     {VOLLBILD}")
    log.info("=" * 55)

    # Ordner anlegen falls nicht vorhanden
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)

    # Status-Datei initialisieren
    status_setzen("warming_up")

    # ── Alle Threads starten ──────────────────────────────────
    threads = [
        threading.Thread(target=webserver_thread, name="Webserver",  daemon=True),
        threading.Thread(target=pir_thread,       name="PIR-Sensor", daemon=True),
        threading.Thread(target=timeout_thread,   name="Timeout",    daemon=True),
        threading.Thread(target=gdrive_thread,    name="GDrive",     daemon=True),

        #für verbindung php und json dings
        threading.Thread(target=control_thread, name="Control", daemon=True),
    ]

    for t in threads:
        t.start()
        log.info(f"Thread gestartet: {t.name}")

    # ── Chromium sofort öffnen (zeigt Aufwärm-Animation) ─────
    log.info("Chromium-Fenster wird geöffnet...")
    browser_starten()

    # ── Warten bis Sensor bereit ist ─────────────────────────
    log.info("Warte auf Aufwärmphase des Sensors...")
    while not system_ready:
        time.sleep(1)

    log.info("System bereit! Bilderrahmen läuft.")

    # ── Hauptthread am Leben halten ───────────────────────────
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
