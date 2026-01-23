import os
from importlib import resources

import tgcf.web_ui as wu
from tgcf.config import read_config, CONFIG_FILE_NAME

package_dir = resources.files(wu)

def main():
    config_path = os.getenv("TGCF_CONFIG", CONFIG_FILE_NAME)
    os.environ["TGCF_CONFIG"] = config_path

    config = read_config(config_path)
    path = package_dir.joinpath("0_👋_Hello.py")

    os.environ["STREAMLIT_THEME_BASE"] = config.theme
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.system(f"streamlit run {str(path)}")

if __name__ == "__main__":
    main()
