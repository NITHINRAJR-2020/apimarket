from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "APIMarket"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me-in-production-apimarket-secret-key"

    # --- Auth (JWT) ---
    # JWT_SECRET defaults to SECRET_KEY if left blank (see get_settings()).
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # --- Initial admin bootstrap (used by scripts/create_admin.py) ---
    # Never hardcode production credentials; set these in the environment.
    ADMIN_EMAIL: str = "admin@payperquery.local"
    ADMIN_PASSWORD: str = ""
    ADMIN_NAME: str = "Platform Admin"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://user:password@ep-example.neon.tech/apimarket?ssl=require"
    DB_ECHO: bool = False

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "https://apimarket-ui.onrender.com"]

    # --- Algorand network ---
    ALGOD_ADDRESS: str = "https://testnet-api.algonode.cloud"
    ALGOD_TOKEN: str = ""
    INDEXER_ADDRESS: str = "https://testnet-idx.algonode.cloud"
    INDEXER_TOKEN: str = ""
    ALGORAND_NETWORK: str = "testnet"
    USDC_TESTNET_ASA_ID: int = 10458941

    # --- x402 v2 / GoPlausible facilitator ---
    FACILITATOR_URL: str = "https://facilitator.goplausible.xyz"
    # CAIP-2 identifier required by x402 v2 -- NOT the plain string "testnet".
    # Matches x402.mechanisms.avm.ALGORAND_TESTNET_CAIP2; kept as a plain
    # setting (not imported from the SDK) so config.py has no hard
    # dependency on x402-avm being importable at settings-load time.
    X402_NETWORK_CAIP2: str = "algorand:SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="
    X402_MAX_TIMEOUT_SECONDS: int = 60

    # --- x402 protocol ---
    X402_SCHEME: str = "exact"
    X402_QUOTE_TTL_SECONDS: int = 120
    X402_QUOTE_SECRET: str = "change-me-in-production-x402-quote-hmac-secret"
    MIN_CONFIRMATIONS: int = 1

    # --- Platform escrow wallet -------------------------------------------------
    # THIS is what makes payment real escrow instead of "pay and pray":
    # agents pay the x402 quote to ESCROW_WALLET_ADDRESS (an address the
    # PLATFORM controls), not straight to the provider. Funds only leave this
    # wallet when the platform's escrow service explicitly RELEASES them to
    # the provider (after the upstream call succeeds) or REFUNDS them back to
    # the paying agent (after a failure/dispute). ESCROW_WALLET_MNEMONIC must
    # be the 25-word mnemonic that controls ESCROW_WALLET_ADDRESS, and must
    # be treated as a production secret (KMS/secrets manager), never committed.
    ESCROW_WALLET_ADDRESS: str = "PLATFORMESCROWALGORANDADDRESSXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    ESCROW_WALLET_MNEMONIC: str = ""
    ESCROW_AUTO_RELEASE: bool = True  # release automatically once upstream call succeeds
    ESCROW_HOLD_SECONDS: int = 0  # optional cooling-off period before auto-release is allowed
    ESCROW_STALE_SECONDS: int = 600  # HELD longer than this with no settlement -> watchdog auto-refunds
    ESCROW_WATCHDOG_INTERVAL_SECONDS: int = 60  # how often the background sweep runs

    # --- Proxy / upstream calls ---
    UPSTREAM_TIMEOUT_SECONDS: float = 15.0

    # --- Policy defaults for newly-created agents ---
    DEFAULT_MIN_PROVIDER_REPUTATION: int = 50

    # --- Platform commission (optional, taken out of the release amount) ---
    PLATFORM_FEE_BPS: int = 250  # 2.5%, in basis points

    # --- Support chatbot (Gemini) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    CHATBOT_ENABLED: bool = True
    CHATBOT_HISTORY_TURNS: int = 6  # how many prior turns to keep as context


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.JWT_SECRET:
        settings.JWT_SECRET = settings.SECRET_KEY
    return settings
