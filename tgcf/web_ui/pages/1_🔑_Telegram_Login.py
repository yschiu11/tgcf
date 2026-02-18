import streamlit as st

from tgcf.web_ui.password import check_password
from tgcf.web_ui.utils import (
    hide_st,
    load_config_to_session,
    save_session_config,
    switch_theme,
)

CONFIG = load_config_to_session()

st.set_page_config(
    page_title="Telegram Login",
    page_icon="🔑",
)
hide_st(st)
switch_theme(st,CONFIG)
if check_password(st):
    CONFIG.login.api_id = int(
        st.text_input("API ID", value=str(CONFIG.login.api_id), type="password")
    )
    CONFIG.login.api_hash = st.text_input(
        "API HASH", value=CONFIG.login.api_hash, type="password"
    )
    st.write("You can get api id and api hash from https://my.telegram.org.")

    user_type = st.radio(
        "Choose account type", ["Bot", "User"], index=CONFIG.login.user_type
    )
    if user_type == "Bot":
        CONFIG.login.user_type = 0
        CONFIG.login.bot_token = st.text_input(
            "Enter bot token", value=CONFIG.login.bot_token, type="password"
        )
    else:
        CONFIG.login.user_type = 1
        CONFIG.login.session_string = st.text_input(
            "Enter session string", value=CONFIG.login.session_string, type="password"
        )
        with st.expander("How to get session string ?"):
            st.markdown(
                """

            Link to repl: https://replit.com/@aahnik/tg-login?v=1

            _Click on the above link and enter api id, api hash, and phone no to generate session string._

            **Note from developer:**

            Due some issues logging in with a user account using a phone no is not supported in this web interface.

            I have built a command-line program named tg-login (https://github.com/aahnik/tg-login) that can generate the session string for you.

            You can run tg-login on your computer, or securely in this repl. tg-login is open source, and you can also inspect the bash script running in the repl.

            What is a session string ?
            https://docs.telethon.dev/en/stable/concepts/sessions.html#string-sessions

            """
            )

    if st.button("Save"):
        save_session_config(CONFIG)
