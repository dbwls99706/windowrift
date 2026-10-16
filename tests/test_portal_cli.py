from windowrift.portal_cli import parser_factory, run

def test_capabilities_dont_need_running_game_or_secrets():
    args = parser_factory().parse_args(["adapters"])
    report = run(args)
    assert report["universal_native_support"] is False
    assert {r["app"] for r in report["builtins"]} == {
        "minecraft-java:block", "minecraft-java:mob"
    }
