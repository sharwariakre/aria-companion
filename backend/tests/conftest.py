"""
Set environment variables before any app module is imported.
All settings have defaults so most tests work without a .env file.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aria:aria@localhost:5432/aria_test")
os.environ.setdefault("BASE_URL", "http://localhost:8001")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest00000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15005550006")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("ALERT_EMAIL_FROM", "test@example.com")
os.environ.setdefault("ALERT_EMAIL_PASSWORD", "password")
os.environ.setdefault("ALERT_EMAIL_TO", "family@example.com")
