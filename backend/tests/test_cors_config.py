from app.core.config import Settings


def test_cors_origins_list_trims_whitespace_and_trailing_slashes() -> None:
    settings = Settings(
        CORS_ORIGINS=(
            " https://rag-chatbot-rosy-five.vercel.app/ , "
            "https://admin.example.com/// "
        )
    )

    assert settings.cors_origins_list == [
        "https://rag-chatbot-rosy-five.vercel.app",
        "https://admin.example.com",
    ]
