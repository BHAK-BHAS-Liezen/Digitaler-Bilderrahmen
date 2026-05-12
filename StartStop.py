from gpiozero import MotionSensor
from datetime import datetime, timedelta
import os
import time

# PIR-Sensor an GPIO-Pin 4
pir = MotionSensor(4)

# Sekunden bis der Bildschirm ausgeht
TIMEOUT = 10

# Status Bildschirm
screen_on = False

# Zeitpunkt der letzten Bewegung
last_motion_time = datetime.now()

print("System gestartet :) ...")


def bildschirm_an():
    """Bildschirm einschalten und Status setzen."""
    global screen_on
    if not screen_on:
        print(f"{datetime.now().strftime('%H:%M:%S')} – Bildschirm AN")
        os.system("vcgencmd display_power 1")
        screen_on = True


def bildschirm_aus():
    """Bildschirm ausschalten und Status setzen."""
    global screen_on
    if screen_on:
        print(f"{datetime.now().strftime('%H:%M:%S')} – Bildschirm AUS")
        os.system("vcgencmd display_power 0")
        screen_on = False


try:
    while True:
        if pir.motion_detected:
            # Bewegung erkannt: Zeit aktualisieren und Bildschirm einschalten
            print("Bewegung erkannt")
            last_motion_time = datetime.now()
            bildschirm_an()
        else:
            # Keine Bewegung: prüfen ob Timeout abgelaufen ist
            inactive_time = datetime.now() - last_motion_time

            if inactive_time > timedelta(seconds=TIMEOUT):
                bildschirm_aus()

        time.sleep(0.5)  # kurze Pause, um die CPU zu entlasten

except KeyboardInterrupt:
    print("\nBeendet.")

except Exception as e:
    print(f"Fehler aufgetreten: {e}")