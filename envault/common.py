from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from PIL import ImageGrab, Image
from io import BytesIO

from imgui_bundle import imgui, portable_file_dialogs as pfd

import pyperclip
import subprocess
import shutil
import platform


@contextmanager
def exception_dialog():
    try:
        yield
    except Exception as e:
        pfd.message("Error", str(e), _icon=pfd.icon.error)


def get_spacing_width() -> float:
    return imgui.get_style().item_spacing.x


def get_button_width(label: str) -> float:
    style = imgui.get_style()
    return imgui.calc_text_size(label).x + style.frame_padding.x * 2


def get_fill_width(mul: float = 1.0):
    return (imgui.get_content_region_avail().x * mul, 0)


def center_text(text: str):
    text_width, text_height = imgui.calc_text_size(text)
    imgui.set_cursor_pos(
        (
            (imgui.get_window_width() - text_width) * 0.5,
            (imgui.get_window_height() - text_height) * 0.5,
        )
    )
    imgui.text(text)


def path_to_label(path: Path, prefix: str):
    return f"{path.name}##{prefix}:{path.as_posix()}"


def menu_item_full(
    label: str,
    enabled: bool,
    tooltip: str,
    shortcut: int | None = None,
    sflags: int = 0,
):
    ok = imgui.menu_item_simple(label, enabled=enabled) or (
        not shortcut is None and imgui.shortcut(shortcut, flags=sflags)
    )
    if imgui.is_item_hovered():
        imgui.set_tooltip(tooltip)
    return ok


def get_clipboard_bytes():
    try:
        img = ImageGrab.grabclipboard()

        if isinstance(img, Image.Image):
            fmt = img.format or "PNG"
            buf = BytesIO()
            img.save(buf, format=fmt)
            return buf.getvalue()
    except Exception:
        pass

    try:
        text = pyperclip.paste()
        if text:
            return text.encode("utf-8")
    except Exception:
        pass
    return None


def set_clipboard_bytes(contents: bytes):
    try:
        image = Image.open(BytesIO(contents))
        image.verify()
    except Exception:
        pyperclip.copy(contents.decode("utf-8"))
        return

    system = platform.system()

    if system == "Linux":
        if shutil.which("wl-copy"):
            subprocess.run(
                ["wl-copy", "--type", str(image.get_format_mimetype())],
                input=contents,
                check=True,
            )
            return

        if shutil.which("xclip"):
            subprocess.run(
                [
                    "xclip",
                    "-selection",
                    "clipboard",
                    "-t",
                    str(image.get_format_mimetype()),
                    "-i",
                ],
                input=contents,
                check=True,
            )
            return

        raise RuntimeError("Neither wl-copy nor xclip is installed.")

    elif system == "Windows":
        import win32clipboard

        image = Image.open(BytesIO(contents))
        output = BytesIO()
        image.convert("RGB").save(output, "BMP")

        dib = output.getvalue()[14:]

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(
                win32clipboard.CF_DIB,
                dib,
            )
        finally:
            win32clipboard.CloseClipboard()

    else:
        raise NotImplementedError(f"Unsupported platform: {system}")


class PopupManager:
    class InputClass:
        def __init__(self, itype: str, label: str, default_value, *args, **kwargs):
            self.itype = itype
            self.label = label
            self.value = default_value

            self.args = args
            self.kwargs = kwargs

    def __init__(self):
        self._label = None
        self._flags = 0
        self._started = False
        self._popup_open = False

        self._states: dict[str, Any] = {}
        self._inputs: list["PopupManager.InputClass"] = []

        self._result_cb: Callable | None = None

    def is_active(self):
        return not self._label is None

    def reset(self):
        self._label = None
        self._flags = 0
        self._started = False
        self._popup_open = False

        self._states = {}
        self._inputs = []

        self._result_cb = None

    def begin(self, name: str, flags: int = imgui.WindowFlags_.no_saved_settings):
        assert self._label is None

        self.reset()
        self._label = name
        self._flags = flags

        return self

    def set_value(self, label: str, value):
        assert not self._label is None
        self._states[label] = value
        return self

    def set_result_cb(self, cb: Callable):
        assert not self._label is None
        self._result_cb = cb
        return self

    def add_text_input(self, label: str, default: str = "", **kwargs):
        assert not self._label is None
        self._inputs.append(self.InputClass("text", label, default, **kwargs))
        return self

    def add_path_input(self, label: str, default: str = "", **kwargs):
        assert not self._label is None
        self._inputs.append(self.InputClass("path", label, default, **kwargs))
        return self

    def add_radio_buttons(
        self, label: str, default: str = "", btr_labels: list[str] = []
    ):
        assert not self._label is None
        self._inputs.append(
            self.InputClass("radio", label, default, btr_labels=btr_labels)
        )
        return self

    def add_custom_input(self, cb: Callable, *args, **kwargs):
        assert not self._label is None

        self._inputs.append(self.InputClass("widget", "", cb, *args, **kwargs))
        return self

    def __draw_text_input(self, label: str, default: str = "", **kwargs):
        contents = self._states.get(label, default)

        imgui.push_item_width(-1)
        changed, self._states[label] = imgui.input_text_with_hint(
            "##" + label, label, contents, **kwargs
        )
        imgui.pop_item_width()

        return changed

    def __draw_path_input(self, label: str, default: str = "", **kwargs):
        contents = self._states.get(label, default)

        imgui.push_item_width(
            get_fill_width()[0]
            - get_button_width("Pick File")
            - imgui.get_style().item_spacing.x
        )
        changed, self._states[label] = imgui.input_text_with_hint(
            "##" + label, label, contents, **kwargs
        )
        imgui.pop_item_width()

        imgui.same_line()
        if imgui.button("Pick File##" + label + "_btr"):
            contents = pfd.save_file(
                "Pick Vault File", contents, options=pfd.opt.force_overwrite
            ).result()
            if contents:
                self._states[label] = contents

        imgui.same_line()
        imgui.dummy((get_button_width("Pick File") * 2, 0))

        return changed

    def __draw_radio_buttons(
        self, label: str, default: str = "", btr_labels: list[str] = []
    ):
        selected = self._states.get(label, default)

        for i, blabel in enumerate(btr_labels):
            if imgui.radio_button(blabel, blabel == selected):
                selected = blabel

            if i != len(btr_labels) - 1:
                imgui.same_line()

        self._states[label] = selected
        return selected

    def draw(self):
        if self._label is None:
            return

        if not self._started:
            imgui.open_popup(self._label)
            self._popup_open = True
            self._started = True

        visible, self._popup_open = imgui.begin_popup_modal(
            self._label, self._popup_open, self._flags
        )

        if not self._popup_open:
            if self._result_cb:
                self._result_cb(False, self._states)
            self.reset()
            return

        if not visible:
            return

        for inp in self._inputs:
            if inp.itype == "text":
                self.__draw_text_input(inp.label, inp.value, **inp.kwargs)
            elif inp.itype == "path":
                self.__draw_path_input(inp.label, inp.value, **inp.kwargs)
            elif inp.itype == "radio":
                self.__draw_radio_buttons(inp.label, inp.value, **inp.kwargs)
            elif inp.itype == "widget":
                inp.value(*inp.args, **inp.kwargs)

        imgui.dummy(
            (
                get_button_width("Submit")
                + get_button_width("Cancel")
                + get_spacing_width() * 2,
                0,
            )
        )
        button_height = imgui.get_frame_height_with_spacing()
        remaining = imgui.get_content_region_avail().y - button_height
        if remaining > 0:
            imgui.dummy((0, remaining))

        if imgui.button("Submit", get_fill_width(0.5)):
            imgui.close_current_popup()
            if self._result_cb:
                self._result_cb(True, self._states)
            self.reset()

        imgui.same_line()

        if imgui.button("Cancel", get_fill_width()) or imgui.shortcut(imgui.Key.escape):
            if self._result_cb:
                self._result_cb(False, self._states)
            imgui.close_current_popup()
            self.reset()

        imgui.end_popup()
