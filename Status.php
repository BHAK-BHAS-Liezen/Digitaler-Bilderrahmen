<?php
/**
 * status_api.php — Liefert Sensor-Status als JSON
 * Wird vom Control-Panel per AJAX alle 2 Sekunden abgefragt.
 */

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-cache, no-store, must-revalidate');

$status_datei = __DIR__ . '/../data/sensor_status.json';

if (file_exists($status_datei)) {
    $inhalt = file_get_contents($status_datei);
    echo $inhalt;
} else {
    echo json_encode([
        "zeitstempel"     => date("H:i:s"),
        "pir_aktiv"       => false,
        "mikrofon_aktiv"  => false,
        "monitor_an"      => true,
        "system_bereit"   => false,
        "mic_schwellwert" => 500,
        "timeout_sek"     => 30,
        "fehler"          => "sensor_status.json nicht gefunden"
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
}
?>
