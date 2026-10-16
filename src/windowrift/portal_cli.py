"""Capability-first CLI for application-owned native state adapters."""
from __future__ import annotations
from dataclasses import asdict
import argparse
import json
import os
from pathlib import Path

from .portal_api import AdapterRegistry, PortalError
from .minecraft_transfer import MinecraftTransfer, TransferError
from .minecraft_mobs import MinecraftMobs
from .minecraft_adapters import MinecraftBlockAdapter, MinecraftMobAdapter
from .minecraft_rcon import RconClient, RconError
from .minecraft_cli import parse_location
from .http_adapter import LocalAppAdapter


def parser_factory():
    parser = argparse.ArgumentParser(description="WindowRift native object handoff")
    parser.add_argument("--app", choices=("minecraft-java:block", "minecraft-java:mob", "local-http"))
    parser.add_argument("--port", type=int, default=25575)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--vault", type=parse_location)
    parser.add_argument("--url", default="http://127.0.0.1:8791")
    cmds = parser.add_subparsers(dest="command", required=True)
    cmds.add_parser("adapters")
    cmds.add_parser("list")
    cmds.add_parser("recover")
    take = cmds.add_parser("take")
    take.add_argument("--tag")
    take.add_argument("--type", default="minecraft:zombie")
    take.add_argument("--at", type=parse_location)
    take.add_argument("--material")
    take.add_argument("--id")
    put = cmds.add_parser("put")
    put.add_argument("object_id")
    put.add_argument("--at", type=parse_location)
    put.add_argument("--destination")
    move = cmds.add_parser("move")
    move.add_argument("object_id")
    move.add_argument("--x", type=int, required=True)
    move.add_argument("--y", type=int, required=True)
    return parser


def select_adapter(args):
    if not args.app:
        raise PortalError("Select an application with --app")
    if args.app == "local-http":
        return LocalAppAdapter(args.url, os.environ.get("WINDOWRIFT_APP_TOKEN", ""))
    secret = os.environ.get("WINDOWRIFT_RCON_PASSWORD")
    if not secret:
        raise PortalError("Set WINDOWRIFT_RCON_PASSWORD privately in the environment")
    server = RconClient(secret, port=args.port)
    if args.app == "minecraft-java:block":
        return MinecraftBlockAdapter(MinecraftTransfer(
            server, args.ledger or Path.home() / ".local/share/windowrift/real-minecraft.json",
            vault_base=args.vault or (10000, 300, 10000)))
    return MinecraftMobAdapter(MinecraftMobs(
        server, args.ledger or Path.home() / ".local/share/windowrift/real-mobs.json",
        vault_base=args.vault or (10300, 300, 10300)))


def run(args):
    if args.command == "adapters":
        return {
            "version": "v1", "universal_native_support": False,
            "builtins": [asdict(MinecraftBlockAdapter.capability),
                         asdict(MinecraftMobAdapter.capability)],
            "app_extension_protocol": "windowrift.portal_api.ApplicationAdapter",
            "local_http_protocol": "/windowrift/v1/",
        }
    adapter = select_adapter(args)
    reg = AdapterRegistry()
    reg.register(adapter)
    if args.command == "list":
        return {"app": adapter.capability.app, "capability": asdict(adapter.capability),
                "objects": [asdict(x) for x in adapter.objects()]}
    if args.command == "take":
        if args.app == "minecraft-java:block":
            if args.at is None or not args.material:
                raise PortalError("Block take needs --at and --material")
            state = adapter.take(args.at, args.material)
        elif args.app == "minecraft-java:mob":
            if not args.tag:
                raise PortalError("Mob take needs --tag")
            state = adapter.take(args.tag, args.type)
        else:
            if not args.id:
                raise PortalError("Local app take needs --id")
            state = adapter.take(args.id)
        return {"object": asdict(state)}
    if args.command == "put":
        if args.app == "local-http":
            if args.destination is None:
                raise PortalError("Use --destination with a JSON object")
            try:
                dest = json.loads(args.destination)
            except ValueError as exc:
                raise PortalError("Invalid destination JSON") from exc
        else:
            if args.at is None:
                raise PortalError("Minecraft return needs --at x,y,z")
            dest = args.at
        return {"object": asdict(adapter.put(args.object_id, dest))}
    if args.command == "move":
        return {"object": asdict(adapter.move(args.object_id, args.x, args.y))}
    if args.command == "recover":
        return {"recovered": adapter.recover()}
    raise PortalError("Unknown operation")


def main():
    parser = parser_factory()
    args = parser.parse_args()
    try:
        result = run(args)
    except (PortalError, TransferError, RconError, OSError, ValueError) as exc:
        parser.exit(2, "WindowRift: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
