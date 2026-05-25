<?php

$data = [

    "monitor" => $_POST["monitor"],
    "timeout" => (int)$_POST["timeout"],
    "slideshow_speed" => 7
];

file_put_contents(
    "../data/control.json",
    json_encode($data, JSON_PRETTY_PRINT)
);

header("Location: index.php");
exit;
?>