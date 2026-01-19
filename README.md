# Gmail Cleaner Bot

Bot automatisé pour nettoyer les emails Gmail selon des règles personnalisées.

## Fonctionnalités

- Suppression/archivage automatique des emails selon des règles
- Filtrage par sujet, expéditeur, destinataire, contenu du body, **label**
- Opérateurs: contient, contient (exact), égal, commence par, finit par
- Support regex via checkbox dédiée
- Condition d'âge (ex: emails de plus de 3 jours)
- Pagination automatique (traite jusqu'à 500 messages par règle)
- TUI (Terminal User Interface) pour gérer les règles
- Filtrage des règles en temps réel (vim-like avec `/`)
- Modal d'exécution avec logs en temps réel (sujet, expéditeur, date)
- Indicateur visuel du mode dry-run
- Suivi de la dernière exécution de chaque règle
- Logs de toutes les actions effectuées avec rotation automatique
- Mode dry-run pour tester sans modifier

## Installation

```bash
# Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos paramètres

# Lancer (le venv sera créé automatiquement)
./manage.sh
```

Ou manuellement:

```bash
# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

## Configuration Google Workspace

1. Créer un projet dans [Google Cloud Console](https://console.cloud.google.com/)
2. Activer l'API Gmail
3. Créer un Service Account avec Domain-Wide Delegation
4. Télécharger la clé JSON et la placer dans `credentials.json`
5. Dans [Google Admin Console](https://admin.google.com/):
   - Security > API Controls > Domain-wide Delegation
   - Ajouter le Client ID du Service Account
   - Scope requis:
     - `https://www.googleapis.com/auth/gmail.modify`

## Utilisation

### Interface TUI

```bash
./manage.sh
# ou
./manage.sh tui
```

Raccourcis clavier:
- `/` - Filtrer les règles (vim-like: taper le texte, Enter pour confirmer, Escape pour effacer)
- `n` - Nouvelle règle
- `a` - Exécuter toutes les règles actives
- `s` - Exécuter la règle sélectionnée
- `t` - Tester la connexion Gmail
- `d` - Activer/désactiver le mode dry-run
- `q` - Quitter

L'indicateur jaune "DRY MODE" s'affiche en haut quand le mode simulation est actif.

### Script en ligne de commande

```bash
# Exécuter le nettoyage
./manage.sh run

# Mode dry-run (ne fait aucune modification)
./manage.sh dry

# Tester la connexion
./manage.sh test

# Installer/mettre à jour les dépendances
./manage.sh install
```

### Déploiement serveur (prod)

Sur le serveur de production, un alias est disponible :

```bash
cleangmail        # Lance la TUI
cleangmail run    # Exécute toutes les règles
cleangmail dry    # Dry-run (simulation)
cleangmail test   # Test connexion Gmail
```

**Cron configuré :** tous les jours à 4h00

**Fichiers :** `/var/www/vhosts/gmail-cleaner-bot.example.com/httpdocs/`

### Configuration Cron

```bash
# Éditer le crontab
crontab -e

# Exécuter tous les jours à 4h
0 4 * * * /chemin/vers/manage.sh run >> /chemin/vers/logs/cron.log 2>&1

# Ou toutes les heures
0 * * * * /chemin/vers/manage.sh run >> /chemin/vers/logs/cron.log 2>&1
```

### Cron sur WSL2

Cron ne démarre pas automatiquement sur WSL2. Pour l'activer:

```bash
# Vérifier/démarrer cron
sudo service cron status
sudo service cron start
```

Pour démarrer cron automatiquement, ajouter dans `/etc/wsl.conf`:
```ini
[boot]
command = service cron start
```

**Note:** WSL2 s'arrête après ~8 secondes d'inactivité. Pour que les tâches cron tournent en permanence:
- Garder un terminal WSL ouvert
- Ou utiliser le Task Scheduler Windows pour lancer `wsl -e /chemin/vers/manage.sh run`

## Exemples de règles

### Règle simple
Supprimer tous les messages de plus de 3 jours contenant "Host Up" dans le sujet:

| Paramètre | Valeur |
|-----------|--------|
| Name | Cleanup Host Up alerts |
| Field | subject |
| Operator | contains |
| Value | Host Up |
| Action | delete |
| Older than days | 3 |

### Règle avec regex
Supprimer les notifications Plesk (toutes versions):

| Paramètre | Valeur |
|-----------|--------|
| Name | Plesk Updates |
| Field | subject |
| Regex | ✓ (coché) |
| Value | `Plesk .* Update is Live` |
| Action | delete |
| Older than days | 7 |

**Note regex:** `.*` signifie "n'importe quels caractères". Le pattern ci-dessus matche "Plesk Obsidian 18.0.74 Update is Live".

### Règle par label
Supprimer tous les messages avec le label "Notifications" de plus de 30 jours:

| Paramètre | Valeur |
|-----------|--------|
| Name | Cleanup old notifications |
| Field | label |
| Operator | equals |
| Value | Notifications |
| Action | delete |
| Older than days | 30 |

**Note:** Utiliser le nom du label tel qu'il apparaît dans Gmail (ex: "Transaid - Feraid") ou le slug technique (ex: "transaid---feraid"). Les deux formats fonctionnent.

## Structure du projet

```
gmail-cleaner/
├── manage.sh           # Script de gestion (point d'entrée)
├── cleaner.py          # Script principal (cron)
├── tui.py              # Interface terminal
├── src/
│   ├── config.py       # Configuration
│   ├── database.py     # Modèles et base SQLite
│   ├── gmail_client.py # Client API Gmail
│   └── rules_engine.py # Moteur de règles
├── data/               # Base de données SQLite
├── logs/               # Fichiers de logs
├── .env                # Configuration (non versionné)
└── credentials.json    # Clé Service Account (non versionné)
```

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| GOOGLE_CREDENTIALS_PATH | Chemin vers credentials.json | ./credentials.json |
| GMAIL_USER_EMAIL | Email à impersonner | (requis) |
| DATABASE_PATH | Chemin base SQLite | ./data/gmail_cleaner.db |
| LOG_PATH | Dossier des logs | ./logs |
| LOG_LEVEL | Niveau de log | INFO |
| LOG_MAX_SIZE | Taille max du log avant rotation (octets) | 5242880 (5 MB) |
| LOG_BACKUP_COUNT | Nombre de fichiers de backup | 3 |
| DRY_RUN | Mode simulation | false |
| MAX_SEARCH_RESULTS | Messages max par règle | 500 |
| PYTHON_PATH | Chemin vers Python | (auto-détecté) |
| SMTP_ENABLED | Activer l'envoi de rapport par email | false |
| SMTP_HOST | Serveur SMTP | (requis si SMTP_ENABLED) |
| SMTP_PORT | Port SMTP | 587 |
| SMTP_USER | Utilisateur SMTP | (requis si SMTP_ENABLED) |
| SMTP_PASSWORD | Mot de passe SMTP | (requis si SMTP_ENABLED) |
| SMTP_FROM | Adresse expéditeur | (requis si SMTP_ENABLED) |
| SMTP_TO | Adresse destinataire | (requis si SMTP_ENABLED) |
| SMTP_TLS | Utiliser STARTTLS | true |

## Rapport par email

Quand `SMTP_ENABLED=true`, un rapport est envoyé par email après l'exécution via `cleaner.py`.

**Quand le rapport est envoyé :**
| Commande | Email envoyé |
|----------|--------------|
| `manage.sh run` | ✅ Oui |
| `manage.sh dry` | ✅ Oui |
| Cron | ✅ Oui |
| TUI (Run All / Run Selected) | ❌ Non |

**Contenu du rapport :**
- Date et mode d'exécution (LIVE/DRY RUN)
- Nombre de règles traitées
- Messages trouvés, actions réussies/échouées

**Exemple de sujet :**
- `[Gmail Cleaner] Rapport du 2024-01-20 04:00 - Aucune action`
- `[Gmail Cleaner] Rapport du 2024-01-20 04:00 - 2 erreur(s)`

## Rotation des logs

La rotation des logs est gérée automatiquement par l'application (pas besoin de `logrotate`).

**Fonctionnement :**
- Quand `cleaner.log` atteint la taille max (`LOG_MAX_SIZE`) → renommé en `cleaner.log.1`
- Les anciens backups sont décalés (`.1` → `.2` → `.3`)
- Le plus ancien est supprimé quand le nombre dépasse `LOG_BACKUP_COUNT`
- Un nouveau `cleaner.log` vide est créé

**Exemple avec les valeurs par défaut :**
```
logs/
├── cleaner.log       # Fichier actif (max 5 MB)
├── cleaner.log.1     # Backup le plus récent
├── cleaner.log.2     # Backup intermédiaire
└── cleaner.log.3     # Backup le plus ancien (supprimé à la prochaine rotation)
```
