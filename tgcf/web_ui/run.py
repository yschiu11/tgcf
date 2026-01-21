import os
from importlib import resources

import tgcf.web_ui as wu
from tgcf.config import read_config

package_dir = resources.files(wu)

def main():
    config = read_config()
    path = package_dir.joinpath("0_👋_Hello.py")

    os.environ["STREAMLIT_THEME_BASE"] = config.theme
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.system(f"streamlit run {str(path)}")

if __name__ == "__main__":
    main()
