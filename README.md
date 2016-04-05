This module uses the network module to create a server, and implements http(s)
and WebSockets over those connections.  The most useful part of it is the RPC
over WebSocket protocol.  With only 6 lines of code you have a working system:

    import websocketd
    
    class Rpc:
        def __init__(self, remote):
            self.remote = remote
    
    s = websocketd.RPChttpd(8000, Rpc)
    websocketd.fgloop()

You only have to add what you want your server to do.  Any connection to the
server (in this case it listens on port 8000) causes an Rpc object to be
instanced.  Any calls made through that connection will cause method calls on
that object.  If the remote side supports the same protocol, calls can be made
on it by calling methods on remote.

Please see example/server for more details on how to use this module.
