"""Which model answers, and how it is reached.

The program used to call Gemini directly, in one place, with the model name
written into the call. That is fine until the key belongs to somebody who has
left, or the free tier runs out mid-afternoon, or the next team already pays
for something else. Then a working tool is stuck behind an account nobody
controls, and the fix is a code change nobody is left to make.

So the provider is configuration, not code. One entry per provider, in the
`kinds.py` pattern: a dataclass with no defaults, checked at import, so a
half-declared provider stops the program instead of failing on the first call.

**Gemini keeps its own direct path, deliberately.** Every published number —
366/372 on the archive, 143/144 on the views — was measured through
`google-genai`, and those runs come from cache, so re-measuring them through a
different client would cost real API calls to prove something that is currently
true. The default therefore stays on the code path that produced the evidence.
Everything else goes through LiteLLM, which is the one dependency that speaks
to all of them, and which is only imported when actually used — a provider
nobody selects costs nothing at startup.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

DIRECT = "direct"      # this provider has its own client in this file
LITELLM = "litellm"    # reached through litellm.completion


@dataclass(frozen=True)
class Provider:
    """Everything about reaching one model vendor, declared once.

    No field has a default. A provider missing its key variable or its model
    would fail at the moment of the call — the slowest and most expensive place
    to discover a typo — so `_check()` refuses the registry at import instead.
    """

    name: str
    label: str                  # what a person calls it, for the settings screen
    default_model: str
    key_var: Optional[str]      # None for a local runtime that needs no key
    transport: str
    key_url: Optional[str]      # where a person gets one, shown in the UI


_REGISTRY = (
    Provider(
        name="gemini", label="Google Gemini",
        # The model every published number was measured with. Changing this
        # string silently re-measures the whole project.
        default_model="gemini-3.5-flash",
        key_var="GEMINI_API_KEY", transport=DIRECT,
        key_url="https://aistudio.google.com",
    ),
    Provider(
        name="openai", label="OpenAI",
        default_model="gpt-4o-mini",
        key_var="OPENAI_API_KEY", transport=LITELLM,
        key_url="https://platform.openai.com/api-keys",
    ),
    Provider(
        name="anthropic", label="Anthropic Claude",
        default_model="claude-sonnet-4-5",
        key_var="ANTHROPIC_API_KEY", transport=LITELLM,
        key_url="https://console.anthropic.com/settings/keys",
    ),
    Provider(
        name="mistral", label="Mistral",
        default_model="mistral-medium-latest",
        key_var="MISTRAL_API_KEY", transport=LITELLM,
        key_url="https://console.mistral.ai/api-keys",
    ),
    Provider(
        # Runs on the machine. No key, no quota, no data leaving the laptop —
        # which is the only option if a document may not go to a vendor at all.
        name="ollama", label="Ollama (chạy trên máy / local)",
        default_model="ollama/llama3.1",
        key_var=None, transport=LITELLM,
        key_url="https://ollama.com/download",
    ),
)

PROVIDERS = {p.name: p for p in _REGISTRY}
DEFAULT_PROVIDER = "gemini"

# Read at call time, not import: the desktop app writes these into the
# environment when the user changes them mid-session.
PROVIDER_VAR = "HECATE_PROVIDER"
MODEL_VAR = "HECATE_MODEL"


def get(name) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Unknown provider {name!r}; registered: {sorted(PROVIDERS)}"
        ) from None


def selected() -> Provider:
    """The provider this run should use."""
    return get((os.environ.get(PROVIDER_VAR) or DEFAULT_PROVIDER).strip().lower())


def model_for(provider) -> str:
    """The model to ask for, honouring an override if one is set."""
    return (os.environ.get(MODEL_VAR) or "").strip() or provider.default_model


def has_key(provider) -> bool:
    return provider.key_var is None or bool(os.environ.get(provider.key_var))


def litellm_available() -> bool:
    """Is the router actually present in THIS build?

    Checked rather than assumed. A settings screen that offers a provider the
    build cannot reach is worse than one that offers fewer: the person picks
    it, saves it, runs, and only then discovers a dead end — and if the person
    who could install the missing package has left, it stays a dead end.
    """
    try:
        import litellm            # noqa: F401
        return True
    except Exception:
        return False


def available(provider) -> bool:
    """Can this provider actually be called from this build?"""
    return provider.transport == DIRECT or litellm_available()


def describe() -> dict:
    """What the settings screen needs to render, without leaking the key."""
    provider = selected()
    return {
        "provider": provider.name,
        "label": provider.label,
        "model": model_for(provider),
        "needs_key": provider.key_var is not None,
        "has_key": has_key(provider),
        "key_url": provider.key_url,
        "available": available(provider),
        "litellm": litellm_available(),
        "choices": [{"name": p.name, "label": p.label,
                     "default_model": p.default_model,
                     "needs_key": p.key_var is not None,
                     "key_url": p.key_url,
                     "available": available(p)}
                    for p in _REGISTRY],
    }


# --------------------------------------------------------------- calling

def _call_direct(provider, model, prompt) -> str:
    """Gemini's own client — the path every published number came through."""
    from google import genai
    client = genai.Client(api_key=os.environ[provider.key_var])
    return client.models.generate_content(model=model, contents=prompt).text


def _call_litellm(provider, model, prompt) -> str:
    try:
        import litellm
    except ImportError:
        raise RuntimeError(
            f"{provider.label} needs the 'litellm' package, which is not "
            "installed in this build. Install it, or switch back to "
            f"{PROVIDERS[DEFAULT_PROVIDER].label} in settings.") from None
    # LiteLLM addresses models as "<vendor>/<model>". Ollama's default already
    # carries its prefix, so only add one where it is missing.
    target = model if "/" in model else f"{provider.name}/{model}"
    response = litellm.completion(
        model=target, messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content


def complete(prompt) -> str:
    """One prompt, one reply, from whichever provider is configured."""
    provider = selected()
    model = model_for(provider)
    if provider.key_var and not os.environ.get(provider.key_var):
        raise RuntimeError(
            f"{provider.label} is selected but {provider.key_var} is not set. "
            f"Add a key in settings, or get one at {provider.key_url}.")
    call = _call_direct if provider.transport == DIRECT else _call_litellm
    return call(provider, model, prompt)


def parse_json_array(raw):
    """The reply, as the JSON array every schema expects.

    Models fence code even when told not to. Stripping it here rather than in
    the caller means every provider is forgiven the same way, instead of one
    of them quietly returning a string that fails schema validation.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _check():
    """Reject a half-declared provider at import."""
    if DEFAULT_PROVIDER not in PROVIDERS:
        raise ValueError(
            f"DEFAULT_PROVIDER {DEFAULT_PROVIDER!r} is not registered")
    if len(PROVIDERS) != len(_REGISTRY):
        raise ValueError("two providers share a name")
    for provider in _REGISTRY:
        if not provider.name or not provider.label:
            raise ValueError(f"provider {provider.name!r} is missing a name or label")
        if not provider.default_model:
            raise ValueError(
                f"provider {provider.name!r} declares no default_model; the "
                "call would be made with no model and fail at the API.")
        if provider.transport not in (DIRECT, LITELLM):
            raise ValueError(
                f"provider {provider.name!r} has transport "
                f"{provider.transport!r}; expected {DIRECT!r} or {LITELLM!r}")
        if provider.key_var is None and provider.transport == DIRECT:
            raise ValueError(
                f"provider {provider.name!r} has a direct client but no key "
                "variable; the client below would read a name that is None.")


_check()
