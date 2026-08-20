from imgui_bundle import imgui, icons_fontawesome_6 as ifa
from pathlib import Path

import shutil

from envault.context import AppContext
from envault.vault import VaultDB
from envault.common import (
    center_text,
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

    def __draw_file_tree(self):
        if self.ctx.vault is None:
            return
        tree = {}

        dirs = self.ctx.vault.get_all_directories()
        for directory in dirs:
            node = tree
            current = Path("")

            for part in directory.parts:
                current /= part
                node = node.setdefault(current, {})

        files = self.ctx.vault.get_all_files()
        for file in files:
            node = tree
            current = Path("")

            for part in file.parts[:-1]:
                current /= part
                node = node.setdefault(current, {})

            node.setdefault(None, []).append(file)

        if tree.get(Path("/"), {}):
            self.__draw_tree(tree[Path("/")])

        avail = imgui.get_content_region_avail()

        imgui.begin_child(
            "##root_file_drop",
            avail,
            child_flags=0,
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

    def __draw_tree(self, node):
        if self.ctx.vault is None:
            return

        for directory in sorted(k for k in node if k is not None):
            if self._renaming_path == directory:
                if self.__draw_rename():
                    self.ctx.vault.rename_directory(directory, self._rename_buffer)
            else:
                if not self._uncollapse_path is None:
                    if is_subpath(directory, self._uncollapse_path):
                        imgui.set_next_item_open(True)

                    if (
                        directory == self._uncollapse_path
                        or self._uncollapse_path == Path("/")
                    ):
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

            else:
                flags = (
                    imgui.TreeNodeFlags_.leaf
                    | imgui.TreeNodeFlags_.no_tree_push_on_open
                    | imgui.TreeNodeFlags_.span_full_width
                )

                if self.ctx.selected_file == file:
                    flags |= imgui.TreeNodeFlags_.selected

                imgui.tree_node_ex(path_to_label(file, "file"), flags)

                if imgui.is_item_clicked():
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

    def __draw_rename(self) -> bool:
        imgui.set_next_item_width(-1)

        if not self._rename_started:
            self._rename_started = True
            imgui.set_keyboard_focus_here()

        finished, self._rename_buffer = imgui.input_text(
            "##rename",
            self._rename_buffer,
            imgui.InputTextFlags_.enter_returns_true
            | imgui.InputTextFlags_.auto_select_all,
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
                .add_path_input("Destination", "vault.evlt")
                .set_result_cb(self._on_save_vault)
            )

        imgui.end_menu_bar()

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
                if is_file:
                    self.ctx.vault.remove_file(root)
                    if self.ctx.selected_file == root:
                        self.ctx.selected_file = None
                else:
                    self.ctx.vault.remove_directory(root)

            imgui.end_popup()

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

    @property
    def _vault_exists(self):
        return not self.ctx.vault is None

    def _on_open_vault(self, submitted: bool, states: dict):
        if not submitted:
            return
        with exception_dialog():
            self.open_vault(states["Vault Path"], states["Password"])

    def _on_exit_vault(self, submitted: bool, _):
        if not submitted:
            return
        assert not self.ctx.vault is None

        with exception_dialog():
            self.ctx.vault.close()
            self.ctx.vault = None
            self.ctx.selected_file = None

    def _on_save_vault(self, submitted: bool, states: dict):
        if not submitted:
            return
        with exception_dialog():
            self.vault_save_as(states["Destination"])

    def draw(self):
        imgui.begin("Explorer", flags=imgui.WindowFlags_.menu_bar)

        self.__draw_menu()
        self.__draw_file_tree()

        imgui.end()

    def open_vault(self, path: str, password: str):
        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")

        if not self.ctx.vault is None:
            self.ctx.vault.close()
        self.ctx.vault = VaultDB(vpath, password)

    def vault_save_as(self, path: str):
        assert not self.ctx.vault is None

        vpath = Path(path)
        if vpath.is_dir():
            raise RuntimeError("The Given Vault Path is a directory!")

        shutil.copy2(self.ctx.vault.path, path)
