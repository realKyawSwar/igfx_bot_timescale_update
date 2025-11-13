from src.igfx_bot import runner


def test_resolve_mode_prefers_cli():
    assert runner._resolve_mode("live", "demo") == "LIVE"


def test_resolve_mode_defaults_to_demo_on_unknown():
    assert runner._resolve_mode(None, "paper") == "DEMO"


def test_resolve_ig_env_names_mode_specific_overrides():
    ig_cfg = {
        "api_key_env": "IG_API_KEY",
        "credentials": {
            "LIVE": {
                "api_key_env": "IG_API_KEY_LIVE",
                "username_env": "IG_USERNAME_LIVE",
            }
        },
    }

    env_names = runner._resolve_ig_env_names(ig_cfg, "LIVE")

    assert env_names["api_key_env"] == "IG_API_KEY_LIVE"
    assert env_names["username_env"] == "IG_USERNAME_LIVE"
    # Returns None when neither a mode-specific nor top-level value exists
    assert env_names["password_env"] is None


def test_resolve_ig_env_names_uses_top_level_defaults():
    ig_cfg = {
        "api_key_env": "IG_API_KEY",
        "username_env": "IG_USERNAME",
        "password_env": "IG_PASSWORD",
    }

    env_names = runner._resolve_ig_env_names(ig_cfg, "DEMO")

    assert env_names["api_key_env"] == "IG_API_KEY"
    assert env_names["username_env"] == "IG_USERNAME"
    assert env_names["password_env"] == "IG_PASSWORD"
