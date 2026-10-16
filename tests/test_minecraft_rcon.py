import socket,struct,threading
import pytest
from windowrift.minecraft_rcon import RconClient,RconError

def test_protocol_roundtrip_with_real_tcp_socket():
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen(1)
    port=listener.getsockname()[1]
    seen=[]
    def server():
        with listener:
            conn,_=listener.accept()
            with conn:
                def packet():
                    data=b''
                    length=struct.unpack('<i',conn.recv(4))[0]
                    while len(data)<length:
                        data+=conn.recv(length-len(data))
                    rid,kind=struct.unpack('<ii',data[:8])
                    return rid,kind,data[8:-2].decode()
                rid,kind,password=packet()
                assert kind==3 and password=='pass'
                conn.sendall(RconClient._packet(rid,0,''))
                conn.sendall(RconClient._packet(rid,2,''))
                rid,kind,msg=packet()
                seen.append(msg)
                conn.sendall(RconClient._packet(rid,0,'Test passed, count: 1'))
    thread=threading.Thread(target=server,daemon=True)
    thread.start()
    assert RconClient('pass',port=port).command('list')=='Test passed, count: 1'
    thread.join(timeout=2)
    assert seen==['list']

def test_security_and_malformed_queries():
    with pytest.raises(ValueError):
        RconClient('pass',host='8.8.8.8')
    with pytest.raises(ValueError):
        RconClient('')
    with pytest.raises(ValueError):
        RconClient('pass').command('say hi\nstop')
    with pytest.raises(RconError):
        RconClient('pass',port=1,timeout=.2).command('list')
