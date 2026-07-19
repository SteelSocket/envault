from imgui_bundle import imgui, immvision

from PIL import Image
from io import BytesIO

import numpy as np


class Inspector:
    def __init__(self) -> None:
        self._content = None
        self._image_params = immvision.ImageParams()

    def set_content(self, data: bytes):
        try:
            image = Image.open(BytesIO(data)).convert("RGB")
            self._content = np.array(image)
        except:
            self._content = data.decode()

    def draw(self):
        imgui.begin("Inspector", flags=imgui.WindowFlags_.horizontal_scrollbar)

        if not self._content is None:
            size = imgui.get_content_region_avail()

            if isinstance(self._content, str):
                imgui.input_text_multiline(
                    "##text",
                    self._content,
                    size=(size.x, size.y),
                    flags=imgui.InputTextFlags_.read_only,
                )
            else:
                immvision.image("Vault Image", self._content, self._image_params)

        imgui.end()
