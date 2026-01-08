import gradio as gr
from tgcf.config import read_config
from tgcf.web_ui.pages_gradio.welcome import create_welcome_page


def create_app():
    """Create the main tgcf Gradio application"""
    with gr.Blocks(title="tgcf - Telegram Forwarder") as app:
        # tabs for multi-page structure
        with gr.Tabs() as tabs:
            # Welcome page
            with gr.Tab("👋 Welcome", id="welcome"):
                create_welcome_page()

            # Placeholder tabs for future pages
            with gr.Tab("🔑 Telegram Login", id="login"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will contain Telegram login configuration.")

            with gr.Tab("⭐ Admins", id="admins"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will contain admin configuration.")

            with gr.Tab("🔗 Connections", id="connections"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will contain source to destination connection setup.")

            with gr.Tab("🔌 Plugins", id="plugins"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will contain plugin configuration (filter, format, replace, etc).")

            with gr.Tab("🏃 Run", id="run"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will allow you to run the forwarding process.")

            with gr.Tab("🔬 Advanced", id="advanced"):
                gr.Markdown("## Coming soon...")
                gr.Info("This page will contain advanced settings.")

    return app


def main():
    """Launch the Gradio web interface."""
    CONFIG = read_config()

    theme = gr.themes.Soft() if CONFIG.theme == "light" else gr.themes.Default()

    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=theme
    )


if __name__ == "__main__":
    main()
