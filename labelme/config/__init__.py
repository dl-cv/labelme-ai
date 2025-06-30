import os.path as osp
import shutil

import yaml

from labelme.logger import logger

here = osp.dirname(osp.abspath(__file__))


def update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            logger.warn("Skipping unexpected key in config: {}".format(key))
            continue
        if isinstance(target_dict[key], dict) and isinstance(value, dict):
            update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


# -----------------------------------------------------------------------------


def get_default_config():
    config_file = osp.join(here, "default_config.yaml")
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # save default config to ~/.labelmerc
    user_config_file = osp.join(osp.expanduser("~"), ".labelmerc")
    if not osp.exists(user_config_file):
        try:
            shutil.copy(config_file, user_config_file)
        except Exception:
            logger.warn("Failed to save config: {}".format(user_config_file))

    return config


def validate_config_item(key, value):
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(
            "Unexpected value for config key 'validate_label': {}".format(value)
        )
    if key == "shape_color" and value not in [None, "auto", "manual"]:
        raise ValueError(
            "Unexpected value for config key 'shape_color': {}".format(value)
        )
    if key == "labels" and value is not None and len(value) != len(set(value)):
        raise ValueError(
            "Duplicates are detected for config key 'labels': {}".format(value)
        )


def get_config(config_file_or_yaml=None, config_from_args=None):
    # 1. default config
    config = get_default_config()

    # 2. specified as file or yaml
    if config_file_or_yaml is not None:
        config_from_yaml = yaml.safe_load(config_file_or_yaml)
        if not isinstance(config_from_yaml, dict):
            with open(config_from_yaml) as f:
                logger.info("Loading config file from: {}".format(config_from_yaml))
                config_from_yaml = yaml.safe_load(f)
        update_dict(config, config_from_yaml, validate_item=validate_config_item)

    # 3. command line argument or specified config file
    if config_from_args is not None:
        update_dict(config, config_from_args, validate_item=validate_config_item)

    return config


extra_shortcuts = {
    'canvas_auto_left_click': '1',
    'add_text_flag': 'T',

    # 设置面板快捷键:
    'display_shape_label': 'C',

    # 旋转框快捷键
    'rotate_left': 'Z',
    'rotate_right': 'X',

    # 查看属性快捷键
    'view_attribute': 'Ctrl+I',
}


# 自己的代码
def get_config(*args, **kwargs):
    config = {'auto_save': True,
              'store_data': False,
              'shortcuts': {
                  'close': 'Ctrl+P',
                  'open': 'Ctrl+O',
                  'open_dir': 'Ctrl+U',
                  'quit': 'Ctrl+P',
                  'save': 'Ctrl+S',
                  'save_as': 'Ctrl+Shift+S',
                  'save_to': None,
                  'delete_file': 'Ctrl+Delete',
                  'open_next': ['D', 'Down', 'Ctrl+Shift+D'],
                  'open_prev': ['A', 'Up', 'Ctrl+Shift+A'],
                  'zoom_in': ['Ctrl++', 'Ctrl+='],
                  'zoom_out': 'Ctrl+-',
                  'zoom_to_original': 'Ctrl+0',
                  'fit_window': 'F',
                  'fit_width': 'Ctrl+Shift+F',
                  'create_polygon': ['Q'],
                  'create_rectangle': ['W'],
                  'create_circle': ['E'],
                  'create_polygon_circle': ['T'],
                  'create_circle_by_points': ['Y'],
                  'magic_wand_tool': ['U'],
                  'create_line': ['I', 'G'],
                  'create_point': ['K'],
                  'create_linestrip': None,
                  'create_ai_polygon': ['S'],
                  'edit_polygon': ['ESC', '\\'],
                  'delete_polygon': 'Delete',
                  'duplicate_polygon': 'Ctrl+D',
                  'copy_polygon': 'Ctrl+C',
                  'paste_polygon': 'Ctrl+V',
                  'undo': ['Ctrl+Z', 'Backspace'],
                  'undo_last_point': 'Ctrl+Z',
                  'add_point_to_edge': 'Ctrl+Shift+P',
                  'edit_label': 'Ctrl+E',
                  'toggle_keep_prev_mode': None,
                  'remove_selected_point': ['Meta+H', 'Backspace'],
                  'show_all_polygons': None,
                  'hide_all_polygons': None,
                  'toggle_all_polygons': 'V',

              },

              'display_label_popup': False,
              'keep_prev': False,
              'keep_prev_scale': False,
              'keep_prev_brightness': False,
              'keep_prev_contrast': False,
              'logger_level': 'info',
              'flags': None,
              'label_flags': None,
              'labels': None,
              'file_search': None,
              'sort_labels': True,
              'validate_label': None,
              'default_shape_color': [0, 255, 0],
              'shape_color': 'auto',
              'shift_auto_shape_color': 0,
              'label_colors': None,
              'shape': {'line_color': [0, 255, 0, 128],
                        'fill_color': [0, 0, 0, 64],
                        'vertex_fill_color': [0, 255, 0, 255],
                        'select_line_color': [255, 255, 255, 255],
                        'select_fill_color': [0, 255, 0, 64],
                        'hvertex_fill_color': [255, 255, 255, 255],
                        'point_size': 8},
              'ai': {'default': 'EfficientSam (accuracy)'},
              'flag_dock': {'show': True,
                            'closable': True,
                            'movable': True,
                            'floatable': True},
              'label_dock': {'show': True,
                             'closable': True,
                             'movable': True,
                             'floatable': True},
              'shape_dock': {'show': True,
                             'closable': True,
                             'movable': True,
                             'floatable': True},
              'file_dock': {'show': True,
                            'closable': True,
                            'movable': True,
                            'floatable': True},
              'show_label_text_field': True,
              'label_completion': 'contains',
              'fit_to_content': {'column': True, 'row': False},
              'epsilon': 10.0,
              'canvas': {'fill_drawing': True,
                         'double_click': 'close',
                         'num_backups': 50,
                         'crosshair': {'polygon': False,
                                       'rectangle': True,
                                       'circle': False,
                                       'line': False,
                                       'point': False,
                                       'linestrip': False,
                                       'ai_polygon': False,
                                       'ai_mask': False}}, }
    config['shortcuts'].update(extra_shortcuts)
    return config
