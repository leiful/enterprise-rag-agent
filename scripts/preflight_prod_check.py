import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


REQUIRED_KEYS = {
    "DEEPSEEK_API_KEY",
    "CHAT_MODEL",
    "CHAT_BASE_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "MILVUS_URI",
    "MILVUS_COLLECTION",
    "APP_ENV",
    "APP_USERNAME",
    "APP_PASSWORD",
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_SAMESITE",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "DEFAULT_KNOWLEDGE_SOURCE_PATH",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_LOCALHOST_REGEX",
}

PLACEHOLDER_MARKERS = (
    "replace_with",
    "your-frontend-domain.example",
    "changeme",
    "change_me",
)

WEAK_PASSWORDS = {
    "123456",
    "password",
    "admin",
    "admin123",
    "change_this_local_password",
    "replace_with_a_strong_production_password",
    "replace_with_production_db_password",
}


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self):
        return not self.errors


def parse_env_file(path):
    values = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Line {line_number} is not a KEY=VALUE entry.")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def has_placeholder(value):
    normalized = value.strip().lower()
    return any(marker in normalized for marker in PLACEHOLDER_MARKERS)


def is_weak_password(value):
    normalized = value.strip()
    return normalized.lower() in WEAK_PASSWORDS or len(normalized) < 12


def database_url_password(database_url):
    parsed = urlparse(database_url)
    if not parsed.password:
        return ""
    return unquote(parsed.password)


def split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def check_env_values(values):
    errors = []
    warnings = []

    missing = sorted(key for key in REQUIRED_KEYS if not values.get(key))
    for key in missing:
        errors.append(f"{key} is required.")

    for key, value in values.items():
        if has_placeholder(value):
            errors.append(f"{key} still contains a placeholder value.")

    if values.get("APP_ENV", "").lower() != "production":
        errors.append("APP_ENV must be production.")

    if values.get("SESSION_COOKIE_SECURE", "").lower() != "true":
        errors.append("SESSION_COOKIE_SECURE must be true in production.")

    if values.get("SESSION_COOKIE_SAMESITE", "").lower() not in {"lax", "strict", "none"}:
        errors.append("SESSION_COOKIE_SAMESITE must be lax, strict, or none.")

    if values.get("SESSION_COOKIE_SAMESITE", "").lower() == "none" and values.get("SESSION_COOKIE_SECURE", "").lower() != "true":
        errors.append("SESSION_COOKIE_SECURE must be true when SESSION_COOKIE_SAMESITE is none.")

    if values.get("CORS_ALLOW_LOCALHOST_REGEX", "").lower() != "false":
        errors.append("CORS_ALLOW_LOCALHOST_REGEX must be false in production.")

    origins = split_csv(values.get("CORS_ALLOWED_ORIGINS", ""))
    if not origins:
        errors.append("CORS_ALLOWED_ORIGINS must include the production HTTPS origin.")
    for origin in origins:
        if origin == "*":
            errors.append("CORS_ALLOWED_ORIGINS must not use wildcard origins.")
        if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
            errors.append("CORS_ALLOWED_ORIGINS must not include localhost in production.")
        if not origin.startswith("https://"):
            errors.append("CORS_ALLOWED_ORIGINS should use HTTPS production origins.")

    if is_weak_password(values.get("APP_PASSWORD", "")):
        errors.append("APP_PASSWORD is too weak for production.")

    postgres_password = values.get("POSTGRES_PASSWORD", "")
    if is_weak_password(postgres_password):
        errors.append("POSTGRES_PASSWORD is too weak for production.")

    db_password = database_url_password(values.get("DATABASE_URL", ""))
    if postgres_password and db_password and postgres_password != db_password:
        errors.append("POSTGRES_PASSWORD must match the password in DATABASE_URL.")

    if values.get("DEFAULT_KNOWLEDGE_SOURCE_PATH", "").startswith(("http://", "https://")):
        errors.append("DEFAULT_KNOWLEDGE_SOURCE_PATH must be a container filesystem path, not a URL.")

    milvus_uri = values.get("MILVUS_URI", "")
    parsed_milvus_uri = urlparse(milvus_uri)
    if milvus_uri:
        if parsed_milvus_uri.scheme not in {"http", "https", "tcp", "grpc"}:
            errors.append("MILVUS_URI must use http, https, tcp, or grpc scheme.")
        if parsed_milvus_uri.hostname in {"localhost", "127.0.0.1"}:
            errors.append("MILVUS_URI must not point to localhost in production.")

    return CheckResult(errors=errors, warnings=warnings)


def check_env_file(path):
    path = Path(path)
    if not path.exists():
        return CheckResult(errors=[f"{path} does not exist."], warnings=[])
    try:
        values = parse_env_file(path)
    except ValueError as exc:
        return CheckResult(errors=[str(exc)], warnings=[])
    return check_env_values(values)


def main():
    parser = argparse.ArgumentParser(description="Check production .env settings before deployment.")
    parser.add_argument("--env-file", default=".env.prod", help="Path to the production env file.")
    args = parser.parse_args()

    result = check_env_file(args.env_file)
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if result.ok:
        print("Production env preflight passed.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
