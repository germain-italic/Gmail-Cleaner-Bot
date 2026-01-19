# Gmail Cleaner Bot

Bot automatisé pour nettoyer les emails Gmail selon des règles personnalisées.

## Fonctionnalités

- Suppression/archivage automatique des emails selon des règles
- Filtrage par sujet, expéditeur, destinataire, contenu
- Opérateurs: contient, égal, commence par, finit par, regex
- Condition d'âge (ex: emails de plus de 3 jours)
- TUI (Terminal User Interface) pour gérer les règles
- Logs de toutes les actions effectuées
- Mode dry-run pour tester sans modifier

## Installation

```bash
# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos paramètres
```

## Configuration Google Workspace

1. Créer un projet dans [Google Cloud Console](https://console.cloud.google.com/)
2. Activer l'API Gmail
3. Créer un Service Account avec Domain-Wide Delegation
4. Télécharger la clé JSON et la placer dans `credentials.json`
5. Dans [Google Admin Console](https://admin.google.com/):
   - Security > API Controls > Domain-wide Delegation
   - Ajouter le Client ID du Service Account
   - Scopes requis:
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.readonly`

## Utilisation

### Interface TUI

```bash
./tui.py
# ou
python tui.py
```

Raccourcis clavier:
- `n` - Nouvelle règle
- `r` - Exécuter les règles maintenant
- `t` - Tester la connexion
- `d` - Activer/désactiver le mode dry-run
- `q` - Quitter

### Script en ligne de commande

```bash
# Exécuter le nettoyage
./cleaner.py

# Mode dry-run (ne fait aucune modification)
./cleaner.py --dry-run

# Tester la connexion
./cleaner.py --test
```

### Configuration Cron

```bash
# Éditer le crontab
crontab -e

# Exécuter toutes les heures
0 * * * * /chemin/vers/venv/bin/python /chemin/vers/cleaner.py >> /chemin/vers/logs/cron.log 2>&1

# Ou toutes les 15 minutes
*/15 * * * * /chemin/vers/venv/bin/python /chemin/vers/cleaner.py >> /chemin/vers/logs/cron.log 2>&1
```

## Exemple de règle

Supprimer tous les messages de plus de 3 jours contenant "Host Up" dans le sujet:

| Paramètre | Valeur |
|-----------|--------|
| Name | Cleanup Host Up alerts |
| Field | subject |
| Operator | contains |
| Value | Host Up |
| Action | delete |
| Older than days | 3 |

## Structure du projet

```
gmail-cleaner/
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
| DRY_RUN | Mode simulation | false |
