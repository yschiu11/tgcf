import os
from importlib import resources

import tgcf.web_ui as wu
from tgcf.config import CONFIG

package_dir = resources.files(wu)

def main():
    """Launch the web interface.
    
    Supports both Gradio (new) and Streamlit (original) interfaces.
    Use environment variable WEB_UI=streamlit to use the old interface.
    """
    web_ui_type = os.getenv("WEB_UI", "gradio").lower()
    
    if web_ui_type == "streamlit":
        path = package_dir.joinpath("0_👋_Hello.py")
        os.environ["STREAMLIT_THEME_BASE"] = CONFIG.theme
        os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
        os.system(f"streamlit run {str(path)}")
    else:
        from tgcf.web_ui.gradio_app import main as gradio_main
        gradio_main()

if __name__ == "__main__":
    main()
