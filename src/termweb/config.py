"""Environment configuration. Secrets come from k8s secrets; nothing here is baked in."""

import os

# OIDC (ringer pattern): confidential client in the Keycloak homelab realm.
KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER", "https://auth.kardol.us/realms/homelab")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "term")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-secret")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://term.kardol.us")

# This app hands out a shell on forge; the allow-list is deliberately one person.
ALLOWED_EMAILS = [e.strip() for e in os.environ.get("ALLOWED_EMAILS", "g@kardol.us").split(",") if e.strip()]

# Read-only hostPath mounts (see deploy/k8s/10-term-web.yaml).
CLAUDE_ARCHIVE_DIR = os.environ.get("CLAUDE_ARCHIVE_DIR", "/data/claude-archive")
CODEX_SESSIONS_DIR = os.environ.get("CODEX_SESSIONS_DIR", "/data/codex-sessions")
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/data/workspace")

# SSH to the forge host — the terminal path. Key + pinned known_hosts from the
# term-ssh secret.
SSH_HOST = os.environ.get("SSH_HOST", "10.0.0.120")
SSH_USER = os.environ.get("SSH_USER", "guillermo")
SSH_KEY = os.environ.get("SSH_KEY", "/ssh/id_ed25519")
SSH_KNOWN_HOSTS = os.environ.get("SSH_KNOWN_HOSTS", "/ssh/known_hosts")

# Remote home — used to localize recorded cwds from other machines.
REMOTE_HOME = os.environ.get("REMOTE_HOME", "/home/guillermo")

MAX_TERMINALS = int(os.environ.get("MAX_TERMINALS", "4"))
IDLE_TIMEOUT_S = int(os.environ.get("IDLE_TIMEOUT_S", "14400"))
TICKET_MAX_AGE_S = int(os.environ.get("TICKET_MAX_AGE_S", "30"))

BRAND = "term"
DOMAIN = os.environ.get("DOMAIN", "term.kardol.us")
