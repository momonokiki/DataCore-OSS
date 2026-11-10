import reflex as rx

config = rx.Config(
    app_name="webui",
    plugins=[
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="light")
        )
    ],
)
