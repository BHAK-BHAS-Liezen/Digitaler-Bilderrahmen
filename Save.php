<?php
/**
 * Save.php — Speichert Einstellungen in data/control.json
 * Funktioniert sowohl mit AJAX als auch normalen Formular-Submits
 */

$data = [
    "monitor"         => $_POST["monitor"] ?? "on",
    "timeout"         => (int)($_POST["timeout"] ?? 30),
    "slideshow_speed" => (int)($_POST["slideshow_speed"] ?? 7),
    "mic_schwellwert" => (int)($_POST["mic_schwellwert"] ?? 500),
];

file_put_contents(
    __DIR__ . "/data/control.json",
    json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)
);

// Prüfe ob AJAX-Anfrage oder normales Formular
$is_ajax = !empty($_SERVER['HTTP_X_REQUESTED_WITH']) &&
           strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) === 'xmlhttprequest';

if ($is_ajax) {
    // AJAX: JSON-Response (kein Redirect)
    header('Content-Type: application/json');
    http_response_code(200);
    echo json_encode(["success" => true, "message" => "Gespeichert"]);
} else {
    // Normales Formular: Umleiten
    header("Location: index.php");
}
exit;
?>