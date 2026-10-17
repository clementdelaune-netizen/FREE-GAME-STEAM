"""
Application principale en ligne de commande : Steam Auto Free Games Collector.
Scanne un catalogue de plus de 8000 vrais jeux gratuits du magasin Steam, trie strictement ceux
qui ne sont PAS encore dans votre bibliothèque, et les ajoute en direct dans votre client Steam.
"""

import os
import sys
import time
import webbrowser
from typing import Dict, List, Set, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from steam_client import SteamSession, launch_steam, is_steam_running, get_steam_exe
from free_games_db import (
    DEFAULT_CATALOG_TARGET,
    fetch_real_free_games,
    load_progress,
    save_progress,
    sanitize_progress,
    get_unowned_games,
)
from browser_helper import generate_browser_script

console = Console()


def print_banner(session: SteamSession) -> None:
    """Affiche la bannière d'accueil avec les statuts actuels."""
    console.clear()
    steam_status = "[bold green]En cours d'exécution[/bold green]" if is_steam_running() else "[bold yellow]Arrêté[/bold yellow]"
    
    if session.session_id and session.steam_login_secure and session.account_name:
        src = f" ({session.connection_source})" if session.connection_source else ""
        login_status = f"[bold green]Connecté en tant que : {session.account_name}{src}[/bold green]"
    else:
        login_status = "[bold yellow]Non connecté (Détection automatique disponible)[/bold yellow]"

    info_text = (
        f"[bold cyan]🎮 STEAM AUTO FREE GAMES COLLECTOR (Catalogue 8000+ Jeux)[/bold cyan]\n"
        f"[dim]Ajout automatique et vérifié de vrais jeux gratuits à votre bibliothèque Steam Desktop[/dim]\n\n"
        f"• Client Steam Desktop : {steam_status}\n"
        f"• Compte Steam actif   : {login_status}"
    )
    console.print(Panel(info_text, border_style="cyan"))


def menu_launch_steam() -> None:
    """Vérifie ou lance le client Steam."""
    console.print("\n[bold cyan]--- DÉMARRAGE DU CLIENT STEAM ---[/bold cyan]")
    if is_steam_running():
        console.print("[bold green]✔ Le client Steam est déjà ouvert et opérationnel.[/bold green]")
    else:
        console.print("[yellow]Lancement du client Steam en cours...[/yellow]")
        success, msg = launch_steam()
        if success:
            console.print(f"[bold green]✔ {msg}[/bold green]")
        else:
            console.print(f"[bold red]✖ {msg}[/bold red]")
    input("\nAppuyez sur Entrée pour continuer...")


def menu_configure_session(session: SteamSession) -> None:
    """Menu de gestion de session (Détection auto ou manuelle)."""
    console.print("\n[bold cyan]--- GESTION DE LA SESSION STEAM ---[/bold cyan]")
    console.print(
        "  [bold cyan][1][/bold cyan] 🔄 [bold green]Détection 100% automatique[/bold green] (depuis Steam Desktop)\n"
        "  [bold cyan][2][/bold cyan] ✍️ Saisie manuelle des cookies (si besoin)\n"
        "  [bold cyan][3][/bold cyan] 🔙 Retour au menu principal\n"
    )
    sub_choice = Prompt.ask("Votre choix", choices=["1", "2", "3"], default="1")

    if sub_choice == "1":
        console.print("\n[yellow]Recherche automatique de votre session Steam en cours...[/yellow]")
        ok, msg = session.auto_login()
        if ok:
            console.print(f"[bold green]✔ Succès : {msg}[/bold green]")
            console.print(f"[dim]Vous êtes connecté avec le compte : {session.account_name}[/dim]")
        else:
            console.print(f"[bold red]✖ {msg}[/bold red]")

    elif sub_choice == "2":
        console.print("\n[white]Saisie manuelle des cookies (sessionid & steamLoginSecure)[/white]")
        current_sid = session.session_id or ""
        current_sec = session.steam_login_secure or ""
        session_id = Prompt.ask("Collez votre [bold yellow]sessionid[/bold yellow]", default=current_sid).strip()
        steam_login = Prompt.ask("Collez votre [bold yellow]steamLoginSecure[/bold yellow]", default=current_sec).strip()

        if session_id and steam_login:
            session.set_credentials(session_id, steam_login)
            valid, msg = session.validate()
            if valid:
                session.connection_source = "Saisie manuelle"
                session.save()
                console.print(f"[bold green]✔ Succès : {msg}[/bold green]")
            else:
                console.print(f"[bold red]✖ Échec : {msg}[/bold red]")

    input("\nAppuyez sur Entrée pour continuer...")


def scan_and_filter_games(session: SteamSession, min_unowned_needed: int = 50) -> Tuple[List[Tuple[str, int]], Set[int], Dict]:
    """Scanne le catalogue réel (8000 jeux) et filtre les jeux non possédés."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress_bar:
        t1 = progress_bar.add_task("[cyan]Interrogation de votre bibliothèque Steam...", total=None)
        owned_packages, owned_apps = session.get_owned_items()
        progress_bar.remove_task(t1)

        progress_data = load_progress()
        # Assainit l'historique : supprime les ajouts fantômes non réellement possédés
        progress_data = sanitize_progress(progress_data, owned_apps)

        t2 = progress_bar.add_task("[cyan]Chargement du catalogue de 8000 jeux gratuits...", total=None)
        all_games = fetch_real_free_games(
            target_count=DEFAULT_CATALOG_TARGET,
            owned_apps=owned_apps,
            min_unowned_target=min_unowned_needed,
            session_http=session.http,
        )
        progress_bar.remove_task(t2)

    unowned_games = get_unowned_games(all_games, owned_apps, progress_data)
    return unowned_games, owned_apps, progress_data


def menu_scan_games(session: SteamSession) -> None:
    """Affiche le diagnostic complet de la bibliothèque et des jeux à ajouter."""
    console.print("\n[bold cyan]--- SCAN ET DIAGNOSTIC DU CATALOGUE (8000 JEUX) ---[/bold cyan]")
    
    if not session.session_id:
        session.auto_login()

    unowned, owned_apps, progress = scan_and_filter_games(session, min_unowned_needed=50)
    all_catalog = fetch_real_free_games(target_count=DEFAULT_CATALOG_TARGET, session_http=session.http)

    table = Table(title=f"📊 Bibliothèque Steam de {session.account_name or 'votre compte'}", border_style="cyan")
    table.add_column("Indicateur", style="bold white")
    table.add_column("Quantité", justify="right", style="bold green")

    table.add_row("Jeux gratuits du catalogue analysés", str(len(all_catalog)))
    table.add_row("Jeux actuellement dans votre bibliothèque", str(len(owned_apps)))
    table.add_row("Jeux confirmés ajoutés via ce script", str(len(progress.get("added_appids", []))))
    table.add_row("Jeux gratuits NON possédés prêts à être ajoutés (ou réessayés)", f"[bold yellow]{len(unowned)}[/bold yellow]")

    console.print(table)

    if unowned:
        console.print(f"\n[dim]Aperçu des prochains jeux gratuits à ajouter (sur {len(unowned)} disponibles) :[/dim]")
        for title, aid in unowned[:15]:
            console.print(f"  • [bold white]{title}[/bold white] (AppID: [cyan]{aid}[/cyan])")

    input("\nAppuyez sur Entrée pour continuer...")


def menu_add_free_games(session: SteamSession) -> None:
    """Ajoute les jeux gratuits non possédés directement dans le client Steam avec réessai indéfini."""
    console.print("\n[bold cyan]--- AJOUT DIRECT DES JEUX GRATUITS À VOTRE BIBLIOTHÈQUE ---[/bold cyan]")

    # S'assurer que Steam est lancé
    if not is_steam_running():
        console.print("[yellow]Démarrage automatique du client Steam Desktop...[/yellow]")
        launch_steam()
        time.sleep(3)

    unowned, owned_apps_before, progress = scan_and_filter_games(session, min_unowned_needed=50)
    total_unowned = len(unowned)

    if total_unowned == 0:
        console.print("[bold green]🎉 Félicitations : tous les jeux gratuits du catalogue sont déjà dans votre bibliothèque ![/bold green]")
        input("\nAppuyez sur Entrée pour continuer...")
        return

    console.print(f"[bold green]✔ {total_unowned} jeux gratuits non possédés identifiés pour {session.account_name or 'votre compte'}.[/bold green]")
    console.print("\n[bold white]Choisissez votre mode d'activation :[/bold white]")
    console.print("  [bold cyan][1][/bold cyan] 📦 [bold white]Ajouter un lot spécifique[/bold white] (ex: 30, 50, 100 jeux avec réessai indéfini)")
    console.print("  [bold cyan][2][/bold cyan] ⚡ [bold green]MODE CONTINU INFINI[/bold green] (Réessaye indéfiniment et ajoute tout non-stop jusqu'à épuisement)")
    console.print("  [bold cyan][3][/bold cyan] 🔙 Retour au menu principal\n")

    mode = Prompt.ask("Votre choix", choices=["1", "2", "3"], default="1")
    if mode == "3":
        return

    is_continuous = (mode == "2")

    if not is_continuous:
        batch_size = IntPrompt.ask("\nCombien de jeux souhaitez-vous ajouter dans ce lot ?", default=min(30, total_unowned))
        queue = list(unowned[:batch_size])
    else:
        batch_size = 25
        queue = list(unowned)
        console.print("\n[bold green]🚀 Démarrage du MODE CONTINU INFINI : réessai et ajout en boucle non-stop ![/bold green]")
        console.print("[dim]Le script traitera tous les jeux et réessayera indéfiniment ceux qui ne sont pas encore validés.[/dim]")
        console.print("[yellow]Astuce : Vous pouvez appuyer sur Ctrl+C à tout moment pour faire une pause, tous les jeux ajoutés restent sauvegardés.[/yellow]\n")

    attempt_counts: Dict[int, int] = {}
    total_added_session = 0
    pass_number = 1

    try:
        while queue:
            # Sélectionner le sous-lot actif
            current_batch = queue[:batch_size]

            console.print(f"\n[bold cyan]🔄 Passe #{pass_number} : Envoi de l'activation pour {len(current_batch)} jeux...[/bold cyan]")
            console.print(f"[dim]Progression session : {total_added_session} jeux déjà confirmés dans votre bibliothèque Steam[/dim]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress_bar:
                task = progress_bar.add_task("[green]Activation dans Steam Desktop...", total=len(current_batch))

                for title, aid in current_batch:
                    attempt_counts[aid] = attempt_counts.get(aid, 0) + 1
                    session.add_free_game_client(aid)
                    safe_title = (title[:30] + "..") if len(title) > 30 else title
                    progress_bar.update(task, description=f"[green]Tentative #{attempt_counts[aid]} : {safe_title}")
                    progress_bar.advance(task)
                    time.sleep(1.0)

            console.print("\n[yellow]Synchronisation et vérification avec Steam...[/yellow]")
            time.sleep(3)
            _, owned_apps_now = session.get_owned_items()

            new_validated = []
            for title, aid in current_batch:
                if aid in owned_apps_now:
                    new_validated.append((title, aid))
                    if aid not in progress.get("added_appids", []):
                        progress.setdefault("added_appids", []).append(aid)
                        progress.setdefault("added_names", []).append(title)

            if new_validated:
                progress["total_added"] = len(progress.get("added_appids", []))
                save_progress(progress)
                total_added_session += len(new_validated)
                for t, a in new_validated:
                    console.print(f"  [bold green]✔ CONFIRMÉ DANS STEAM :[/bold green] [bold white]{t}[/bold white] (AppID: {a})")

            # Retirer de la file tous les jeux validés
            queue = [g for g in queue if g[1] not in owned_apps_now]

            if not queue:
                console.print("\n[bold green]🎉 TOUS LES JEUX ONT ÉTÉ ENTIÈREMENT VALIDÉS DANS VOTRE BIBLIOTHÈQUE ![/bold green]")
                break

            # S'il reste des jeux non validés dans le lot actuel :
            unvalidated_in_batch = [g for g in current_batch if g[1] not in owned_apps_now]
            if unvalidated_in_batch:
                console.print(
                    f"\n[bold yellow]🔁 {len(unvalidated_in_batch)} jeux n'ont pas encore été enregistrés par Steam.[/bold yellow]\n"
                    f"[yellow]⚡ Réessai indéfini en cours...[/yellow]"
                )

                # Si certains jeux ont déjà été réessayés 3 fois sans succès immédiat
                # et qu'il reste d'autres jeux dans la file :
                # On les place temporairement à la fin de la file pour laisser passer les autres jeux,
                # tout en continuant à les réessayer indéfiniment lors des tours suivants !
                stubborn_games = [g for g in unvalidated_in_batch if attempt_counts.get(g[1], 0) >= 3]
                if stubborn_games and len(queue) > len(stubborn_games):
                    queue = [g for g in queue if g not in stubborn_games] + stubborn_games
                    console.print(f"[dim]ℹ {len(stubborn_games)} jeux temporairement différés en fin de file pour continuer l'ajout des autres titres.[/dim]")

            pass_number += 1
            time.sleep(1.5)

    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]⏹ Opération suspendue par l'utilisateur (Ctrl+C).[/bold yellow]")

    # Résumé de la session
    console.print(
        Panel(
            f"[bold green]📊 BILAN DE LA SESSION D'ACTIVATION[/bold green]\n\n"
            f"• [bold green]Nouveaux jeux réellement ajoutés à Steam :[/bold green] {total_added_session}\n"
            f"• [bold white]Total de vos jeux possédés dans Steam :[/bold white] {len(session.get_owned_items()[1])}\n"
            f"• [bold yellow]Jeux restants à ajouter / réessayer :[/bold yellow] {len(queue)}\n\n"
            f"[dim]Tous vos ajouts ont été enregistrés et sont immédiatement présents dans votre bibliothèque Steam Desktop ![/dim]",
            border_style="green"
        )
    )
    input("\nAppuyez sur Entrée pour continuer...")


def menu_reset_progress() -> None:
    """Réinitialise l'historique d'avancement."""
    console.print("\n[bold red]--- RÉINITIALISATION DE L'AVANCEMENT ---[/bold red]")
    if Confirm.ask("Voulez-vous réinitialiser le fichier de progression (progress.json) ?", default=False):
        if os.path.exists("progress.json"):
            os.remove("progress.json")
            console.print("[bold green]✔ Progression réinitialisée.[/bold green]")
        if os.path.exists("cache/real_free_games.json"):
            os.remove("cache/real_free_games.json")
            console.print("[bold green]✔ Cache des jeux actualisé.[/bold green]")
    input("\nAppuyez sur Entrée pour continuer...")


def main() -> None:
    """Boucle principale de l'application."""
    session = SteamSession()

    # Connexion automatique silencieuse dès le lancement
    if not session.session_id or not session.validate()[0]:
        session.auto_login()

    # Assainit automatiquement progress.json au démarrage si Steam est accessible
    try:
        _, owned_apps = session.get_owned_items()
        if owned_apps:
            p = load_progress()
            sanitize_progress(p, owned_apps)
    except Exception:
        pass

    while True:
        print_banner(session)
        console.print(
            "[bold white]MENU PRINCIPAL :[/bold white]\n"
            "  [bold cyan][1][/bold cyan] 🚀 Lancer / Vérifier le statut de Steam\n"
            "  [bold cyan][2][/bold cyan] 🔑 Gestion de la session Steam (Auto-détection / Manuel)\n"
            "  [bold cyan][3][/bold cyan] 🔍 Scanner le catalogue & trier les jeux non possédés (8000 jeux)\n"
            "  [bold cyan][4][/bold cyan] 🎁 [bold green]Ajouter les jeux gratuits à ma bibliothèque[/bold green]\n"
            "  [bold cyan][5][/bold cyan] 🔄 Réinitialiser la progression et le cache\n"
            "  [bold cyan][6][/bold cyan] ❌ Quitter\n"
        )

        choice = Prompt.ask("[bold yellow]Votre choix[/bold yellow]", choices=["1", "2", "3", "4", "5", "6"], default="4")

        if choice == "1":
            menu_launch_steam()
        elif choice == "2":
            menu_configure_session(session)
        elif choice == "3":
            menu_scan_games(session)
        elif choice == "4":
            menu_add_free_games(session)
        elif choice == "5":
            menu_reset_progress()
        elif choice == "6":
            console.print("\n[bold cyan]Merci d'avoir utilisé Steam Auto Free Games Collector. Bon jeu ![/bold cyan]")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Programme interrompu. À bientôt ![/yellow]")
        sys.exit(0)
