import os
import streamlit as st
from typing import Dict, List
from tgcf.web_ui.run import package_dir
from streamlit.components.v1 import html
from tgcf.config import read_config, write_config, Config
from tgcf.const import CONFIG_FILE_NAME, CONFIG_ENV_VAR_NAME

def get_config_path() -> str:
    return os.getenv(CONFIG_ENV_VAR_NAME, CONFIG_FILE_NAME)

def load_config_to_session() -> Config:
    if "config" not in st.session_state:
        path = get_config_path()
        try:
            st.session_state.config = read_config(path)
        except Exception as err:
            st.error(f"Failed to load config from {path}: {err}")
            st.stop()
    return st.session_state.config

def save_session_config(config: Config) -> None:
    path = get_config_path()
    write_config(config, path)
    st.session_state.config = config

def get_list(string: str):
    # string where each line is one element
    my_list = []
    for line in string.splitlines():
        clean_line = line.strip()
        if clean_line != "":
            my_list.append(clean_line)
    return my_list


def get_string(my_list: List):
    string = ""
    for item in my_list:
        string += f"{item}\n"
    return string


def dict_to_list(dict: Dict):
    my_list = []
    for key, val in dict.items():
        my_list.append(f"{key}: {val}")
    return my_list


def list_to_dict(my_list: List):
    my_dict = {}
    for item in my_list:
        key, val = item.split(":")
        my_dict[key.strip()] = val.strip()
    return my_dict


def apply_theme(st,CONFIG,hidden_container):
    """Apply theme using browser's local storage"""
    if  st.session_state.theme == '☀️':
        theme = 'Light'
        CONFIG.theme = 'light'
    else:
        theme = 'Dark'
        CONFIG.theme = 'dark'
    save_session_config(CONFIG)
    script = f"<script>localStorage.setItem('stActiveTheme-/-v1', '{{\"name\":\"{theme}\"}}');"
    pages_dir = package_dir / 'pages'
    pages = [p.name for p in pages_dir.iterdir()]
    for page in pages:
        script += f"localStorage.setItem('stActiveTheme-/{page[4:-3]}-v1', '{{\"name\":\"{theme}\"}}');"
    script += 'parent.location.reload()</script>'
    with hidden_container: # prevents the layout from shifting
        html(script,height=0,width=0)


def switch_theme(st,CONFIG):
    """Display the option to change theme (Light/Dark)"""
    with st.sidebar:
        leftpad,content,rightpad = st.columns([0.27,0.46,0.27])
        with content:
            st.radio (
                'Theme:',['☀️','🌒'],
                horizontal=True,
                label_visibility="collapsed",
                index=CONFIG.theme == 'dark',
                on_change=apply_theme,
                key="theme",
                args=[st,CONFIG,leftpad] # or rightpad
            )
        

def hide_st(st):
    dev = os.getenv("DEV")
    if dev:
        return
    hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)
