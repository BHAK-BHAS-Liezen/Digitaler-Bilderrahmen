<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Bilderrahmen Steuerung</title>
</head>

<body>

<h1>Bilderrahmen Steuerung</h1>

<form action="save.php" method="POST">

    <h2>Monitor</h2>

    <button name="monitor" value="on">
        Monitor AN
    </button>

    <button name="monitor" value="off">
        Monitor AUS
    </button>

    <br><br>

    <h2>Timeout</h2>

    <input type="number"
           name="timeout"
           value="30">

    <br><br>

    <button type="submit">
        Speichern
    </button>

</form>

</body>
</html>