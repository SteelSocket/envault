from imgui_bundle import imgui, icons_fontawesome_6 as ifa
from pathlib import Path

import re
import shutil

from envault.context import AppContext
from envault.vault import VaultDB
from envault.common import (
    center_text,
    toggle_button,
    exception_dialog,
    menu_item_full,
    next_string_number,
    path_to_label,
)


def is_subpath(subpath: Path, path: Path) -> bool:
    try:
        subpath.relative_to(path)
        return True
    except ValueError:
        return False


class Explorer:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

        self._renaming_path: Path | None = None
        self._rename_buffer = ""
        self._rename_started = False

        self._uncollapse_path: Path | None = None

        self._search_text: str = ""
        self._search_regex: bool = False
        self._search_case: bool = False

        self._shortcut_move: int = 0

    @property
    def _vault_exists(self):
        return not self.ctx.vault is None

    def _on_open_vault(self, submitted: bool, states: dict):
        if not submitted:
            return True

        with exception_dialog() as success:
            self.open_vault(states["Vault Path"], states["Password"])

        return success.ok

    def _on_exit_vault(self, submitted: bool, _):
        if not submitted:
            return True
        assert not self.ctx.vault is None

        self.ctx.vault.close()
        self.ctx.vault = None
        self.ctx.selected_file = None
        return True

    def _on_save_vault(self, submitted: bool, states: dict):
        if not submitted:
            return True

        with exception_dialog() as success:
            self.vault_save_as(states["Save File"])

        return success.ok

    def _on_file_delete(self, is_file: bool, path: Path, submitted: bool, _: dict):
        if not submitted:
            return True
        assert self.ctx.vault

        with exception_dialog() as success:
            if is_file:
                self.ctx.vault.remove_file(path)
                if self.ctx.selected_file == path:
                    self.ctx.selected_file = None
            else:
                self.ctx.vault.remove_directory(path)

        return success.ok

    def __file_name_filter(self, data: imgui.InputTextCallbackData):
        c = chr(data.event_char)
        if ord(c) < 32 or c in '/\\:*?"<>|':
            return 1
        return 0

    def __draw_rename(self) -> bool:
        imgui.set_next_item_width(-1)

        if not self._rename_started:
            self._rename_started = True
            imgui.set_keyboard_focus_here()

        finished, self._rename_buffer = imgui.input_text(
            "##rename",
            self._rename_buffer,
            imgui.InputTextFlags_.enter_returns_true
            | imgui.InputTextFlags_.auto_select_all
            | imgui.InputTextFlags_.callback_char_filter,
            self.__file_name_filter,
        )

        if finished:
            self._renaming_path = None
            self._rename_started = False
            return True

        if not imgui.is_item_active() and imgui.is_mouse_clicked(0):
            self._renaming_path = None
            self._rename_started = False
            return True

        return False

    def __draw_window_ctx_menu(self):
        if self.ctx.vault is None:
            return

        if imgui.begin_popup_context_window(
            "window_context",
            imgui.PopupFlags_.no_open_over_existing_popup,
        ):
            if imgui.menu_item_simple(ifa.ICON_FA_FOLDER_PLUS + " New Folder"):
                self.add_new_directory(Path("/"))

            if imgui.menu_item_simple(ifa.ICON_FA_FILE_CIRCLE_PLUS + " New File"):
                self.add_new_file(Path("/"))

            imgui.end_popup()

    def __draw_file_ctx_menu(self, root: Path, is_file: bool):
        if self.ctx.vault is None:
            return

        if imgui.begin_popup_context_item(
            (root.as_posix() + "_context"),
            imgui.PopupFlags_.no_open_over_items
            | imgui.PopupFlags_.no_open_over_existing_popup,
        ):
            if imgui.menu_item_simple(ifa.ICON_FA_FOLDER_PLUS + " New Folder"):
                self.add_new_directory(root.parent if is_file else root)

            if imgui.menu_item_simple(ifa.ICON_FA_FILE_CIRCLE_PLUS + " New File"):
                self.add_new_file(root.parent if is_file else root)

            imgui.separator()

            if imgui.menu_item_simple(ifa.ICON_FA_FILE_PEN + " Rename"):
                self._renaming_path = root
                self._rename_buffer = root.name

            if is_file and imgui.menu_item_simple(ifa.ICON_FA_COPY + " Duplicate"):
                self.add_duplicate_file(root)

            if imgui.menu_item_simple(ifa.ICON_FA_FILE_CIRCLE_MINUS + " Delete"):
                self.ctx.pm.begin("Delete File").add_custom_input(
                    imgui.text, "Do you want to perminantly delete the file?"
                ).set_result_cb(lambda x, y: self._on_file_delete(is_file, root, x, y))

            imgui.end_popup()

    def __draw_tree(self, node):
        if self.ctx.vault is None:
            return

        for directory in sorted(k for k in node if k is not None):
            if self._renaming_path == directory:
                if self.__draw_rename():
                    self.ctx.vault.rename_directory(directory, self._rename_buffer)
            else:
                if not self._uncollapse_path is None:
                    if self._uncollapse_path == Path("/"):
                        self._uncollapse_path = None
                    elif is_subpath(directory, self._uncollapse_path):
                        imgui.set_next_item_open(True)

                    if directory == self._uncollapse_path:
                        self._uncollapse_path = None

                opened = imgui.tree_node_ex(path_to_label(directory, "tree"))

                if imgui.is_item_clicked() and imgui.is_mouse_double_clicked(0):
                    self._renaming_path = directory
                    self._rename_buffer = directory.name

                self.__draw_file_ctx_menu(directory, False)

                # File Move Destination - Directory
                if imgui.begin_drag_drop_target():
                    payload = imgui.accept_drag_drop_payload_py_id("str")
                    if payload:
                        file = self.ctx.vault.get_file_by_rowid(payload.data_id)
                        self.ctx.vault.move_file(file, directory)

                    imgui.end_drag_drop_target()

                if opened:
                    self.__draw_tree(node[directory])
                    imgui.tree_pop()

        for file in sorted(node.get(None, [])):
            if self._renaming_path == file:
                if self.__draw_rename():
                    self.ctx.vault.rename_file(
                        file,
                        self._rename_buffer,
                    )
                    if self.ctx.selected_file and self.ctx.selected_file == file:
                        self.ctx.selected_file = (
                            self.ctx.selected_file.parent / self._rename_buffer
                        )

            else:
                flags = (
                    imgui.TreeNodeFlags_.leaf
                    | imgui.TreeNodeFlags_.no_tree_push_on_open
                    | imgui.TreeNodeFlags_.span_full_width
                )

                if self.ctx.selected_file == file:
                    flags |= imgui.TreeNodeFlags_.selected

                imgui.tree_node_ex(path_to_label(file, "file"), flags)

                if imgui.is_item_clicked() or imgui.is_item_activated():
                    self.ctx.selected_file = file

                if imgui.is_item_clicked() and imgui.is_mouse_double_clicked(0):
                    self._renaming_path = file
                    self._rename_buffer = file.name

                # File Move Source
                if imgui.begin_drag_drop_source():
                    imgui.set_drag_drop_payload_py_id(
                        "str", self.ctx.vault.get_rowid_by_file(file)
                    )
                    imgui.text(file.name)
                    imgui.end_drag_drop_source()

                self.__draw_file_ctx_menu(file, True)

    def __filter_files(self, files: list):
        if self._search_text == "":
            return files

        if self._search_regex:
            return [
                x
                for x in files
                if re.search(
                    self._search_text, x.name, 0 if self._search_case else re.IGNORECASE
                )
            ]

        if self._search_case:
            return [x for x in files if x.name.startswith(self._search_text)]

        return [
            x
            for x in files
            if x.name.casefold().startswith(self._search_text.casefold())
        ]

    def __draw_file_tree(self):
        if self.ctx.vault is None:
            return
        tree = {}

        dirs = self.ctx.vault.get_all_directories()
        if not self._search_text:
            for directory in dirs:
                node = tree
                current = Path("")

                for part in directory.parts:
                    current /= part
                    node = node.setdefault(current, {})
        elif self._renaming_path in dirs:
            node = tree
            current = Path("")

            for part in self._renaming_path.parts:
                current /= part
                node = node.setdefault(current, {})

        files = self.ctx.vault.get_all_files()
        filtered = self.__filter_files(files)

        if self._renaming_path in files and not self._renaming_path in filtered:
            filtered.append(self._renaming_path)

        for file in filtered:
            node = tree
            current = Path("")

            for part in file.parts[:-1]:
                current /= part
                node = node.setdefault(current, {})

            node.setdefault(None, []).append(file)

        if self._shortcut_move:
            if self.ctx.selected_file in files:
                idx = (files.index(self.ctx.selected_file) + self._shortcut_move) % len(
                    files
                )
                self.ctx.selected_file = files[idx]
                self._uncollapse_path = files[idx].parent
            self._shortcut_move = 0

        if tree.get(Path("/"), {}):
            self.__draw_tree(tree[Path("/")])

        avail = imgui.get_content_region_avail()

        imgui.begin_child(
            "##root_file_drop",
            avail,
            child_flags=imgui.ChildFlags_.nav_flattened,
            window_flags=0,
        )

        self.__draw_window_ctx_menu()

        region = imgui.get_content_region_avail()
        imgui.invisible_button("##drop_target", region)

        if imgui.begin_drag_drop_target():
            payload = imgui.accept_drag_drop_payload_py_id("str")
            if payload:
                file = self.ctx.vault.get_file_by_rowid(payload.data_id)
                self.ctx.vault.move_file(file, Path("/"))
            imgui.end_drag_drop_target()

        if len(tree.get(Path("/"), {})) == 0:
            center_text("Right Click to add files and directories")

        imgui.end_child()

    def __draw_search_bar(self):
        toggle_size = imgui.calc_text_size("aA")
        toggle_size.y += 2

        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 0.0)

        self._search_case = toggle_button("aA", self._search_case)
        imgui.set_item_tooltip("Toogle Case Sensitivity")
        imgui.same_line(0, 0)

        self._search_regex = toggle_button("(.*)", self._search_regex)
        imgui.set_item_tooltip("Toogle Regex Search")
        imgui.same_line(0, 0)

        imgui.set_next_item_width(-1)
        self._search_text = imgui.input_text("##Search Bar", self._search_text)[1]
        imgui.pop_style_var()

    def __draw_menu(self):
        if not imgui.begin_menu_bar():
            return

        imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 2)

        if (
            menu_item_full(
                ifa.ICON_FA_VAULT,
                True,
                "Open Vault",
                imgui.Key.o | imgui.Key.mod_ctrl,
                imgui.InputFlags_.route_global,
            )
            and not self.ctx.pm.is_active()
        ):
            (
                self.ctx.pm.begin("Open")
                .add_path_input("Vault Path")
                .add_text_input("Password", flags=imgui.InputTextFlags_.password)
                .set_result_cb(self._on_open_vault)
            )

        if (
            menu_item_full(
                ifa.ICON_FA_CIRCLE_XMARK,
                self._vault_exists,
                "Exit Vault",
                imgui.Key.q | imgui.Key.mod_ctrl,
                imgui.InputFlags_.route_global,
            )
            and not self.ctx.pm.is_active()
        ):
            (
                self.ctx.pm.begin("Exit")
                .add_custom_input(
                    imgui.text, "Are you sure you want to exit the vault?"
                )
                .set_result_cb(self._on_exit_vault)
            )

        if (
            menu_item_full(
                ifa.ICON_FA_FLOPPY_DISK,
                self._vault_exists,
                "Save Vault As",
                imgui.Key.s | imgui.Key.mod_shift | imgui.Key.mod_ctrl,
                imgui.InputFlags_.route_global,
            )
            and not self.ctx.pm.is_active()
        ):
            (
                self.ctx.pm.begin("Save As")
                .add_path_input("Save File", "vault.evlt")
                .set_result_cb(self._on_save_vault)
            )

        imgui.end_menu_bar()

    def __handle_shortcuts(self):
        if (
            self.ctx.vault is None
            or self.ctx.selected_file is None
            or imgui.get_io().nav_visible
        ):
            return

        if imgui.shortcut(imgui.Key.up_arrow):
            self._shortcut_move = -1

        if imgui.shortcut(imgui.Key.down_arrow):
            self._shortcut_move = 1

    def draw(self):
        if imgui.begin(
            "Explorer",
            flags=imgui.WindowFlags_.menu_bar,
        )[0]:
            self.__handle_shortcuts()
            self.__draw_menu()
            self.__draw_search_bar()
            self.__draw_file_tree()

        imgui.end()

    def open_vault(self, path: str, password: str):
        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")

        if not self.ctx.vault is None:
            self.ctx.vault.close()

        try:
            self.ctx.vault = VaultDB(vpath, password)
        except:
            raise RuntimeError("Wrong Password!")

    def vault_save_as(self, path: str):
        assert not self.ctx.vault is None

        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")

        shutil.copy2(self.ctx.vault.path, path)

    def add_new_file(self, root: Path):
        assert not self.ctx.vault is None

        existing = self.ctx.vault.get_files(root)
        name = next_string_number(
            "New File", [e.relative_to(root).as_posix() for e in existing]
        )

        file = root / Path(name)
        self.ctx.vault.add_file(file, b"")
        self._renaming_path = file
        self._rename_buffer = file.name
        self._uncollapse_path = root

    def add_new_directory(self, root: Path):
        assert not self.ctx.vault is None

        existing = self.ctx.vault.get_directories(root)
        name = next_string_number(
            "New Folder", [e.relative_to(root).as_posix() for e in existing]
        )

        dir = root / Path(name)
        self.ctx.vault.add_directory(dir)
        self._renaming_path = dir
        self._rename_buffer = dir.name
        self._uncollapse_path = root

    def add_duplicate_file(self, file: Path):
        assert not self.ctx.vault is None

        existing = self.ctx.vault.get_files(file.parent)
        name = next_string_number(
            file.name + " Copy",
            [e.relative_to(file.parent).as_posix() for e in existing],
        )

        dfile = file.parent / Path(name)
        self.ctx.vault.copy_file(file, name)
        self._renaming_path = dfile
        self._rename_buffer = dfile.name
        self._uncollapse_path = dfile
