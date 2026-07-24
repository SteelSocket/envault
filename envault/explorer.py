from imgui_bundle import imgui
from pathlib import Path
from collections import defaultdict

import shutil
import requests

from envault.vault import VaultDB
from envault.common import (
    PopupManager,
    exception_dialog,
    get_clipboard_bytes,
    set_clipboard_bytes,
)


class Explorer:
    VAULT_OPEN = "Open Vault"
    VAULT_SAVE_AS = "Save As"
    VAULT_EXIT = "Exit Vault"
    FILE_ADD = "Add File"
    FILE_REMOVE = "Remove File"
    FILE_RENAME = "Rename File"
    FILE_EXTRACT = "Extract File"

    def __init__(self, file_select_cb):
        self.pm = PopupManager()

        self._vault = None
        self._selected_file = None
        self._cb = file_select_cb

        self._popup_add_type = 0

    def __move_selected(self, delta: int):
        if self._vault is None:
            return

        files = self._vault.get_files()
        if not files:
            return

        if self._selected_file is None:
            idx = 0
        else:
            idx = (files.index(self._selected_file) + delta) % len(files)

        self._selected_file = files[idx]
        self._cb(self._vault.read_file(self._selected_file))

    def __handle_hotkeys(self):
        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.o, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.VAULT_OPEN)
        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.s, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.VAULT_SAVE_AS)
        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.q, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.VAULT_EXIT)
        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.n, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.FILE_ADD)
        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.d, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.FILE_REMOVE)

        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.r, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.FILE_RENAME)

        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.e, imgui.InputFlags_.route_global
        ):
            self.pm.show(self.FILE_EXTRACT)

        if imgui.is_window_focused():
            if imgui.is_key_pressed(imgui.Key.left_arrow) or imgui.is_key_pressed(
                imgui.Key.up_arrow
            ):
                self.__move_selected(-1)

            elif imgui.is_key_pressed(imgui.Key.right_arrow) or imgui.is_key_pressed(
                imgui.Key.down_arrow
            ):
                self.__move_selected(1)

    def __draw_menu(self):
        if not imgui.begin_menu_bar():
            return

        if imgui.begin_menu("Vault"):
            if imgui.menu_item_simple("Open", "Ctrl+O"):
                print("Open")
                self.pm.show(self.VAULT_OPEN)

            if imgui.menu_item_simple(
                "Save As", "Ctrl+S", enabled=not self._vault is None
            ):
                print("Save As")
                self.pm.show(self.VAULT_SAVE_AS)

            imgui.separator()

            if imgui.menu_item_simple(
                "Exit", "Ctrl+Q", enabled=not self._vault is None
            ):
                print("Exit")
                self.pm.show(self.VAULT_EXIT)

            imgui.end_menu()

        if imgui.begin_menu("File", enabled=not self._vault is None):
            if imgui.menu_item_simple("Add", "Ctrl+N"):
                print("Add")
                self.pm.show(self.FILE_ADD)

            if imgui.menu_item_simple("Remove", "Ctrl+D"):
                print("Remove")
                self.pm.show(self.FILE_REMOVE)

            if imgui.menu_item_simple("Rename", "Ctrl+R"):
                print("Rename")
                self.pm.show(self.FILE_RENAME)

            if imgui.menu_item_simple("Extract", "Ctrl+E"):
                print("Extract")
                self.pm.show(self.FILE_EXTRACT)

            imgui.end_menu()

        imgui.end_menu_bar()

    def __draw_popups(self):
        if self.pm.begin(self.VAULT_OPEN):
            self.pm.add_path_input("Vault Path")
            self.pm.add_text_input(
                "Vault Password", flags=imgui.InputTextFlags_.password
            )
            status, result = self.pm.end()

            if status == PopupManager.POPUP_SUBMIT:
                with exception_dialog():
                    self.open_vault(result["Vault Path"], result["Vault Password"])

        elif self.pm.begin(self.VAULT_SAVE_AS):
            self.pm.add_path_input("Vault Path")
            status, result = self.pm.end()

            if status == PopupManager.POPUP_SUBMIT:
                with exception_dialog():
                    self.vault_save_as(result["Vault Path"])

        elif self.pm.begin(self.VAULT_EXIT):
            imgui.text("Confirm to exit the Vault?")

            status, result = self.pm.end()
            if status == PopupManager.POPUP_SUBMIT:
                assert not self._vault is None
                self._vault.close()
                self._vault = None

        elif self.pm.begin(self.FILE_ADD):
            atype = self.pm.add_radio_buttons(
                "Add Type", ["File", "Clipboard", "URL"], "File"
            )
            self.pm.add_text_input("Internal Path")

            if atype == "File":
                self.pm.add_path_input("File Path")
            elif atype == "URL":
                self.pm.add_text_input("Url")

            status, result = self.pm.end()
            if status == PopupManager.POPUP_SUBMIT:
                assert not self._vault is None

                ipath = Path(result["Internal Path"])

                if atype == "File":
                    fpath = Path(result["File Path"])
                    with exception_dialog():
                        self._vault.add_file(ipath, fpath.read_bytes())

                elif atype == "Clipboard":
                    data = get_clipboard_bytes()
                    with exception_dialog():
                        if isinstance(data, bytes):
                            self._vault.add_file(ipath, data)
                        else:
                            raise RuntimeError("Clipboard does not contain any data")

                elif atype == "URL":
                    url = result["Url"]
                    response = requests.get(url)

                    with exception_dialog():
                        response.raise_for_status()
                        self._vault.add_file(ipath, response.content)

        elif self.pm.begin(self.FILE_REMOVE):
            self.pm.add_text_input("Internal Path")

            status, result = self.pm.end()
            if status == PopupManager.POPUP_SUBMIT:
                assert not self._vault is None
                with exception_dialog():
                    path = Path(result["Internal Path"])
                    self._vault.remove_file(path)
                    if self._selected_file == path:
                        self._selected_file = None

        elif self.pm.begin(self.FILE_RENAME):
            self.pm.add_text_input("Source Path")
            self.pm.add_text_input("Destination Path")

            status, result = self.pm.end()
            if status == PopupManager.POPUP_SUBMIT:
                assert not self._vault is None
                with exception_dialog():
                    src = Path(result["Source Path"])
                    dst = Path(result["Destination Path"])
                    self._vault.rename_file(src, dst)

        elif self.pm.begin(self.FILE_EXTRACT):
            atype = self.pm.add_radio_buttons(
                "Extract Type", ["File", "Clipboard"], "File"
            )
            self.pm.add_text_input("Internal Path")
            if atype == "File":
                self.pm.add_path_input("File Path")

            status, result = self.pm.end()
            if status == PopupManager.POPUP_SUBMIT:
                assert not self._vault is None
                path = Path(result["Internal Path"])

                with exception_dialog():
                    if not path in self._vault.get_files():
                        raise RuntimeError("Given Internal Path does not exists")

                    contents = self._vault.read_file(path)
                    if atype == "File":
                        fpath = Path(result["File Path"])
                        fpath.mkdir(parents=True, exist_ok=True)
                        fpath.write_bytes(contents)
                    elif atype == "Clipboard":
                        set_clipboard_bytes(contents)

    def __draw_file_tree(self):
        if self._vault is None:
            return
        files = self._vault.get_files()
        dir_files = defaultdict(lambda: [])
        for file in files:
            dir_files[file.parent].append(file)

        for dir, files in dir_files.items():
            opened = imgui.tree_node(dir.as_posix())

            if imgui.begin_popup_context_item():
                if imgui.menu_item_simple("Add"):
                    self.pm.set_value(
                        self.FILE_ADD, "Internal Path", dir.as_posix() + "/"
                    )
                    self.pm.show(self.FILE_ADD)
                imgui.end_popup()

            if not opened:
                continue

            for file in files:
                clicked, _ = imgui.selectable(
                    file.name, p_selected=(self._selected_file == file)
                )
                if clicked:
                    self._selected_file = file
                    self._cb(self._vault.read_file(file))

                if imgui.begin_popup_context_item():
                    if imgui.menu_item_simple("Remove"):
                        self.pm.set_value(
                            self.FILE_REMOVE, "Internal Path", file.as_posix()
                        )
                        self.pm.show(self.FILE_REMOVE)

                    if imgui.menu_item_simple("Rename"):
                        self.pm.set_value(
                            self.FILE_RENAME, "Source Path", file.as_posix()
                        )
                        self.pm.show(self.FILE_RENAME)

                    if imgui.menu_item_simple("Extract"):
                        self.pm.set_value(
                            self.FILE_EXTRACT, "Internal Path", file.as_posix()
                        )
                        self.pm.show(self.FILE_EXTRACT)

                    imgui.end_popup()
            imgui.tree_pop()

    def draw(self):
        imgui.begin("Explorer", flags=imgui.WindowFlags_.menu_bar)

        self.__handle_hotkeys()
        self.__draw_menu()
        self.__draw_file_tree()
        self.__draw_popups()

        imgui.end()

    def open_vault(self, path: str, password: str):
        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")
        self._vault = VaultDB(vpath, password)

    def vault_save_as(self, path: str):
        assert not self._vault is None

        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")

        shutil.copy2(self._vault.path, path)
