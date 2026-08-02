# Bot Discord - Répartition des Parts (Ondura)

Ce bot permet de gérer la répartition des parts (equity) pour un projet via des commandes Discord.
Les données sont sauvegardées localement dans le fichier `shares.json`.

## Prérequis

- Python 3.8 ou supérieur
- Pip

## Installation

1. Clonez ce dépôt ou copiez les fichiers dans votre répertoire.
2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Ouvrez le fichier `bot.py` et modifiez la variable `TOKEN` avec le token de votre bot Discord. 
   *(Optionnel)* : Vous pouvez aussi définir `GUILD_ID` avec l'ID de votre serveur pour que les commandes slash se synchronisent instantanément sur ce serveur spécifique.

## Lancement

Pour un test en local, exécutez simplement :
```bash
python3 bot.py
```

## Lancement en arrière-plan sur un serveur Linux

Pour que le bot tourne H24 sur un VPS, vous avez deux options recommandées : PM2 ou Systemd.

### Option 1 : Avec PM2 (Recommandé, le plus simple)

PM2 est un gestionnaire de processus très pratique. Il nécessite Node.js installé.

1. Installez PM2 (si non installé) :
   ```bash
   npm install -g pm2
   ```
2. Lancez le bot via PM2 :
   ```bash
   pm2 start bot.py --name "ondura-bot" --interpreter python3
   ```
3. Sauvegardez PM2 pour qu'il se relance au redémarrage du serveur :
   ```bash
   pm2 save
   pm2 startup
   ```

*(Commandes utiles : `pm2 logs ondura-bot` pour voir les logs, `pm2 restart ondura-bot` pour redémarrer)*

### Option 2 : Avec Systemd (Natif sur Linux)

1. Créez un fichier de service systemd :
   ```bash
   sudo nano /etc/systemd/system/ondura-bot.service
   ```
2. Ajoutez ce contenu (en modifiant les chemins `/chemin/vers/...` avec vos vrais chemins) :
   ```ini
   [Unit]
   Description=Bot Discord Ondura
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/chemin/vers/bot-parts
   ExecStart=/usr/bin/python3 /chemin/vers/bot-parts/bot.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Rechargez systemd, activez et lancez le service :
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ondura-bot
   sudo systemctl start ondura-bot
   ```

*(Commande utile : `sudo journalctl -u ondura-bot -f` pour voir les logs en temps réel)*
