from dataclasses import dataclass
from pathlib import Path

from envault.common import PopupManager
from envault.vault import VaultDB


@dataclass()
class AppContext:
    vault: VaultDB | None = None
    selected_file: Path | None = None
    pm: PopupManager = PopupManager()
