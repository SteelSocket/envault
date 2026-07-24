from collections import defaultdict
from contextlib import contextmanager
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


def get_text_width(text: str) -> float:
    """Returns the width of plain text."""
    return imgui.calc_text_size(text).x


def get_spacing_width() -> float:
    return imgui.get_style().item_spacing.x


def get_button_width(label: str) -> float:
    """Returns the minimum width a button with this label will occupy."""
    style = imgui.get_style()
    return imgui.calc_text_size(label).x + style.frame_padding.x * 2


def get_fill_width(mul: float = 1.0):
    return (imgui.get_content_region_avail().x * mul, 0)


def bottom_align():
    height = imgui.get_frame_height()
    imgui.set_cursor_pos_y(
        imgui.get_window_height() - height - imgui.get_style().window_padding.y
    )


def left_align():
    imgui.set_cursor_pos_x(imgui.get_style().window_padding.x)


def right_align(width: float):
    imgui.set_cursor_pos_x(
        imgui.get_window_width() - width - imgui.get_style().window_padding.x
    )


def center_align(width: float):
    imgui.set_cursor_pos_x((imgui.get_window_width() - width) * 0.5)


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
    POPUP_NONE = 0
    POPUP_SUBMIT = 1
    POPUP_CANCEL = 2

    def __init__(self):
        self._show_popup = None
        self._popup_states = defaultdict(lambda: {})

        self._current_popup = None
        self._showing_popup = False

    def begin(self, name: str, flags: int = imgui.WindowFlags_.no_saved_settings):
        if name == self._show_popup:
            imgui.open_popup(name)
            self._show_popup = None

        visible, _ = imgui.begin_popup_modal(name, True, flags)
        if visible:
            self._current_popup = name
            self._showing_popup = True
        else:
            self._showing_popup = False
        return visible

    def end(self):
        ret_status = self.POPUP_NONE

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
            ret_status = self.POPUP_SUBMIT
            self._showing_popup = False

        imgui.same_line()

        if imgui.button("Cancel", get_fill_width()):
            imgui.close_current_popup()
            ret_status = self.POPUP_CANCEL
            self._showing_popup = False

        if imgui.shortcut(imgui.Key.escape):
            imgui.close_current_popup()
            ret_status = self.POPUP_CANCEL
            self._showing_popup = False

        imgui.end_popup()

        ret = (ret_status, self._popup_states[self._current_popup])
        self._current_popup = None
        return ret

    def show(self, name: str):
        if not self._showing_popup:
            self._show_popup = name

    def set_value(self, popup: str, label: str, value):
        state = self._popup_states[popup]
        state[label] = value

    def add_text_input(self, label: str, default: str = "", **kwargs):
        if self._current_popup is None:
            raise RuntimeError()

        state = self._popup_states[self._current_popup]
        contents = state.get(label, default)

        imgui.push_item_width(-1)
        changed, state[label] = imgui.input_text_with_hint(
            "##" + label, label, contents, **kwargs
        )
        imgui.pop_item_width()

        return changed

    def add_path_input(self, label: str, default: str = "", **kwargs):
        if self._current_popup is None:
            raise RuntimeError()

        state = self._popup_states[self._current_popup]
        contents = state.get(label, default)

        imgui.push_item_width(
            get_fill_width()[0]
            - get_button_width("Pick File")
            - imgui.get_style().item_spacing.x
        )
        changed, state[label] = imgui.input_text_with_hint(
            "##" + label, label, contents, **kwargs
        )
        imgui.pop_item_width()

        imgui.same_line()
        if imgui.button("Pick File##" + label + "_btr"):
            contents = pfd.save_file(
                "Pick Vault File", contents, options=pfd.opt.force_overwrite
            ).result()
            if contents:
                state[label] = contents

        imgui.same_line()
        imgui.dummy((get_button_width("Pick File") * 2, 0))

        return changed

    def add_radio_buttons(self, label: str, btr_labels: list[str], default: str = ""):
        if self._current_popup is None:
            raise RuntimeError()

        state = self._popup_states[self._current_popup]
        selected = state.get(label, default)

        for i, blabel in enumerate(btr_labels):
            if imgui.radio_button(blabel, blabel == selected):
                selected = blabel

            if i != len(btr_labels) - 1:
                imgui.same_line()

        state[label] = selected
        return selected
