from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/birdphotos"
    test_database_url: str = "postgresql+psycopg://localhost/birdphotos_test"
    internal_api_token: str = "dev-secret-change-me"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "birdphotos"

    anthropic_api_key: str = ""

    # The removable AI-trust layer (see plan: Data Model). Flip to true
    # later to move to a fully-automatic species workflow with zero
    # schema/call-site changes — see app/queries.py get_effective_species.
    trust_ai_suggestions: bool = False

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""


settings = Settings()
