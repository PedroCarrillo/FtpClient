import sys, posix, string, getpass, re, os
from socket import *

# static variables

BufferSize = 1024
FTP_PORT = 21
CRLF = '\r\n'

# FTP RESPONSE CODES
LOGIN_INCORRECT = "530"
PASSWORD_REQUIRED = "331"

class PedroFTP:

    clientSocket = None
    file = None
    authenticated = False

    def main(self):
        hostname = sys.argv[1]
        self.init(hostname)

    def init(self, hostname):
        print("Attempting connection to "+hostname)
        self.clientSocket = socket(AF_INET, SOCK_STREAM)
        self.clientSocket.connect((hostname, FTP_PORT))
        self.file = self.clientSocket.makefile('rb')
        self.readMultiline()
        while self.clientSocket != None:
            # print "are you authenticated? %s" %self.authenticated
            if not self.authenticated:
                self.login()
            else:
                query = raw_input("pedroFTP>")
                if (query == "quit"):
                    self.logout()
                elif("ls" in query[:2]):
                    self.list(query)
                elif("cd" in query[:2]):
                    self.cwd(query)
                elif("get" in query[:3]):
                    self.get(query)
                elif("put" in query[:3]):
                    self.put(query)
                elif("delete" in query[:6]):
                    self.delete(query)
                else:
                    print "unknown command"+CRLF

    # Navigating through the directories
    # example: cd Documents
    def cwd(self, query):
        query = self.cleanQuery(query, 3) # removing "cd"
        if (query == '..'):
            self.sendCommand('CDUP')
        else:
            self.sendCommand('CWD '+query)
        print self.readMultiline()

    # Starting the login process. If no user, password won't be required and the request will be sent empty.
    def login(self):
        userQuery = raw_input("Username: ")
        self.sendCommand('USER '+userQuery)
        response = self.readMultiline()
        print response
        if PASSWORD_REQUIRED in response:
            passwordQuery = getpass.getpass('Password:')
            self.sendCommand('PASS '+passwordQuery)
            print self.readMultiline()
        self.authenticated = LOGIN_INCORRECT not in response

    # DEL command to delete file on ftp server
    def delete(self, path):
        path = self.cleanQuery(path, 6)
        self.sendCommand('DELE'+path)
        print self.readMultiline()

    # List all the files in the directory. If null is sent it will take the current directory as default
    def list(self, path):
        path = self.cleanQuery(path, 2) # removing "ls"
        self.getAsciiFile("LIST")

    # Login out of ftp connection and disabling the socket.
    def logout(self):
        self.sendCommand('QUIT')
        print self.readLine()
        self.clientSocket.close()
        clientSocket = None
        exit()

    # Download a file creating a new one from the name in the end of the path and then copying the binary data into it..
    # Example: get Documents/Arduino/libraries/readme.txt
    # Example: get readme.txt
    def get(self, path):
        path = self.cleanQuery(path, 4)
        command = 'RETR ' + path
        head, tail = os.path.split(path)
        newFile = open(tail, "w+")
        self.getBinaryFile(command, newFile)
        print "Success. %s bytes received" % newFile.tell()
        newFile.close()

    # Upload a file using STOR command.
    # Example: put Documents/Arduino/libraries/readme.txt
    # Example: put testimage.png
    def put(self, path):
        path = self.cleanQuery(path, 4)
        file = open(path, 'rb')
        command = 'STOR '+path
        self.uploadBinaryFile(command, file)
        print "Success. %s bytes uploaded" % file.tell()
        file.close()

    # Send the command to socket
    def sendCommand(self, command):
        command += CRLF
        self.clientSocket.sendall(command)

    # Helper line to read the last line from the file created from socket.
    def readLine(self):
        line = self.file.readline()
        if line[-2:] == CRLF:
            line = line[:-2]
        return line

    # reading multiple lines until there is no more lines.
    def readMultiline(self):
        line = self.readLine()
        if line[3:4] == '-':
            code = line[:3]
            while 1:
                nextLine = self.readLine()
                line = line + ('\n' + nextLine)
                if nextLine[:3] == code and \
                                nextLine[3:4] != '-':
                    break
        return line

    # Cleaning the queries to be sent to the server with a custom number of characters
    def cleanQuery(self, rawQuery, numberOfCharacters):
        cleanQuery = rawQuery[numberOfCharacters:]
        return cleanQuery

    # Uploading files command. Creating a data socket connection in order to send the bytes through that socket.
    def uploadBinaryFile(self, command, file):
        self.sendCommand('TYPE I')
        responseTypeI = self.readLine()
        print responseTypeI
        dataSocket = self.startConnectionToPassivePort(command)
        while 1:
            data = file.readline(BufferSize)
            if not data: break
            dataSocket.sendall(data)
        dataSocket.close()
        print self.readMultiline()

    # In order to download a file we need to create a passive connection to download the file
    def getBinaryFile(self, command, file = None):
        self.sendCommand('TYPE I')
        responseTypeI = self.readLine()
        print responseTypeI
        dataSocket = self.startConnectionToPassivePort(command)
        while 1:
            bytesInfo = dataSocket.recv(BufferSize)
            if (file is not None):
                file.write(bytesInfo)
            if not bytesInfo: break
        dataSocket.close()
        print self.readMultiline()


    # In order to download a file we need to create a passive connection to download the file
    # if no file specified it will print out the message
    def getAsciiFile(self, command, file = None):
        self.sendCommand('TYPE A')
        responseTypeA = self.readLine()
        print responseTypeA
        dataSocket = self.startConnectionToPassivePort(command)
        fp = dataSocket.makefile('rb')
        while 1:
            line = fp.readline()
            if not line:
                break
            if line[-2:] == CRLF:
                line = line[:-2]
            elif line[-1:] == '\n':
                line = line[:-1]
            if (file is None):
                print line
            else:
                file.write(line)
        fp.close()
        dataSocket.close()
        self.readMultiline()

    # Initiate the passive mode (PASV) and obtain the host and port information from the response to start the data connection
    # Using regexp to parse the string received in the format (h1,h2,h3,h4,p1,p2) and then translating them to host ip and port
    def infoOfServerPassivePort(self):
        self.sendCommand('PASV')
        responsePASV = self.readLine()
        print responsePASV
        values = re.findall('\d+', self.cleanQuery(responsePASV, 3))
        host = '.'.join(values[:4])
        port = (int(values[4]) << 8) + int(values[5])
        return host, port

    # Based on socket.py create_connection I couldn't use it for some reason.
    def startConnectionToPassivePort(self, command):
        host, port = self.infoOfServerPassivePort()
        print host, port
        dataSocket = None
        for res in getaddrinfo(host, port, 0, SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            dataSocket = socket(af, socktype, proto)
            dataSocket.connect(sa)
            self.sendCommand(command)
            print self.readLine()
        return dataSocket


PedroFTP.main(PedroFTP())