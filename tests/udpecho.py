import socket
import sys

PORT = 8125
BUFSIZE = 512

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PORT))
while 1:
    data, addr = sock.recvfrom(BUFSIZE)
    sys.stderr.buffer.write(data + b'\n')
    sys.stderr.buffer.flush()
