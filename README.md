# TLS bidirectional tunnel
### This script allows you to forward ports from/to a computer behind NAT, simply, without setup and installation.
- Two functionally identical modes are supported - **client** and **server**. Thus, port forwarding can be used in both directions: from the client to the server and from the server to the client.
- Connection - encrypted over TLS, even insecure traffic (for example VNC viewer for Mac) can be transfered securely.
- The server requires both a key and a certificate in PEM format.
- For the client to work - only a certificate is required (to verify that the certificate has not been spoofed in the event of a man-in-the-middle attack).
- A single connection is created that aggregates all connections through the forwarded ports.
- Ports remapping is supported.
- Protocol version based on the source file content.
### A typical use cases:
#### Help:
```
python tunnel.py client -h
python tunnel.py server -h
```
#### Client:
```
python tunnel.py client my.server.com 12345
python tunnel.py client my.server.com 12345 --forward 22
python tunnel.py client my.server.com 12345 --forward 3899 --cert my_certificate.cert
python tunnel.py client my.server.com 12345 --mapping 22:10022 5900:15900
python tunnel.py client my.server.com 12345 --forward 22 3899 --mapping 22:10022 5900:15900
```
#### Server:
```
python tunnel.py server 12345
python tunnel.py server 12345 --mapping 22:10022 5900:15900
python tunnel.py server 12345 --cert my_certificate.cert --key my_private_key.key
python tunnel.py server 12345 --forward 22 5900 3899
python tunnel.py server 12345 --forward 22 5900 3899 --mapping 22:10022 5900:15900
```
