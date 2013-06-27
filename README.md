This module uses the network module to create a server, and implements http(s)
and WebSockets over those connections.  With only 6 lines of code you have a
working system:

  import wshttpd
  import network
  
  class Connection (wshttpd.Wshttpd):
  	pass
  
  s = network.Server (8000, Connection, tls = 'key.pem')
  network.fgloop ()

You only have to add what you want your server to do.

Please see example/server for more details on how to use this module.
