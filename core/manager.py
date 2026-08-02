import json
import os
from datetime import datetime
import uuid

class SharesManager:
    def __init__(self, filename, history_filename):
        self.filename = filename
        self.history_filename = history_filename
        self.owner_id = os.getenv("OWNER_ID", "Owner")
        self.shares = self.load_shares()
        self.history = self.load_history()

    def load_shares(self):
        if not os.path.exists(self.filename):
            return {self.owner_id: 100.0}
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: float(v) for k, v in data.items()}
        except Exception:
            return {self.owner_id: 100.0}

    def load_history(self):
        if not os.path.exists(self.history_filename):
            return []
        try:
            with open(self.history_filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_shares(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.shares, f, indent=4)

    def save_history(self):
        with open(self.history_filename, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4)

    def get_shares(self):
        return dict(sorted(self.shares.items(), key=lambda item: item[1], reverse=True))

    def log_action(self, action_type, details, executor, contract_id):
        log_entry = {
            "id": contract_id,
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "executor": executor,
            "details": details
        }
        self.history.append(log_entry)
        self.save_history()

    def transfer(self, source: str, target: str, amount: float, executor: str, contract_id: str):
        amount = round(amount, 2)
        if amount <= 0:
            raise ValueError("Le pourcentage doit être supérieur à 0.")
        
        source_share = self.shares.get(source, 0.0)
        if source_share < amount:
            raise ValueError(f"Fonds insuffisants ({source_share:.2f}%).")

        self.shares[source] = round(source_share - amount, 2)
        if self.shares[source] == 0:
            del self.shares[source]

        self.shares[target] = round(self.shares.get(target, 0.0) + amount, 2)
        self.save_shares()
        self.log_action("TRANSFERT", f"{source} a donné {amount:.2f}% à {target}", executor, contract_id)

    def dilute(self, new_member: str, amount: float, executor: str, contract_id: str):
        amount = round(amount, 2)
        if amount <= 0 or amount >= 100:
            raise ValueError("Le pourcentage doit être entre 0 et 100.")
        
        factor = (100.0 - amount) / 100.0
        total_after = 0.0
        
        for member in list(self.shares.keys()):
            new_share = round(self.shares[member] * factor, 2)
            if new_share == 0:
                del self.shares[member]
            else:
                self.shares[member] = new_share
                total_after += new_share
        
        actual_new_share = round(100.0 - total_after, 2)
        self.shares[new_member] = round(self.shares.get(new_member, 0.0) + actual_new_share, 2)
        self.save_shares()
        self.log_action("DILUTION", f"Nouvel actionnaire {new_member} avec {amount:.2f}%", executor, contract_id)

    def reset(self, executor: str):
        self.shares = {self.owner_id: 100.0}
        self.save_shares()
        self.log_action("RESET", "Réinitialisation de la table", executor, str(uuid.uuid4())[:8])

import dotenv
dotenv.load_dotenv()
manager = SharesManager("shares.json", "history.json")
