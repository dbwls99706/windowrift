"""Minecraft Java Edition real world transfer CLI."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from .minecraft_rcon import RconClient,RconError
from .minecraft_transfer import MinecraftTransfer,TransferError,coord,MATERIALS

def parse_location(raw:str):
    try:
        return coord(*(int(v.strip()) for v in raw.split(',')))
    except (TypeError,ValueError) as exc:
        raise argparse.ArgumentTypeError('Expected Minecraft x,y,z') from exc

def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description='Real Minecraft Java blocks → desktop → Minecraft')
    p.add_argument('--host',default='127.0.0.1',help='Loopback only')
    p.add_argument('--port',type=int,default=25575)
    p.add_argument('--ledger',type=Path,default=Path.home()/'.local/share/windowrift/real-minecraft.json')
    p.add_argument('--vault',type=parse_location,default=(10000,300,10000))
    p.add_argument('--dimension',choices=['minecraft:overworld','minecraft:the_nether','minecraft:the_end'],default='minecraft:overworld')
    sub=p.add_subparsers(dest='action',required=True)
    take=sub.add_parser('take',help='Take an actual block into world escrow')
    take.add_argument('--at',type=parse_location,required=True)
    take.add_argument('--material',required=True,choices=sorted(MATERIALS))
    put=sub.add_parser('put',help='Return same block state to real world')
    put.add_argument('id')
    put.add_argument('--at',type=parse_location,required=True)
    pick=sub.add_parser('pick',help='Take a placed block using same ID')
    pick.add_argument('id')
    sub.add_parser('recover')
    sub.add_parser('list')
    sub.add_parser('ping')
    return p

def run(args:argparse.Namespace)->dict:
    password=os.environ.get('WINDOWRIFT_RCON_PASSWORD','')
    if not password:
        raise TransferError('Set WINDOWRIFT_RCON_PASSWORD, never pass it on the command line')
    server=RconClient(password,host=args.host,port=args.port)
    if args.action=='ping':
        return {'minecraft_server':server.command('list')}
    transfer=MinecraftTransfer(server,args.ledger,vault_base=args.vault,dimension=args.dimension)
    if args.action=='take':
        return {'block':vars(transfer.take(args.at,args.material))}
    if args.action=='put':
        return {'block':vars(transfer.put(args.id,args.at))}
    if args.action=='pick':
        return {'block':vars(transfer.pick_up(args.id))}
    if args.action=='recover':
        return {'repaired':transfer.recover(),'blocks':[vars(b) for b in transfer.snapshot()]}
    return {'blocks':[vars(b) for b in transfer.snapshot()]}

def main()->None:
    parser=build_parser()
    args=parser.parse_args()
    try:
        result=run(args)
    except (TransferError,RconError,OSError,ValueError,KeyError) as exc:
        parser.exit(2,f'WindowRift Minecraft: {exc}\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
