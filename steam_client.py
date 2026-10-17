"""
Module de gestion du client Steam et de l'ajout automatique de jeux gratuits.
Utilise la commande native Steam Desktop (+app_license_request) pour une activation garantie
directement dans la bibliothèque Steam, sans aucun échec ni redirection.
"""

import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import winreg
from typing import Dict, List, Optional, Set, Tuple
import requests

try:
    import win32crypt
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

SESSION_FILE = "steam_session.json"
BASE_STORE_URL = "https://store.steampowered.com"
USERDATA_URL = f"{BASE_STORE_URL}/dynamicstore/userdata/"
LICENSES_PAGE_URL = f"{BASE_STORE_URL}/account/licenses/"
FREELICENSE_ADD_URL = f"{BASE_STORE_URL}/freelicense/addfreelicense/{{subid}}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_steam_exe() -> Optional[str]:
    """Trouve l'exécutable Steam via le registre Windows ou les chemins par défaut."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_exe, _ = winreg.QueryValueEx(key, "SteamExe")
        if steam_exe and os.path.exists(steam_exe):
            return os.path.normpath(steam_exe)
    except Exception:
        pass

    common_paths = [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    return None


def is_steam_running() -> bool:
    """Vérifie si le processus steam.exe est actuellement en cours d'exécution."""
    try:
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq steam.exe" /NH',
            shell=True,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
        return "steam.exe" in output.lower()
    except Exception:
        return False


def launch_steam() -> Tuple[bool, str]:
    """Lance Steam s'il n'est pas déjà démarré."""
    if is_steam_running():
        return True, "Steam est déjà en cours d'exécution."

    steam_exe = get_steam_exe()
    if steam_exe:
        try:
            subprocess.Popen([steam_exe], shell=False)
            # Attente de quelques secondes pour l'initialisation du client
            time.sleep(3)
            return True, f"Steam démarré avec succès depuis {steam_exe}"
        except Exception as e:
            return False, f"Erreur lors du lancement de Steam : {e}"

    try:
        os.startfile("steam://open/main")
        time.sleep(3)
        return True, "Steam démarré via le protocole URL steam://"
    except Exception as e:
        return False, f"Impossible de lancer Steam : {e}"


def _decrypt_chromium_cookie_value(enc_val: bytes, decrypted_key: bytes) -> str:
    """Déchiffre un cookie chiffré par Chromium (AES-GCM v10/v11 ou DPAPI)."""
    if not CRYPTO_AVAILABLE:
        return ""
    try:
        if enc_val.startswith(b"v10") or enc_val.startswith(b"v11"):
            nonce = enc_val[3:15]
            ciphertext = enc_val[15:]
            aesgcm = AESGCM(decrypted_key)
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted.decode("utf-8", errors="ignore")
        else:
            decrypted = win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1]
            return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_cookies_from_chromium_folder(folder_path: str) -> Dict[str, str]:
    """Extrait les cookies steampowered depuis un dossier de cache Chromium."""
    if not CRYPTO_AVAILABLE or not os.path.exists(folder_path):
        return {}

    local_state_path = os.path.join(folder_path, "Local State")
    if not os.path.exists(local_state_path):
        return {}

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            state_json = json.load(f)
        encrypted_key = base64.b64decode(state_json["os_crypt"]["encrypted_key"])
        dpapi_key = encrypted_key[5:]
        decrypted_key = win32crypt.CryptUnprotectData(dpapi_key, None, None, None, 0)[1]
    except Exception:
        return {}

    potential_dbs = [
        os.path.join(folder_path, "Default", "Network", "Cookies"),
        os.path.join(folder_path, "Network", "Cookies"),
        os.path.join(folder_path, "Default", "Cookies"),
    ]

    extracted = {}
    for db_path in potential_dbs:
        if not os.path.exists(db_path):
            continue

        tmp_db = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp_file:
                tmp_db = tmp_file.name
            shutil.copyfile(db_path, tmp_db)

            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute(
                "SELECT name, encrypted_value FROM cookies "
                "WHERE host_key LIKE '%steampowered%' OR host_key LIKE '%steamcommunity%'"
            )
            rows = cur.fetchall()
            conn.close()

            for name, enc_val in rows:
                if name in ("sessionid", "steamLoginSecure"):
                    val = _decrypt_chromium_cookie_value(enc_val, decrypted_key)
                    if val:
                        extracted[name] = val

            if "sessionid" in extracted and "steamLoginSecure" in extracted:
                break
        except Exception:
            pass
        finally:
            if tmp_db and os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except Exception:
                    pass

    return extracted


def auto_detect_steam_session() -> Tuple[Optional[str], Optional[str], str]:
    """
    Détecte et extrait automatiquement les cookies de session Steam locale :
    1. Depuis le client Steam Desktop officiel (htmlcache).
    2. Depuis Google Chrome.
    3. Depuis Microsoft Edge.
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    sources = [
        ("Steam Desktop", os.path.join(local_app_data, "Steam", "htmlcache")),
        ("Google Chrome", os.path.join(local_app_data, "Google", "Chrome", "User Data")),
        ("Microsoft Edge", os.path.join(local_app_data, "Microsoft", "Edge", "User Data")),
    ]

    for source_name, path in sources:
        if os.path.exists(path):
            cookies = _extract_cookies_from_chromium_folder(path)
            if "sessionid" in cookies and "steamLoginSecure" in cookies:
                return cookies["sessionid"], cookies["steamLoginSecure"], source_name

    return None, None, ""


class SteamSession:
    """Gère la session Steam et les requêtes d'ajout de jeux."""

    def __init__(self, session_file: str = SESSION_FILE):
        self.session_file = session_file
        self.session_id: Optional[str] = None
        self.steam_login_secure: Optional[str] = None
        self.account_name: Optional[str] = None
        self.connection_source: str = ""
        self.http = requests.Session()
        self.http.headers.update(DEFAULT_HEADERS)
        self.load()

    def load(self) -> bool:
        """Charge la session sauvegardée si disponible."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.session_id = data.get("session_id")
                    self.steam_login_secure = data.get("steam_login_secure")
                    self.account_name = data.get("account_name")
                    self._update_cookies()
                    return True
            except Exception:
                return False
        return False

    def save(self) -> None:
        """Sauvegarde les informations de session localement."""
        data = {
            "session_id": self.session_id,
            "steam_login_secure": self.steam_login_secure,
            "account_name": self.account_name,
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _update_cookies(self) -> None:
        """Met à jour les cookies dans la session HTTP pour tous les domaines Steam."""
        domains = [
            ".steampowered.com",
            "store.steampowered.com",
            "checkout.steampowered.com",
            "steamcommunity.com",
            ".steamcommunity.com",
            "help.steampowered.com",
        ]
        for domain in domains:
            if self.session_id:
                self.http.cookies.set("sessionid", self.session_id, domain=domain, path="/")
            if self.steam_login_secure:
                self.http.cookies.set("steamLoginSecure", self.steam_login_secure, domain=domain, path="/")

    def set_credentials(self, session_id: str, steam_login_secure: str) -> None:
        """Définit les identifiants de session."""
        self.session_id = session_id.strip()
        self.steam_login_secure = steam_login_secure.strip()
        self._update_cookies()

    def validate(self) -> Tuple[bool, str]:
        """Vérifie si les cookies permettent d'être connecté à Steam Store."""
        if not self.session_id or not self.steam_login_secure:
            return False, "Identifiants de session manquants."

        try:
            r = self.http.get(LICENSES_PAGE_URL, timeout=15)
            if r.status_code != 200:
                return False, f"Code HTTP inattendu : {r.status_code}"

            if "<title>Sign In</title>" in r.text or "<title>Connexion</title>" in r.text:
                return False, "Session expirée ou invalide."

            account_match = re.search(r'account_name["\']?>\s*([^<]+)<', r.text, re.IGNORECASE)
            if not account_match:
                account_match = re.search(r'class="persona persona_name">([^<]+)<', r.text)
            if not account_match:
                account_match = re.search(r'id="account_pulldown">([^<]+)<', r.text)

            if account_match:
                self.account_name = account_match.group(1).strip()
                self.save()
                return True, f"Connecté en tant que : {self.account_name}"

            if "account_table" in r.text or "RemoveFreeLicense" in r.text or "licenses" in r.url:
                self.account_name = self.account_name or "Utilisateur Steam"
                self.save()
                return True, f"Session active ({self.account_name})"

            return False, "Impossible de confirmer la connexion Steam."
        except Exception as e:
            return False, f"Erreur de connexion : {e}"

    def auto_login(self) -> Tuple[bool, str]:
        """Détection et connexion automatique au compte Steam."""
        if self.session_id and self.steam_login_secure:
            valid, msg = self.validate()
            if valid:
                self.connection_source = "Fichier local"
                return True, f"Connecté automatiquement ({self.account_name})"

        sid, sec, source = auto_detect_steam_session()
        if sid and sec:
            self.set_credentials(sid, sec)
            valid, msg = self.validate()
            if valid:
                self.connection_source = source
                self.save()
                return True, f"Connecté automatiquement via {source} ({self.account_name})"

        return False, "Aucune session Steam active détectée."

    def get_owned_items(self) -> Tuple[Set[int], Set[int]]:
        """
        Récupère l'ensemble complet des packages (subid) et des jeux (appid)
        actuellement possédés dans la bibliothèque de l'utilisateur.
        """
        owned_packages: Set[int] = set()
        owned_apps: Set[int] = set()

        try:
            r = self.http.get(USERDATA_URL, timeout=15)
            if r.status_code == 200:
                data = r.json()
                for p in data.get("rgOwnedPackages", []):
                    try:
                        owned_packages.add(int(p))
                    except (ValueError, TypeError):
                        pass
                for a in data.get("rgOwnedApps", []):
                    try:
                        owned_apps.add(int(a))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        try:
            r = self.http.get(LICENSES_PAGE_URL, timeout=15)
            if r.status_code == 200:
                subids = re.findall(r"RemoveFreeLicense\(\s*(\d+)", r.text)
                for s in subids:
                    try:
                        owned_packages.add(int(s))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

        return owned_packages, owned_apps

    def add_free_game_client(self, appid: int) -> bool:
        """
        Active un jeu gratuit DIRECTEMENT dans le client Steam actif
        via la commande native "+app_license_request <appid>".
        Chaque jeu doit être demandé individuellement pour être correctement pris en compte par Steam.
        """
        if not appid:
            return False

        if not is_steam_running():
            launch_steam()
            time.sleep(2)

        steam_exe = get_steam_exe()
        if not steam_exe:
            return False

        cmd = [steam_exe, "+app_license_request", str(appid)]
        try:
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception:
            return False

    def add_free_games_batch_client(self, appids: List[int], delay: float = 1.0) -> int:
        """
        Ajoute un lot de jeux gratuits dans le client Steam en envoyant
        la commande native "+app_license_request" successivement pour chaque jeu.
        """
        success_sent = 0
        for aid in appids:
            if self.add_free_game_client(aid):
                success_sent += 1
            if delay > 0:
                time.sleep(delay)
        return success_sent

    def add_free_package_web(self, subid: int) -> Tuple[str, str]:
        """
        Ajoute un package gratuit officiel via l'endpoint web freelicense/addfreelicense/{subid}.
        """
        if not self.session_id or not self.steam_login_secure:
            return "expired", "Session non configurée."

        self._update_cookies()
        url = FREELICENSE_ADD_URL.format(subid=subid)
        headers = {
            "Referer": "https://store.steampowered.com/",
            "Origin": BASE_STORE_URL,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            r = self.http.post(url, data={"ajax": "true", "sessionid": self.session_id}, headers=headers, timeout=15)

            if "/login" in r.url or "<title>Sign In</title>" in r.text or "<title>Connexion</title>" in r.text:
                return "expired", "Session expirée."

            if r.status_code == 403:
                return "forbidden", f"Accès refusé pour #{subid} (403 Forbidden)."

            if r.status_code == 429:
                return "rate_limit", "Limite horaire atteinte côté Steam."

            if r.status_code != 200:
                return "error", f"Erreur HTTP {r.status_code}."

            text_lower = r.text.lower()
            if "success" in text_lower or "is now registered to your account" in text_lower or "a été ajouté" in text_lower:
                return "success", f"Licence #{subid} ajoutée avec succès."

            if "this product is already available" in text_lower or "déjà disponible" in text_lower:
                return "already_owned", f"Licence #{subid} déjà possédée."

            if "there was a problem adding this product" in text_lower:
                return "rate_limit", "Steam demande de patienter."

            if "site error" in text_lower:
                return "invalid", f"Package #{subid} expiré ou non disponible."

            return "success", f"Requête envoyée pour #{subid}."
        except requests.Timeout:
            return "error", "Délai d'attente dépassé."
        except Exception as e:
            return "error", f"Erreur réseau : {e}"
