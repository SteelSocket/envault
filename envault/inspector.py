from pathlib import Path
from PIL import Image
from io import BytesIO
from imgui_bundle import (
    imgui,
    immvision,
    icons_fontawesome_6 as ifa,
    portable_file_dialogs as pfd,
)

import numpy as np

from envault.common import (
    center_text,
    exception_dialog,
    get_clipboard_bytes,
    menu_item_full,
    set_clipboard_bytes,
    menu_with_tooltip,
    next_string_number,
)
from envault.context import AppContext


class Inspector:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

        self._current_file = None

        self._content = ""
        self._content_modified = False

        self._image = None
        self._image_params = immvision.ImageParams()

        self._renaming_value: str | None = None
        self._rename_buffer = ""
        self._rename_started = False

    def _save_contents(self, submitted: bool, _):
        self._content_modified = False
        if not submitted:
            return
        self.__save()

    def __save(self):
        assert self.ctx.vault and self._current_file

        if isinstance(self._content, str):
            self.ctx.vault.write_file(self._current_file, self._content.encode())
        else:
            self.ctx.vault.write_file(self._current_file, self._content)

    def __draw_text_editor_menu(self):
        if not imgui.begin_menu_bar():
            return
        assert self._current_file and self.ctx.vault

        if menu_item_full(
            ifa.ICON_FA_FLOPPY_DISK,
            True,
            "Save File",
            imgui.Key.mod_ctrl | imgui.Key.s,
            0,
        ):
            self.__save()
            self.set_file(self._current_file)
            self._content_modified = False

        if menu_with_tooltip(ifa.ICON_FA_FILE_IMPORT, "Import"):
            if menu_item_full("File", True, "Import data from file"):
                file = pfd.open_file("Import File").result()[0]

                data = Path(file).read_bytes()
                self.__set_contents(data)
                self._content_modified = True

            if menu_item_full("Clipboard", True, "Import data from clipboard"):
                data = get_clipboard_bytes()
                if data:
                    self.__set_contents(data)
                    self._content_modified = True

            imgui.end_menu()

        if menu_with_tooltip(ifa.ICON_FA_FILE_EXPORT, "Export"):
            if menu_item_full("File", True, "Export data to file"):
                save_file = Path(pfd.save_file("Export File").result())

                if isinstance(self._content, str):
                    save_file.write_text(self._content)
                else:
                    save_file.write_bytes(self._content)

            if menu_item_full("Clipboard", True, "Export data to clipboard"):
                if isinstance(self._content, str):
                    set_clipboard_bytes(self._content.encode())
                else:
                    set_clipboard_bytes(self._content)

            imgui.end_menu()

        imgui.separator()
        imgui.text(f"File: {self._current_file.name}")
        imgui.separator()
        imgui.text(f"File Size: {len(self._content)}")
        imgui.separator()
        if not self._content_modified:
            imgui.text(f"File Status: Saved  ")
        else:
            imgui.text(f"File Status: Unsaved")
        imgui.separator()

        imgui.end_menu_bar()

    def __draw_text_editor(self):
        if not imgui.begin_tab_item("Text Editor")[0]:
            return

        if imgui.begin_child(
            "##TEChild",
            window_flags=imgui.WindowFlags_.menu_bar | imgui.WindowFlags_.no_scrollbar,
        ):
            self.__draw_text_editor_menu()

            if isinstance(self._content, str):
                imgui.push_font(imgui.get_io().fonts.fonts[1], 0.0)
                changed, self._content = imgui.input_text_multiline(
                    f"##TextEditor_{self._current_file}",
                    self._content,
                    imgui.get_content_region_avail(),
                    imgui.InputTextFlags_.allow_tab_input,
                )
                if changed:
                    self._content_modified = True
                imgui.pop_font()
            else:
                center_text("Binary files cannot be edited by text editor")

            imgui.end_child()

        imgui.end_tab_item()

    def __draw_image_view(self):
        if not imgui.begin_tab_item("Image Viewer")[0]:
            return
        assert self._current_file and self.ctx.vault

        if not self._image is None:
            immvision.image("Vault Image", self._image, self._image_params)
        else:
            center_text("The file is not a image")

        imgui.end_tab_item()

    def __draw_rename(self, multi_line: bool = False) -> bool:
        imgui.set_next_item_width(-1)

        if not self._rename_started:
            self._rename_started = True
            imgui.set_keyboard_focus_here()

        if not multi_line:
            finished, self._rename_buffer = imgui.input_text(
                "##rename",
                self._rename_buffer,
                flags=imgui.InputTextFlags_.enter_returns_true
                | imgui.InputTextFlags_.auto_select_all,
            )
        else:
            finished, self._rename_buffer = imgui.input_text_multiline(
                "##rename",
                self._rename_buffer,
                flags=imgui.InputTextFlags_.enter_returns_true
                | imgui.InputTextFlags_.auto_select_all,
            )

        if finished:
            self._renaming_value = None
            self._rename_started = False
            return True

        if not imgui.is_item_active() and imgui.is_mouse_clicked(0):
            self._renaming_value = None
            self._rename_started = False
            return True

        return False

    def __draw_row_ctx_menu(self, key: str, suffix: str):
        assert self.ctx.vault and self._current_file
        if imgui.begin_popup_context_item(
            f"##{key}_{suffix}_context",
            imgui.PopupFlags_.no_open_over_items
            | imgui.PopupFlags_.no_open_over_existing_popup
            | imgui.PopupFlags_.no_reopen,
        ):
            if imgui.menu_item_simple(ifa.ICON_FA_CIRCLE_XMARK + " Delete Metadata"):
                self.ctx.vault.remove_metadata(self._current_file, key)

            imgui.end_popup()

    def __draw_metadata_view(self):
        if not imgui.begin_tab_item("Metadata")[0]:
            return
        assert self.ctx.vault and self._current_file
        metadata = self.ctx.vault.get_metadata(self._current_file)

        if imgui.begin_child("##MetadataViwer"):
            if imgui.begin_table(
                "MetadataTable",
                2,
                imgui.TableFlags_.borders
                | imgui.TableFlags_.row_bg
                | imgui.TableFlags_.resizable
                | imgui.TableFlags_.reorderable,
            ):
                imgui.table_setup_column("Key", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("Value", imgui.TableColumnFlags_.width_stretch)
                imgui.table_headers_row()

                for key, value in metadata.items():
                    width = imgui.get_content_region_avail()[0]
                    text_size = imgui.calc_text_size(value)
                    height = text_size[1]
                    pos = imgui.get_cursor_screen_pos()

                    imgui.table_next_row()
                    imgui.table_next_column()
                    if self._renaming_value == key:
                        if self.__draw_rename():
                            with exception_dialog(
                                "Conflicting Keys! Key exists with same name!"
                            ):
                                self.ctx.vault.rename_metadata(
                                    self._current_file, key, self._rename_buffer
                                )
                    else:
                        imgui.selectable(key + "##row", False, size=(0, height))
                        if imgui.is_item_hovered():
                            imgui.set_tooltip(
                                "Double Click to Edit Key, Right Click to open menu"
                            )
                        self.__draw_row_ctx_menu(key, "key")

                    if imgui.is_item_clicked() and imgui.is_mouse_double_clicked(0):
                        self._renaming_value = key
                        self._rename_buffer = key

                    imgui.table_next_column()

                    if self._renaming_value == f"{key}|{value}":
                        if self.__draw_rename(True):
                            self.ctx.vault.add_metadata(
                                self._current_file, key, self._rename_buffer
                            )
                    else:
                        width = imgui.get_content_region_avail()[0]
                        text_size = imgui.calc_text_size(value)
                        height = text_size[1]
                        pos = imgui.get_cursor_screen_pos()

                        imgui.selectable(
                            f"##row_{key}_value",
                            False,
                            imgui.SelectableFlags_.allow_overlap,
                            (width, height),
                        )

                        if imgui.is_item_hovered():
                            imgui.set_tooltip(
                                "Double Click to Edit Key, Right Click to open menu"
                            )
                        self.__draw_row_ctx_menu(key, "value")

                        if imgui.is_item_clicked() and imgui.is_mouse_double_clicked(0):
                            self._renaming_value = f"{key}|{value}"
                            self._rename_buffer = value

                        imgui.set_cursor_screen_pos((pos[0], pos[1]))
                        imgui.text_unformatted(value)

                imgui.end_table()

            if imgui.button("Add Metadata", (-1, 0)):
                name = next_string_number("Key", list(metadata.keys()))
                self.ctx.vault.add_metadata(self._current_file, name, "value")

            imgui.end_child()

        imgui.end_tab_item()

    def __draw_tabs(self):
        if not imgui.begin_tab_bar("File Actions"):
            return

        self.__draw_text_editor()
        self.__draw_image_view()
        self.__draw_metadata_view()

        imgui.end_tab_bar()

    def __set_contents(self, contents: bytes):
        self._content_modified = False
        try:
            self._content = contents.decode()
        except:
            self._content = contents

        self._image_params = immvision.ImageParams()
        try:
            image = Image.open(BytesIO(contents)).convert("RGB")
            self._image = np.array(image)
        except:
            self._image = None

    def draw(self):
        imgui.begin("Inspector", flags=imgui.WindowFlags_.horizontal_scrollbar)

        if self._current_file != self.ctx.selected_file:
            if (
                not self.ctx.pm.is_active()
                and self._content_modified
                and self._current_file
            ):
                self.ctx.pm.begin("Unsaved File").add_custom_input(
                    imgui.text,
                    f"The opened file {self._current_file.name} is not saved! (Submit to save)",
                ).set_result_cb(self._save_contents)
            elif not self.ctx.pm.is_active():
                self._current_file = self.ctx.selected_file
                self.set_file(self._current_file)

        if self._current_file:
            self.__draw_tabs()

        imgui.end()

    def set_file(self, file: Path | None):
        if file is None:
            self._content = ""
            return

        assert not self.ctx.vault is None
        self.__set_contents(self.ctx.vault.read_file(file))
