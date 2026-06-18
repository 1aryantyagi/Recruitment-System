"""App package init.

Inject the OS trust store into Python's SSL as early as possible so outbound
HTTPS (OpenAI/Anthropic, Gmail, Twilio, Deepgram, MS Graph) works behind
corporate proxies / custom root CAs. Best-effort — never block startup.
"""
try:  # pragma: no cover
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass
