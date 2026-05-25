<?php

$data = json_decode(file_get_contents("php://input"), true);

file_put_contents(
    "data/control.json",
    json_encode($data, JSON_PRETTY_PRINT)
);

echo json_encode([
    "success" => true
]);
?>