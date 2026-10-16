"""State-backed Minecraft Java Edition world ↔ desktop block transfer.

Blocks are stored inside a reserved Minecraft world vault, not as image crops.
This is experimental and requires a separately owned vanilla 1.21.1 server.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import json,os,re,tempfile
from pathlib import Path
from typing import Protocol
from uuid import uuid4

class TransferError(RuntimeError):
    pass

Coord=tuple[int,int,int]
MATERIALS=frozenset({
    'minecraft:stone','minecraft:dirt','minecraft:grass_block',
    'minecraft:oak_planks','minecraft:spruce_planks','minecraft:birch_planks',
    'minecraft:cobblestone','minecraft:bricks','minecraft:glass',
    'minecraft:oak_stairs','minecraft:spruce_stairs',
    'minecraft:oak_log','minecraft:birch_log','minecraft:sand',
    'minecraft:deepslate','minecraft:polished_andesite',
})
DIMENSIONS=frozenset({'minecraft:overworld','minecraft:the_nether','minecraft:the_end'})

def coord(x:int,y:int,z:int)->Coord:
    if any(type(v) is not int or abs(v)>29000000 for v in (x,y,z)) or not -64<=y<=319:
        raise ValueError('Coordinates out of Minecraft 1.21.1 bounds')
    return x,y,z

def xyz(p:Coord)->str:
    return ' '.join(str(i) for i in p)

class GameCommands(Protocol):
    def command(self,query:str)->str: ...

def _write_json(path:Path,data:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.windowrift-mc-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,sort_keys=True,indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,path)
        if os.name!='nt':
            handle=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(handle)
            finally:os.close(handle)
    finally:
        if os.path.exists(temp):os.unlink(temp)

@dataclass
class BlockIdentity:
    id:str
    material:str
    dimension:str
    source:Coord
    vault:Coord
    phase:str='taking'
    destination:Coord|None=None
    revision:int=0
    screen_x:int=420
    screen_y:int=180
    origin:Coord|None=None

    @classmethod
    def parse(cls,raw:dict)->'BlockIdentity':
        if not isinstance(raw,dict) or raw.get('material') not in MATERIALS or raw.get('dimension') not in DIMENSIONS:
            raise TransferError('Invalid saved material or dimension')
        if not re.fullmatch('[0-9a-f]{32}',str(raw.get('id',''))):
            raise TransferError('Invalid saved block ID')
        if raw.get('phase') not in {'taking','outside','placing','placed'}:
            raise TransferError('Invalid saved phase')
        src,vault=(coord(*raw[n]) for n in ('source','vault'))
        dest=coord(*raw['destination']) if raw.get('destination') is not None else None
        if raw['phase']=='placing' and dest is None:
            raise TransferError('Missing pending destination')
        return cls(raw['id'],raw['material'],raw['dimension'],src,vault,raw['phase'],
                   dest,int(raw.get('revision',0)),
                   int(raw.get('screen_x',420)),int(raw.get('screen_y',180)),
                   coord(*raw['origin']) if raw.get('origin') is not None else src)

class MinecraftTransfer:
    """World-state-first block transfer. Only ordinary whitelisted blocks allowed."""
    def __init__(self,backend:GameCommands,ledger:Path,*,vault_base:Coord=(10000,300,10000),
                 dimension:str='minecraft:overworld')->None:
        self.backend=backend
        self.ledger=Path(ledger)
        self.vault_base=coord(*vault_base)
        if dimension not in DIMENSIONS:
            raise ValueError('Unsupported dimension')
        self.dimension=dimension
        if self.ledger.exists():
            raw=json.loads(self.ledger.read_text(encoding='utf-8'))
            if raw.get('version')!=1 or raw.get('dimension')!=dimension or raw.get('vault_base')!=list(vault_base):
                raise TransferError('Saved world and selected vault mismatch')
            self.records={r.id:r for r in (BlockIdentity.parse(z) for z in raw['records'])}
        else:
            self.records:dict[str,BlockIdentity]={}
        if len(self.records)>32:
            raise TransferError('Too many tracked world objects')

    def _save(self)->None:
        _write_json(self.ledger,{'version':1,'dimension':self.dimension,
            'vault_base':list(self.vault_base),'records':[asdict(x) for x in self.records.values()]})

    def _query(self,statement:str)->str:
        result=self.backend.command(f'execute in {self.dimension} run {statement}')
        if not isinstance(result,str):
            raise TransferError('Invalid Minecraft response')
        return result

    @staticmethod
    def _true(result:str)->bool:
        response=re.sub(r'§.','',result).lower()
        if any(s in response for s in ('test passed','found 1 block','test successful')):
            return True
        if any(s in response for s in ('test failed','failed','found 0 block')):
            return False
        raise TransferError(f'Unrecognized Minecraft test result: {response[:120]!r}')

    def _is(self,at:Coord,material:str)->bool:
        return self._true(self._query(f'execute if block {xyz(at)} {material}'))

    def _equal(self,a:Coord,b:Coord)->bool:
        return self._true(self._query(f'execute if blocks {xyz(a)} {xyz(a)} {xyz(b)} all'))

    def _must_change(self,instruction:str,kind:str)->None:
        response=re.sub(r'§.','',self._query(instruction)).lower()
        match={'clone':('cloned',),'setblock':('changed the block','block changed')}
        if not any(t in response for t in match[kind]):
            raise TransferError(f'World edit not confirmed by Minecraft: {response[:160]!r}')

    def _load(self,p:Coord)->None:
        result=self._query(f'forceload add {p[0]} {p[2]}').lower()
        if not any(s in result for s in ('marked','force','already')):
            raise TransferError(f'Could not load world chunk: {result[:120]!r}')

    def _copy(self,source:Coord,target:Coord)->None:
        self._must_change(f'clone {xyz(source)} {xyz(source)} {xyz(target)} replace force','clone')
        if not self._equal(source,target):
            raise TransferError('World clone did not preserve block state')

    def _air(self,p:Coord)->None:
        self._must_change(f'setblock {xyz(p)} minecraft:air replace','setblock')
        if not self._is(p,'minecraft:air'):
            raise TransferError('Minecraft did not clear expected block')

    def _reserve(self)->Coord:
        used={r.vault[0]-self.vault_base[0] for r in self.records.values()}
        for index in range(32):
            if index not in used:
                return coord(self.vault_base[0]+index,self.vault_base[1],self.vault_base[2])
        raise TransferError('No free vault cells')

    def take(self,source:Coord,material:str)->BlockIdentity:
        source=coord(*source)
        if material not in MATERIALS:
            raise TransferError(f'Unsupported or unsafe block: {material}')
        vault=self._reserve()
        if source==vault or any(r.vault==source for r in self.records.values()):
            raise TransferError('Source is a reserved vault cell')
        self._load(source)
        self._load(vault)
        if not self._is(source,material):
            raise TransferError('Source block type mismatch; nothing removed')
        if not self._is(vault,'minecraft:air'):
            raise TransferError('Reserved vault occupied; nothing removed')
        block=BlockIdentity(uuid4().hex,material,self.dimension,source,vault,origin=source)
        self.records[block.id]=block
        self._save()
        self._copy(source,vault)
        self._air(source)
        block.phase='outside'
        self._save()
        return block

    def put(self,object_id:str,destination:Coord)->BlockIdentity:
        block=self.records.get(object_id)
        if block is None or block.phase!='outside':
            raise TransferError('Block is not outside the game')
        destination=coord(*destination)
        if any(r.vault==destination for r in self.records.values()):
            raise TransferError('Cannot put block into reserved vault')
        self._load(destination)
        self._load(block.vault)
        if not self._is(destination,'minecraft:air'):
            raise TransferError('Destination occupied; original block stays in vault')
        if not self._is(block.vault,block.material):
            raise TransferError('Vault contents do not match tracked block')
        block.phase,block.destination='placing',destination
        self._save()
        self._copy(block.vault,destination)
        self._air(block.vault)
        block.phase,block.source='placed',destination
        block.revision+=1
        self._save()
        return block

    def pick_up(self,object_id:str)->BlockIdentity:
        block=self.records.get(object_id)
        if block is None or block.phase!='placed':
            raise TransferError('Only placed blocks can be picked up')
        self._load(block.source)
        self._load(block.vault)
        if not self._is(block.source,block.material) or not self._is(block.vault,'minecraft:air'):
            raise TransferError('Minecraft state changed; refusing pickup')
        block.phase,block.destination='taking',None
        self._save()
        self._copy(block.source,block.vault)
        self._air(block.source)
        block.phase='outside'
        block.revision+=1
        self._save()
        return block

    def recover(self)->list[str]:
        repaired=[]
        for block in self.records.values():
            if block.phase not in ('taking','placing'):continue
            self._load(block.source)
            self._load(block.vault)
            if block.phase=='taking':
                if self._is(block.source,block.material):
                    if self._is(block.vault,block.material) and self._equal(block.source,block.vault):
                        self._air(block.vault)
                    elif not self._is(block.vault,'minecraft:air'):
                        raise TransferError('Conflicting vault; manual intervention required')
                    block.phase='placed'
                elif self._is(block.source,'minecraft:air') and self._is(block.vault,block.material):
                    block.phase='outside'
                else:raise TransferError('Block missing during pickup recovery')
            else:
                assert block.destination is not None
                self._load(block.destination)
                if self._is(block.destination,block.material):
                    if self._is(block.vault,block.material) and self._equal(block.destination,block.vault):
                        self._air(block.vault)
                    elif not self._is(block.vault,'minecraft:air'):
                        raise TransferError('Conflicting vault during placement recovery')
                    block.phase,block.source='placed',block.destination
                    block.revision+=1
                elif self._is(block.destination,'minecraft:air') and self._is(block.vault,block.material):
                    block.phase='outside'
                    block.destination=None
                else:raise TransferError('Conflicting destination; refusing recovery')
            repaired.append(block.id)
            self._save()
        return repaired

    def move_desktop(self,object_id:str,x:int,y:int)->BlockIdentity:
        block=self.records.get(object_id)
        if block is None or block.phase!='outside':
            raise TransferError('Only an outside block can be dragged')
        if type(x) is not int or type(y) is not int or max(abs(x),abs(y))>32768:
            raise ValueError('Desktop coordinates out of range')
        block.screen_x,block.screen_y=x,y
        self._save()
        return block

    def snapshot(self)->list[BlockIdentity]:
        return list(self.records.values())
