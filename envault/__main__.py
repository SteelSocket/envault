from imgui_bundle import hello_imgui, immvision, imgui

from envault.explorer import Explorer
from envault.inspector import Inspector


class App:
    def __init__(self):
        self.explorer = Explorer(self._on_file_select)
        self.inspector = Inspector()

    def gui(self):
        self.explorer.draw()
        self.inspector.draw()

    def _on_file_select(self, data: bytes):
        self.inspector.set_content(data)


def main():
    app = App()

    params = hello_imgui.RunnerParams()
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.provide_full_screen_dock_space
    )
    params.app_window_params.window_title = "EnVault"
    params.app_window_params.restore_previous_geometry = True
    params.ini_folder_type = hello_imgui.IniFolderType.app_user_config_folder
    params.ini_filename = "envault/imgui.ini"

    split_inspector = hello_imgui.DockingSplit()
    split_inspector.initial_dock = "MainDockSpace"
    split_inspector.new_dock = "RightSpace"
    split_inspector.direction = imgui.Dir.right
    split_inspector.ratio = 0.75

    params.docking_params.docking_splits = [split_inspector]

    explorer_dock = hello_imgui.DockableWindow()
    explorer_dock.label = "Explorer"
    explorer_dock.dock_space_name = "MainDockSpace"
    explorer_dock.call_begin_end = False
    explorer_dock.gui_function = lambda: None


    inspector_dock = hello_imgui.DockableWindow()
    inspector_dock.label = "Inspector"
    inspector_dock.dock_space_name = "RightSpace"
    inspector_dock.call_begin_end = False
    inspector_dock.gui_function = lambda: None

    params.docking_params.dockable_windows = [explorer_dock, inspector_dock]
    params.callbacks.show_gui = app.gui

    immvision.use_rgb_color_order()
    hello_imgui.run(params)


if __name__ == "__main__":
    main()
