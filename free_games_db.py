"""
Module de gestion et de filtrage du catalogue des jeux gratuits Steam réels et actifs.
Permet d'explorer et de gérer un catalogue de plus de 8000 jeux gratuits disponibles sur Steam.
"""

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Set, Tuple
import requests

CACHE_DIR = "cache"
REAL_GAMES_CACHE_FILE = os.path.join(CACHE_DIR, "real_free_games.json")
PROGRESS_FILE = "progress.json"

DEFAULT_CATALOG_TARGET = 8000

STEAM_SEARCH_URL = (
    "https://store.steampowered.com/search/results/?query=&start={start}&count=100&maxprice=free&category1=998"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def ensure_cache_dir() -> None:
    """Crée le dossier de cache s'il n'existe pas."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def load_progress() -> Dict:
    """Charge l'état d'avancement pour reprendre là où on s'était arrêté."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("added_appids", [])
                data.setdefault("added_names", [])
                data.setdefault("unsupported_appids", [])
                data.setdefault("total_added", len(data["added_appids"]))
                return data
        except Exception:
            pass
    return {
        "added_appids": [],
        "added_names": [],
        "unsupported_appids": [],
        "total_added": 0,
    }


def save_progress(progress: Dict) -> None:
    """Sauvegarde l'avancement dans le fichier progress.json."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def sanitize_progress(progress: Dict, owned_apps: Set[int]) -> Dict:
    """
    Assainit l'historique de progression en vérifiant les jeux réellement possédés sur Steam.
    Supprime automatiquement les entrées erronées ou jamais ajoutées à la bibliothèque.
    """
    if not owned_apps:
        return progress

    current_added = progress.get("added_appids", [])
    current_names = progress.get("added_names", [])
    name_map = dict(zip(current_added, current_names)) if len(current_added) == len(current_names) else {}

    # Ne conserver comme réellement ajoutés que les jeux présents dans la bibliothèque Steam
    real_added = [aid for aid in current_added if aid in owned_apps]
    real_names = [name_map.get(aid, str(aid)) for aid in real_added]

    if len(real_added) != len(current_added):
        progress["added_appids"] = real_added
        progress["added_names"] = real_names
        progress["total_added"] = len(real_added)
        save_progress(progress)

    return progress


def fetch_real_free_games(
    target_count: int = DEFAULT_CATALOG_TARGET,
    force_refresh: bool = False,
    owned_apps: Set[int] = None,
    min_unowned_target: int = 50,
    session_http: Optional[requests.Session] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Tuple[str, int]]:
    """
    Récupère en continu le catalogue réel des jeux gratuits du magasin Steam (jusqu'à target_count, ex: 8000 jeux).
    Utilise le cache local s'il est déjà alimenté, et explore le magasin Steam si nécessaire.
    """
    ensure_cache_dir()

    all_games_map: Dict[int, str] = {}

    # 1. Charger le cache existant
    if os.path.exists(REAL_GAMES_CACHE_FILE) and not force_refresh:
        try:
            with open(REAL_GAMES_CACHE_FILE, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                for item in cached_data:
                    all_games_map[int(item["appid"])] = item["title"]
        except Exception:
            pass

    # Vérifier si on a déjà atteint la cible de jeux
    if not force_refresh and len(all_games_map) >= target_count:
        if owned_apps is None:
            return [(title, aid) for aid, title in all_games_map.items()]
        unowned_count = sum(1 for aid in all_games_map if aid not in owned_apps)
        if unowned_count >= min_unowned_target:
            return [(title, aid) for aid, title in all_games_map.items()]

    # 2. Explorer les pages du magasin Steam
    http_client = session_http if session_http is not None else requests.Session()
    http_client.headers.update(DEFAULT_HEADERS)

    start = (len(all_games_map) // 100) * 100
    step = 100
    consecutive_errors = 0

    while len(all_games_map) < target_count:
        try:
            url = STEAM_SEARCH_URL.format(start=start)
            r = http_client.get(url, timeout=12)

            if r.status_code == 429:
                time.sleep(3)
                consecutive_errors += 1
                if consecutive_errors > 4:
                    break
                continue

            if r.status_code != 200:
                consecutive_errors += 1
                if consecutive_errors > 3:
                    break
                time.sleep(1)
                continue

            consecutive_errors = 0
            appids = re.findall(r'data-ds-appid="(\d+)"', r.text)
            titles = re.findall(r'<span class="title">([^<]+)</span>', r.text)

            if not appids:
                break

            newly_discovered = 0
            for title, aid_str in zip(titles, appids):
                aid = int(aid_str)
                if aid not in all_games_map:
                    all_games_map[aid] = title.strip()
                    newly_discovered += 1

            start += step

            if progress_callback:
                progress_callback(len(all_games_map), target_count)

            # Sauvegarde progressive dans le cache tous les 500 jeux
            if len(all_games_map) % 500 < step:
                try:
                    cache_content = [{"title": t, "appid": a} for a, t in all_games_map.items()]
                    with open(REAL_GAMES_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(cache_content, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            if newly_discovered == 0:
                break

            time.sleep(0.15)
        except Exception:
            consecutive_errors += 1
            if consecutive_errors > 3:
                break
            time.sleep(1)

    # 3. Sauvegarde finale dans le cache
    all_games = [(title, aid) for aid, title in all_games_map.items()]
    try:
        cache_content = [{"title": t, "appid": a} for t, a in all_games]
        with open(REAL_GAMES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_content, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return all_games


def get_unowned_games(
    all_games: List[Tuple[str, int]],
    owned_apps: Set[int],
    progress: Dict = None,
) -> List[Tuple[str, int]]:
    """
    Trie et filtre les jeux pour ne garder STRICTEMENT que les jeux
    que l'utilisateur ne possède PAS encore dans sa bibliothèque Steam Desktop.
    Les jeux qui n'ont pas encore été enregistrés restent dans la liste pour être réessayés lors des prochaines activations.
    """
    already_owned = set(owned_apps)

    unowned = [
        (title, aid)
        for title, aid in all_games
        if aid not in already_owned
    ]
    return unowned
