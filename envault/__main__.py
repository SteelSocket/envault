from pathlib import Path
from imgui_bundle import hello_imgui, immvision, imgui

from envault.context import AppContext
from envault.explorer import Explorer
from envault.inspector import Inspector

import argparse


class App:
    def __init__(self):
        self.ctx = AppContext()
        self.explorer = Explorer(self.ctx)
        self.inspector = Inspector(self.ctx)

    def gui(self):
        self.explorer.draw()
        self.inspector.draw()
        self.ctx.pm.draw()

        if imgui.shortcut(
            imgui.Key.mod_ctrl | imgui.Key.q, imgui.InputFlags_.route_global
        ):
            hello_imgui.get_runner_params().app_shall_exit = True

    def set_vault(self, vault: Path, password: str):
        self.explorer.open_vault(vault.as_posix(), password)


def __load_font():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    imgui.get_io().fonts.add_font_default()


def get_runner_params(app: App):
    params = hello_imgui.RunnerParams()
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.provide_full_screen_dock_space
    )
    params.app_window_params.window_title = "EnVault"
    params.app_window_params.restore_previous_geometry = True
    params.ini_folder_type = hello_imgui.IniFolderType.app_user_config_folder
    params.ini_filename = "envault/imgui.ini"
    params.dpi_aware_params.dpi_window_size_factor = 1.5
    params.callbacks.default_icon_font = hello_imgui.DefaultIconFont.font_awesome6
    params.callbacks.load_additional_fonts = __load_font

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

    return params


def get_args():
    parser = argparse.ArgumentParser(
        "envault", description="Application to open/create encrypted vault"
    )
    parser.add_argument(
        "vault_path",
        type=Path,
        nargs="?",
        help="The Vault file to open",
    )
    parser.add_argument(
        "password",
        type=str,
        nargs="?",
        help="Password to the Vault",
    )

    args = parser.parse_args()

    if args.vault_path is None:
        return args

    if args.vault_path.is_dir():
        parser.error("The given vault_path is not a valid file")

    if args.password is None:
        args.password = input("Enter Vault Password: ")

    return args


def main():
    args = get_args()
    app = App()

    if not args.vault_path is None:
        app.set_vault(args.vault_path, args.password)

    params = get_runner_params(app)
    immvision.use_rgb_color_order()
    hello_imgui.run(params)


if __name__ == "__main__":
    main()
