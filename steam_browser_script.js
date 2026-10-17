// ========================================================
// STEAM AUTO FREE GAMES - SCRIPT CONSOLE NAVIGATEUR
// Instructions :
// 1. Ouvre Chrome/Edge/Firefox sur : https://store.steampowered.com/account/licenses/
// 2. Assure-toi d'être bien connecté à ton compte Steam.
// 3. Appuie sur F12 -> Onglet 'Console'.
// 4. Colle tout ce script et appuie sur Entrée.
// ========================================================

(function() {
    const CHECKOUT_URL = 'https://store.steampowered.com/checkout/addfreelicense';
    const packagesToClaim = [199291, 730];
    const delayBetweenRequests = 3000; // 3 secondes entre chaque ajout
    let addedCount = 0;
    let index = 0;

    console.log("%c[Steam Auto Free]%c Démarrage de l'ajout automatique de " + packagesToClaim.length + " jeux...", "color: #00ff00; font-weight: bold", "color: #ffffff");

    function addNext() {
        if (index >= packagesToClaim.length) {
            console.log("%c[Terminé !]%c " + addedCount + " jeux ajoutés avec succès !", "color: #00ff00; font-weight: bold", "color: #ffffff");
            alert("Opération terminée ! " + addedCount + " jeux ajoutés à ta bibliothèque Steam.");
            return;
        }

        const subid = packagesToClaim[index++];
        const data = new URLSearchParams();
        data.append('action', 'add_to_cart');
        data.append('sessionid', g_sessionID);
        data.append('subid', subid);

        fetch(CHECKOUT_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            },
            body: data
        })
        .then(response => response.text())
        .then(html => {
            if (html.toLowerCase().includes("success") || html.toLowerCase().includes("a été ajouté")) {
                addedCount++;
                console.log(`%c[OK]%c Licence #${subid} ajoutée (${addedCount} ajoutés - ${index}/${packagesToClaim.length})`, "color: #2ecc71", "color: #bdc3c7");
            } else if (html.includes("There was a problem adding this product") && html.includes("Please try again later")) {
                console.warn(`%c[Limite Steam atteinte]%c Pause de sécurité recommandée après #${subid}`, "color: #e67e22", "color: #bdc3c7");
            } else {
                console.log(`%c[Info]%c Licence #${subid} ignorée (déjà possédée ou indisponible)`, "color: #95a5a6", "color: #7f8c8d");
            }
            setTimeout(addNext, delayBetweenRequests);
        })
        .catch(err => {
            console.error(`Erreur pour #${subid}:`, err);
            setTimeout(addNext, delayBetweenRequests);
        });
    }

    addNext();
})();
