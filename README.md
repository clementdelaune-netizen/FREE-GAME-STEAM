# 🎮 Steam Auto Free Games Collector

Un programme d'automatisation complet en Python pour :
1. **🚀 Lancer Steam Desktop** s'il n'est pas déjà ouvert.
2. **🔑 Se connecter automatiquement** : si Steam est déjà connecté sur votre PC, aucune saisie de mot de passe ni de cookies n'est nécessaire.
3. **🔍 Scanner le catalogue officiel des jeux gratuits du magasin Steam (plus de 8000 jeux)**.
4. **🎯 Filtrer strictement les jeux gratuits que vous ne possédez PAS encore**.
5. **🎁 Réessai indéfini et Mode Continu Infini** : réessaye indéfiniment en boucle tous les jeux qui n'ont pas encore été validés par Steam, avec rotation intelligente pour ne jamais bloquer la file et possibilité de tout ajouter non-stop.

---

## 🚀 Démarrage Rapide

### Option 1 : En 1 clic (Windows)
Double-cliquez simplement sur :
👉 **`lancer_steam_free.bat`**

### Option 2 : Via le Terminal
```bash
python main.py
```

---

## 📋 Menu Principal

```text
======================================================================
  STEAM AUTO FREE GAMES COLLECTOR
  • Client Steam Desktop : En cours d'exécution
  • Compte Steam actif   : Connecté en tant que : chouchou14270
======================================================================

[1] 🚀 Lancer / Vérifier le statut de Steam
[2] 🔑 Gestion de la session Steam (Auto-détection / Manuel)
[3] 🔍 Scanner le catalogue & trier les jeux non possédés
[4] 🎁 Ajouter les jeux gratuits à ma bibliothèque
[5] 🔄 Réinitialiser la progression et le cache
[6] ❌ Quitter
```

---

## 💡 Pourquoi les anciens scripts ajoutaient "0 jeux" ?

- Les anciens outils utilisaient une vieille liste de packages créés il y a plusieurs années, dont 98% sont désormais expirés ou supprimés du magasin Steam.
- **Cette nouvelle version interroge directement le catalogue en direct du Steam Store** : elle identifie les vrais jeux gratuits actifs (ex: *Dota 2, Lost Ark, Persona5, Dark and Darker, Reverse: 1999, etc.*) et les enregistre directement dans votre bibliothèque via le client Steam !
