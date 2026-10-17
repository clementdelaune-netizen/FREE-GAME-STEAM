"""
Générateur de script navigateur (JavaScript) alternatif pour ajouter les jeux gratuits
directement depuis la console F12 sur store.steampowered.com/account/licenses/
"""

import json
import os
from typing import List


def generate_browser_script(package_ids: List[int], output_file: str = "steam_browser_script.js") -> str:
    """Génère un script JS autonome à coller dans la console du navigateur."""
    packages_json = json.dumps(package_ids[:500])  # Lot de 500 ou sélection
    total = len(package_ids)

    js_code = f"""// ========================================================
// STEAM AUTO FREE GAMES - SCRIPT CONSOLE NAVIGATEUR
// Instructions :
// 1. Ouvre Chrome/Edge/Firefox sur : https://store.steampowered.com/account/licenses/
// 2. Assure-toi d'être bien connecté à ton compte Steam.
// 3. Appuie sur F12 -> Onglet 'Console'.
// 4. Colle tout ce script et appuie sur Entrée.
// ========================================================

(function() {{
    const CHECKOUT_URL = 'https://store.steampowered.com/checkout/addfreelicense';
    const packagesToClaim = {packages_json};
    const delayBetweenRequests = 3000; // 3 secondes entre chaque ajout
    let addedCount = 0;
    let index = 0;

    console.log("%c[Steam Auto Free]%c Démarrage de l'ajout automatique de " + packagesToClaim.length + " jeux...", "color: #00ff00; font-weight: bold", "color: #ffffff");

    function addNext() {{
        if (index >= packagesToClaim.length) {{
            console.log("%c[Terminé !]%c " + addedCount + " jeux ajoutés avec succès !", "color: #00ff00; font-weight: bold", "color: #ffffff");
            alert("Opération terminée ! " + addedCount + " jeux ajoutés à ta bibliothèque Steam.");
            return;
        }}

        const subid = packagesToClaim[index++];
        const data = new URLSearchParams();
        data.append('action', 'add_to_cart');
        data.append('sessionid', g_sessionID);
        data.append('subid', subid);

        fetch(CHECKOUT_URL, {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            }},
            body: data
        }})
        .then(response => response.text())
        .then(html => {{
            if (html.toLowerCase().includes("success") || html.toLowerCase().includes("a été ajouté")) {{
                addedCount++;
                console.log(`%c[OK]%c Licence #${{subid}} ajoutée (${{addedCount}} ajoutés - ${{index}}/${{packagesToClaim.length}})`, "color: #2ecc71", "color: #bdc3c7");
            }} else if (html.includes("There was a problem adding this product") && html.includes("Please try again later")) {{
                console.warn(`%c[Limite Steam atteinte]%c Pause de sécurité recommandée après #${{subid}}`, "color: #e67e22", "color: #bdc3c7");
            }} else {{
                console.log(`%c[Info]%c Licence #${{subid}} ignorée (déjà possédée ou indisponible)`, "color: #95a5a6", "color: #7f8c8d");
            }}
            setTimeout(addNext, delayBetweenRequests);
        }})
        .catch(err => {{
            console.error(`Erreur pour #${{subid}}:`, err);
            setTimeout(addNext, delayBetweenRequests);
        }});
    }}

    addNext();
}})();
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(js_code)
    return output_file
