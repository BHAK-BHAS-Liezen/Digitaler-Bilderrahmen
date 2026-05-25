<!DOCTYPE html>
<html lang="de">

<head>
<meta charset="UTF-8">

<title>Digitaler Bilderrahmen</title>

<style>

body{
    margin:0;
    overflow:hidden;
    background:black;
    color:white;
    font-family:Arial;
}

/* Menü Button */

#menuButton{

    position:fixed;

    top:20px;
    right:20px;

    z-index:9999;

    font-size:30px;

    background:rgba(0,0,0,0.6);

    color:white;

    border:none;

    padding:10px 15px;

    border-radius:10px;

    cursor:pointer;
}

/* Controlpanel */

#controlPanel{

    position:fixed;

    top:0;
    right:-320px;

    width:300px;
    height:100%;

    background:rgba(20,20,20,0.95);

    padding:20px;

    transition:0.3s;

    z-index:9998;
}

/* Buttons */

.controlButton{

    width:100%;

    padding:15px;

    margin-top:10px;

    font-size:18px;

    border:none;

    border-radius:10px;

    cursor:pointer;
}

input{

    width:100%;

    padding:10px;

    margin-top:10px;

    font-size:18px;
}

</style>

</head>

<body>

<!-- Menü Button -->

<button id="menuButton">
☰
</button>

<!-- Controlpanel -->

<div id="controlPanel">

    <h1>Steuerung</h1>

    <h2>Monitor</h2>

    <button class="controlButton" onclick="monitorAn()">
        Monitor AN
    </button>

    <button class="controlButton" onclick="monitorAus()">
        Monitor AUS
    </button>

    <h2>Timeout</h2>

    <input type="number"
           id="timeoutInput"
           value="30">

    <button class="controlButton" onclick="saveTimeout()">
        Timeout speichern
    </button>

</div>

<script>

/* Menü */

const menuButton = document.getElementById("menuButton");
const controlPanel = document.getElementById("controlPanel");

let menuOpen = false;

menuButton.onclick = () => {

    menuOpen = !menuOpen;

    if(menuOpen){
        controlPanel.style.right = "0px";
    }
    else{
        controlPanel.style.right = "-320px";
    }
}

/* Später mit JSON verbinden */
// für die save.php datei 
async function saveControl(data){

    await fetch("save.php", {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify(data)
    });
}

async function monitorAn(){

    await saveControl({
        monitor: "on",
        timeout: 30,
        slideshow_speed: 7
    });

    console.log("Monitor AN");
}

async function monitorAus(){

    await saveControl({
        monitor: "off",
        timeout: 30,
        slideshow_speed: 7
    });

    console.log("Monitor AUS");
}

async function saveTimeout(){

    const value =
        document.getElementById("timeoutInput").value;

    await saveControl({
        monitor: "on",
        timeout: parseInt(value),
        slideshow_speed: 7
    });

    console.log("Timeout gespeichert");
}

function saveTimeout(){

    const value =
        document.getElementById("timeoutInput").value;

    console.log("Timeout:", value);

    // später control.json ändern
}




</script>

</body>
</html>