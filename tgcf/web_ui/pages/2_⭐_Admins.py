import streamlit as st

from tgcf.web_ui.password import check_password
from tgcf.web_ui.utils import (
    get_list,
    get_string,
    hide_st,
    switch_theme,
    load_config_to_session,
    save_session_config
)

CONFIG = load_config_to_session()

st.set_page_config(
    page_title="Admins",
    page_icon="⭐",
)
hide_st(st)
switch_theme(st,CONFIG)
if check_password(st):

    CONFIG.admins = get_list(st.text_area("Admins", value=get_string(CONFIG.admins)))
    st.write("Add the usernames of admins. One in each line.")

    if st.button("Save"):
        save_session_config(CONFIG)
