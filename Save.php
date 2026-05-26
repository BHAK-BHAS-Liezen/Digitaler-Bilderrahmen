<?php
/**
 * save.php — Speichert Einstellungen in data/control.json
 */

$data = [
    "monitor"         => $_POST["monitor"] ?? "on",
    "timeout"         => (int)($_POST["timeout"] ?? 30),
    "slideshow_speed" => (int)($_POST["slideshow_speed"] ?? 7),
    "mic_schwellwert" => (int)($_POST["mic_schwellwert"] ?? 500),
];

file_put_contents(
    __DIR__ . "/../data/control.json",
    json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)
);

header("Location: index.php");
exit;
?>
