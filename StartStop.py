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
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
import threading
import subprocess
import logging
from datetime import datetime, timedelta
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
# Beispiele:
#   "onedrive:"              → Root (alle Dateien)
#   "onedrive:Bilder"        → Ordner namens "Bilder"
#   "onedrive:Fotos/Urlaub"  → Unterordner "Urlaub"
GDRIVE_REMOTE   = "onedrive:Bilder"  # Google Drive Ordner "Bilder"
LOCAL_IMAGE_DIR = "/home/pi/bilderrahmen/bilder"
SYNC_INTERVAL   = 300   # OneDrive-Sync alle 5 Minuten (300 Sekunden)

# Slideshow-Programm (feh zeigt Bilder als Vollbild-Diashow)
SLIDESHOW_CMD = [
    "feh",
    "--fullscreen",
    "--slideshow-delay", "6",
    "--randomize",
    "--auto-zoom",
    "--hide-pointer",
    LOCAL_IMAGE_DIR
]

# ──────────────────────────────────────────────────────────────
#  LOGGING — Ausgabe in Konsole UND Datei
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(threadName)-10s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/home/pi/bilderrahmen/bilderrahmen.log")
    ]
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  GLOBALER ZUSTAND
#  Alle Threads teilen diese Variablen.
#  state_lock verhindert gleichzeitige Zugriffe (Thread-sicher).
# ──────────────────────────────────────────────────────────────

state_lock       = threading.Lock()
screen_on        = True           # Aktueller Monitor-Status
last_motion_time = datetime.now() # Zeitpunkt der letzten Bewegung
motion_active    = False          # Gerade Bewegung erkannt?
system_ready     = False          # False während Aufwärmphase
slideshow_proc   = None           # Prozess-Handle der Slideshow

# ──────────────────────────────────────────────────────────────
#  MONITOR-STEUERUNG
# ──────────────────────────────────────────────────────────────

def monitor_an():
    """Monitor einschalten und Slideshow fortsetzen."""
    global screen_on, slideshow_proc

    with state_lock:
        bereits_an = screen_on

    if bereits_an:
        return  # Nichts tun wenn Monitor schon an ist

    log.info("▶  Monitor AN")
    os.system("vcgencmd display_power 1")

    with state_lock:
        screen_on = True

    # Slideshow wieder starten falls sie gestoppt wurde
    slideshow_starten()


def monitor_aus():
    """Monitor ausschalten und Slideshow pausieren."""
    global screen_on

    with state_lock:
        bereits_aus = not screen_on

    if bereits_aus:
        return  # Nichts tun wenn Monitor schon aus ist

    log.info("◼  Monitor AUS — Schlafmodus")

    # Erst Slideshow stoppen, dann Monitor aus
    slideshow_stoppen()
    time.sleep(0.5)
    os.system("vcgencmd display_power 0")

    with state_lock:
        screen_on = False


def slideshow_starten():
    """feh-Slideshow im Hintergrund starten."""
    global slideshow_proc

    # Prüfen ob Bilder-Ordner existiert
    if not os.path.isdir(LOCAL_IMAGE_DIR):
        log.warning(f"Bilder-Ordner nicht gefunden: {LOCAL_IMAGE_DIR}")
        return

    # Prüfen ob Bilder vorhanden sind
    bilder = [
        f for f in os.listdir(LOCAL_IMAGE_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
    ]

    if not bilder:
        log.warning("Keine Bilder im Ordner — warte auf OneDrive-Sync...")
        return

    # Alte Slideshow stoppen falls noch aktiv
    slideshow_stoppen()

    try:
        slideshow_proc = subprocess.Popen(
            SLIDESHOW_CMD,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log.info(f"Slideshow gestartet ({len(bilder)} Bilder)")
    except FileNotFoundError:
        log.error("'feh' nicht installiert! → sudo apt install feh")


def slideshow_stoppen():
    """Laufende feh-Slideshow beenden."""
    global slideshow_proc

    if slideshow_proc and slideshow_proc.poll() is None:
        slideshow_proc.terminate()
        try:
            slideshow_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            slideshow_proc.kill()
        log.info("Slideshow pausiert")
    slideshow_proc = None


# ──────────────────────────────────────────────────────────────
#  THREAD 1: PIR-SENSOR
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
    # PIR-Sensoren brauchen 30-60 Sek zum Kalibrieren.
    # In dieser Zeit werden alle Bewegungen ignoriert.
    log.info(f"Aufwärmphase gestartet: {WARMUP_SEC} Sekunden...")

    for verbleibend in range(WARMUP_SEC, 0, -5):
        log.info(f"  Sensor bereit in {verbleibend}s ...")
        time.sleep(5)

    log.info("Sensor kalibriert und bereit ✓")
    system_ready = True

    # ── Bewegungserkennung (Endlosschleife) ───────────────────
    counter = 0

    while True:
        if pir.motion_detected:
            counter += 1

            # Erst nach CONFIRM_COUNT aufeinanderfolgenden Treffern reagieren
            if counter >= CONFIRM_COUNT:
                with state_lock:
                    last_motion_time = datetime.now()
                    war_inaktiv = not motion_active
                    motion_active = True

                # Nur beim Übergang von "keine Bewegung" zu "Bewegung" reagieren
                if war_inaktiv:
                    log.info("Bewegung erkannt 👤")
                    monitor_an()

        else:
            # Zähler zurücksetzen sobald keine Bewegung mehr
            if motion_active:
                log.info("Keine Bewegung mehr erkannt.")

            counter = 0
            with state_lock:
                motion_active = False

        time.sleep(CHECK_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  THREAD 2: TIMEOUT-WÄCHTER
#  Prüft jede Sekunde: Wie lange keine Bewegung?
#  Nach TIMEOUT_SEC Sekunden → Monitor aus.
# ──────────────────────────────────────────────────────────────

def timeout_thread():
    letzte_warnung = -1

    while True:
        # Während Aufwärmphase nichts tun
        if not system_ready:
            time.sleep(1)
            continue

        with state_lock:
            lmt  = last_motion_time
            s_on = screen_on

        inaktiv_seit = datetime.now() - lmt
        inaktiv_sek  = int(inaktiv_seit.total_seconds())

        if inaktiv_seit > timedelta(seconds=TIMEOUT_SEC):
            # Timeout erreicht → Monitor ausschalten
            if s_on:
                log.info(f"Keine Bewegung seit {TIMEOUT_SEC}s → Monitor aus.")
                monitor_aus()

        elif s_on:
            # Countdown alle 10 Sekunden loggen
            verbleibend = TIMEOUT_SEC - inaktiv_sek
            if verbleibend % 10 == 0 and verbleibend != letzte_warnung and 0 < verbleibend < TIMEOUT_SEC:
                log.info(f"Keine Bewegung — Monitor aus in {verbleibend}s")
                letzte_warnung = verbleibend

        time.sleep(1)


# ──────────────────────────────────────────────────────────────
#  THREAD 3: GOOGLE DRIVE-SYNC
#  Synchronisiert Bilder vom Google Drive alle SYNC_INTERVAL Sekunden.
#  Benötigt rclone (einmalig einrichten mit: rclone config)
# ──────────────────────────────────────────────────────────────

def onedrive_thread():
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

    while True:
        log.info("Google Drive-Sync wird gestartet...")

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
                    "--transfers", "2",
                    "--low-level-retries", "3"
                ],
                capture_output=True,
                text=True,
                timeout=180
            )

            if result.returncode == 0:
                anzahl = len([
                    f for f in os.listdir(LOCAL_IMAGE_DIR)
                    if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                ])
                log.info(f"Google Drive-Sync abgeschlossen ✓  ({anzahl} Bilder)")

                # Slideshow neu starten damit neue Bilder erscheinen
                with state_lock:
                    s_on = screen_on
                if s_on:
                    slideshow_starten()

            else:
                log.warning(f"rclone Fehler: {result.stderr.strip()}")

        except FileNotFoundError:
            log.error("rclone nicht gefunden! → sudo apt install rclone")
            log.error("Einrichten mit: rclone config")
        except subprocess.TimeoutExpired:
            log.warning("OneDrive-Sync Timeout — nächster Versuch in 5 Min.")
        except Exception as e:
            log.error(f"Sync-Fehler: {e}")

        log.info(f"Nächster Sync in {SYNC_INTERVAL // 60} Minuten.")
        time.sleep(SYNC_INTERVAL)


# ──────────────────────────────────────────────────────────────
#  HAUPTPROGRAMM
# ──────────────────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("   Digitaler Bilderrahmen — Start")
    log.info(f"   GPIO Pin:    {GPIO_PIN}")
    log.info(f"   Aufwärmzeit: {WARMUP_SEC}s")
    log.info(f"   Timeout:     {TIMEOUT_SEC}s")
    log.info(f"   Google Drive: {GDRIVE_REMOTE}")
    log.info("=" * 55)

    # Ordner anlegen falls nicht vorhanden
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)
    os.makedirs("/home/pi/bilderrahmen", exist_ok=True)

    # ── Threads starten ───────────────────────────────────────
    threads = [
        threading.Thread(target=pir_thread,      name="PIR-Sensor", daemon=True),
        threading.Thread(target=timeout_thread,  name="Timeout",    daemon=True),
        threading.Thread(target=onedrive_thread, name="OneDrive",   daemon=True),
    ]

    for t in threads:
        t.start()
        log.info(f"Thread gestartet: {t.name}")

    log.info("Warte auf Aufwärmphase des Sensors...")

    # ── Warten bis Sensor bereit ist ──────────────────────────
    while not system_ready:
        time.sleep(1)

    log.info("System bereit! Slideshow wird gestartet.")
    monitor_an()
    slideshow_starten()

    # ── Hauptthread am Leben halten ───────────────────────────
    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log.info("\nBeendet (Strg+C).")
        slideshow_stoppen()
        monitor_aus()
        log.info("Auf Wiedersehen!")


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
