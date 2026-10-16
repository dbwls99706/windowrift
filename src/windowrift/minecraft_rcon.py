"""Authenticated Minecraft Java Edition RCON, restricted to loopback."""
from __future__ import annotations
import socket
import struct
import threading

class RconError(RuntimeError):
    pass

class RconClient:
    def __init__(self, password: str, *, host: str='127.0.0.1', port: int=25575, timeout: float=8.0):
        if host not in {'127.0.0.1','localhost','::1'}:
            raise ValueError('RCON must bind to loopback')
        if not password:
            raise ValueError('RCON password is required')
        if not 1<=port<=65535 or not 0.1<=timeout<=30:
            raise ValueError('Invalid RCON port or timeout')
        self.host,self.port,self.password,self.timeout=host,port,password,timeout
        self._sequence=1
        self._lock=threading.Lock()

    @staticmethod
    def _recv_exact(sock: socket.socket,count:int)->bytes:
        result=bytearray()
        while len(result)<count:
            data=sock.recv(count-len(result))
            if not data:
                raise RconError('RCON connection closed prematurely')
            result.extend(data)
        return bytes(result)

    @classmethod
    def _read_packet(cls,sock:socket.socket)->tuple[int,int,str]:
        (length,)=struct.unpack('<i',cls._recv_exact(sock,4))
        if not 10<=length<=8192:
            raise RconError('Malformed RCON packet')
        body=cls._recv_exact(sock,length)
        rid,kind=struct.unpack_from('<ii',body)
        if body[-2:]!=b'\x00\x00':
            raise RconError('Malformed RCON terminator')
        return rid,kind,body[8:-2].decode('utf-8',errors='replace')

    @staticmethod
    def _packet(rid:int,kind:int,text:str)->bytes:
        payload=struct.pack('<ii',rid,kind)+text.encode('utf-8')+b'\x00\x00'
        if len(payload)>8192:
            raise ValueError('Oversized RCON command')
        return struct.pack('<i',len(payload))+payload

    def command(self,query:str)->str:
        if not query or any(ch in query for ch in '\r\n\x00') or len(query)>1024:
            raise ValueError('Invalid RCON command')
        with self._lock:
            req=self._sequence
            self._sequence=(req+2)%0x7ffffffe+1
            try:
                with socket.create_connection((self.host,self.port),timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(self._packet(req,3,self.password))
                    for _ in range(3):
                        rid,kind,_=self._read_packet(sock)
                        if rid==-1:
                            raise RconError('RCON authentication failed')
                        if rid==req and kind==2:
                            break
                    else:
                        raise RconError('RCON auth response missing')
                    sock.sendall(self._packet(req+1,2,query))
                    for _ in range(3):
                        rid,kind,response=self._read_packet(sock)
                        if rid==req+1:
                            return response
                        if rid==-1:
                            raise RconError('RCON command rejected')
                    raise RconError('RCON command response missing')
            except (OSError,struct.error) as exc:
                raise RconError(f'RCON transport error: {exc}') from exc
