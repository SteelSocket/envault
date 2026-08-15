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
    get_clipboard_bytes,
    menu_item_full,
    set_clipboard_bytes,
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

        if imgui.begin_menu(ifa.ICON_FA_FILE_IMPORT):
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

        if imgui.begin_menu(ifa.ICON_FA_FILE_EXPORT):
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

    def __draw_tabs(self):
        if not imgui.begin_tab_bar("File Actions"):
            return

        self.__draw_text_editor()
        self.__draw_image_view()

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

    def _save_contents(self, submitted: bool, _):
        self._content_modified = False
        if not submitted:
            return
        self.__save()

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
