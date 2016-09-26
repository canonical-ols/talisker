import socket

PORT = 8125
BUFSIZE = 512

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PORT))
while 1:
    data, addr = sock.recvfrom(BUFSIZE)
    print(data)
