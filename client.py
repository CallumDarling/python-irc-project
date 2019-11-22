import socket
import sys

CRLF='\0xD\0xA'

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((socket.gethostname(), 1234))


    while True:
        msg = s.recv(1024)
        print(msg)

        line = sys.stdin.readline()
        line = line.replace("\n", "\r\n")
        msg = line.encode()
        s.send(msg)


if __name__  == "__main__":
    main()
