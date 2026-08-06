#script uses udp broadcasts and a dedicated host port to connect clients with a mesh topology

import subprocess

#for rec
import struct
import pickle

#for the networking
import socket
import threading
import time
import readline
import sys
import json
import os

discovery_code = "DISCOVERY_PACKET"
disconnect_code = "CLIENT_DISCONNECT" 

server_sock = None
port = 5630
incremented_port = 5631
CONN_LIST = []
debug = True

    

encryption_key = ""

mcast_ip = "224.0.0.251"
mcast_group = '224.1.1.1'
upd_port = 56302
ttl = 10

project_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(project_dir, 'config.json')
notify_path = os.path.join(project_dir, 'simple_notification.scpt')


data_list = []

class packet:
    def __init__(self, conn_port: str, name: str, type: str, key: str):
        self.port = conn_port
        self.name = name
        self.type = type
        self.key = key


udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_sock.bind(('', upd_port))
mreq = struct.pack("4si", socket.inet_aton(mcast_group), socket.INADDR_ANY)
udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)


#encryption
def encrypt(data, key) -> str:
    return ''.join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data))


#gets your ip to prevent self connections
def get_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        return ip_address
    
self_ip = get_ip()

#closes server
def stop_server():
    global server_sock
    if server_sock and server_sock != None:
        server_sock.close()

#gets encryption key (currently just setting to 1 encryption key thats default cuz chatrooms have been buggy for now)
def get_encryption_key():
    return "97u867t564r534w231q2u7e8io0r"
        


#udp listening on multicast group
def listen_udp(prompt, name):
    global encryption_key
    while True:
        try:
            data, address = udp_sock.recvfrom(1024)
        except Exception as e:
            if debug:
                print(f"receive thread has an exception: {e}")
            break

        address = address[0]
        if address and address != self_ip:
            data = pickle.loads(data)
            if debug:
                print("received UDP packet")
            # print(data.key, encryption_key)
            if data.key == encryption_key: 
                #print("received UDP packet matches key")
                data.name = encrypt(data.name, data.key)
                data.port = encrypt(str(data.port), data.key)
                data.type = encrypt(data.type, data.key)

                if debug:
                    print(f"\n[|] client data receievd from {address}: {data}")
                threading.Thread(target=connect, args=(address, data, prompt, name), daemon=True).start()

#sends packet over udp multicast group
def send_udp(prompt, name, packet):
    packet.name = encrypt(packet.name, packet.key)
    packet.port = encrypt(str(packet.port), packet.key)
    packet.type = encrypt(packet.type, packet.key)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    message = pickle.dumps(packet)



    sock.sendto(message, (mcast_group, upd_port))


#thread for receiving data
def receive(sock, nameO, prompt, own_name):
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data:
                break

            data = encrypt(data, encryption_key)

            if data == disconnect_code:
                current_input = readline.get_line_buffer()
                sys.stdout.write("\r\033K")
                sys.stdout.write(f"\n[-] User {nameO} has disconnected \n")

                if "\n" in current_input:
                    current_input = ""

                sys.stdout.write(prompt + current_input)
                sys.stdout.flush()

                readline.redisplay()
                
                CONN_LIST.remove(sock)
                sock.close()
                
                return
                
            if data.startswith(f":{own_name} ") or data.startswith(f":all "):
                data = data.split(" ", 1)
                data = data[1] if len(data) > 0 else ""
                data = f"\033[1m{data}\033[0m"
                command = ['osascript', notify_path, f"Mentioned by {nameO}"]
                subprocess.run(command, capture_output=True, text=True, check=True)


            current_input = readline.get_line_buffer()
            
            if "\n" in current_input:
                current_input = ""
            
            sys.stdout.write("\r\033[K")
            sys.stdout.write(f"{nameO}: {data}\n")
            sys.stdout.write(prompt + current_input)
            sys.stdout.flush()

            readline.redisplay()

        except:
            break

#closes all active connections
def close_sockets():
    global server_sock
    udp_sock.close()
    stop_server()
    for sock in CONN_LIST:
        try:
            CONN_LIST.remove(sock)
            sock.close()
        except:
            pass

#thread for sending data to each connected client
def send(prompt):
    while True:
        try:
            msg = str(input(prompt))
            if msg == "give_info":
                print(f"connections: {CONN_LIST}")
                continue
                
            msg =  encrypt(msg, encryption_key)
        except KeyboardInterrupt:
            for sock in CONN_LIST:
                try:
                    print(disconnect_code)
                    sock.send(encrypt(disconnect_code, encryption_key).encode())
                except:
                    pass
            close_sockets()
            sys.exit()


        for sock in CONN_LIST:
            try:
                sock.send(msg.encode())
            except:
                pass
    

#starts the mesh topo connecting
def connect(address, data, prompt, local_name):

    name = data.name
    port = int(data.port)

    if debug:
        print(f"[|] connect thread ran: connecting to {name} at {address}")

    for active_sock in CONN_LIST:
        try:
            if active_sock.getpeername()[0] == address:
                if debug:
                    sys.stdout.write("\r\033[K")
                    sys.stdout.write(f"[=] Not allowing connection to {name} because there is already an active connection")
                    sys.stdout.flush()
                    readline.redisplay()
                return False
        except:
            sys.stdout.write(f"[?] Not allowing connection to {name} because there is already an active connection")
            pass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(4)
        sock.connect((address, port))
        
        print("receiving server response")
        server_response = sock.recv(1024).decode()
        server_response = encrypt(server_response, encryption_key)
        
        if debug:
            print(server_response)

        if server_response == "ALREADY_CONNECTED":
            return False
        sock.close() 
        
        if server_response.startswith("SHIFT_PORT:"):
            routed_port = int(server_response.split(":")[1])
            
            time.sleep(0.5) 
            
            dedicated_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dedicated_sock.connect((address, routed_port))
            
            nameO = dedicated_sock.recv(1024).decode()
            dedicated_sock.send(local_name.encode())
            
            CONN_LIST.append(dedicated_sock)
            print(f"[+] connected to {nameO} on port {routed_port}")
            sys.stdout.write("\r\033[K")

            sys.stdout.write(prompt)
            sys.stdout.flush()
            readline.redisplay()

            threading.Thread(target=receive, args=(dedicated_sock, nameO, prompt, local_name), daemon=True).start()
            
    except Exception as e:
        print(e)
        print(f"[-] Could not connect or route to {name} at {address}")
        sys.stdout.flush()
        readline.redisplay()

#thread for initialising and maintaining server of host
def server(prompt, name): 
    global incremented_port, server_sock
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    server_sock.bind(("0.0.0.0", port))
    
    server_sock.listen(5)
    sys.stdout.write("\r\033[K")
    sys.stdout.write(f"-Server is listening on {port}-\n")
    #sys.stdout.write("\r\033[K")
    sys.stdout.write(prompt)
    
    sys.stdout.flush()
    readline.redisplay()

    active_conn_code = encrypt(f"ALREADY_CONNECTED", encryption_key)
    

    while True:
        try:
            gateway_conn, address = server_sock.accept()
            
            if debug:
                print("[|] person found")

            if address[0] == self_ip:
                print("[|] person is me \n")
                gateway_conn.send(active_conn_code.encode())
                gateway_conn.close()
                return


            already_connected = False
            for active_sock in CONN_LIST:
                try:
                    if active_sock.getpeername()[0] == address[0]:
                        already_connected = True
                        break
                except:
                    pass


            if already_connected:
                gateway_conn.send(active_conn_code.encode())
                gateway_conn.close()
                continue

            
            given_port = incremented_port
            incremented_port += 1
            
            code = f"SHIFT_PORT:{given_port}"
            code = str(code)
            code = encrypt(code, encryption_key)
            
            if debug: 
                print("server sent response")

            gateway_conn.send(code.encode())
            gateway_conn.close()
            
            def dedicated_listener(target_port):
                try:
                    dedicated_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    dedicated_sock.bind(("0.0.0.0", target_port))
                    dedicated_sock.listen(1)
                    
                    conn, addr = dedicated_sock.accept()

                    
                    conn.send(name.encode())
                    nameO = conn.recv(1024).decode()
                    
                    CONN_LIST.append(conn)
                    print(f"\n[+] connected to {nameO} on port {target_port}")
                    threading.Thread(target=receive, args=(conn, nameO, prompt, name), daemon=True).start()
                    dedicated_sock.close() 
                except:
                    dedicated_sock.close()

            threading.Thread(target=dedicated_listener, args=(given_port,), daemon=True).start()

        except Exception:
            pass


def main():
    global port, incremented_port, debug, encryption_key
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                saved_data = json.load(f)
                port = saved_data.get("port", port)
                incremented_port = saved_data.get("incremented_port", incremented_port)
                debug = saved_data.get("debug", debug)
        except:
            pass

    print("Type 'start' to begin or 'help' for commands")

    while True:
        try:
            user_cmd = input("setup> ").strip()
        except KeyboardInterrupt:
            close_sockets
            sys.exit()
        
        if user_cmd == "start":
            break

        elif user_cmd == 'help':
            print("Commands:")
            print("  config port [value]")
            print("  config Nport [value]")
            print("  config debug [true/false]")
            print("  start\n")

            print("  :[user] to 'ping' them")
            print("    this will also make the text bold")
            print("    you can type text after the ping")
            print("    :all pings everyone")
            
        elif user_cmd.startswith("config port "):
            try:
                port = int(user_cmd.split(" ")[2])
                print(f"[Config Updated] port set to: {port}")
            except:
                print("Invalid port number format.")
                
        elif user_cmd.startswith("config Nport "):
            try:
                incremented_port = int(user_cmd.split(" ")[2])
                print(f"[Config Updated] incremented_port set to: {incremented_port}")
            except:
                print("Invalid Nport number format.")
                
        elif user_cmd.startswith("config debug "):
            val = user_cmd.split(" ")[2].lower()
            if val == "true":
                debug = True
                print("[Config Updated] debug mode enabled.")
            elif val == "false":
                debug = False
                print("[Config Updated] debug mode disabled.")
            else:
                print("Invalid debug value. Choose 'true' or 'false'.")
        else:
            print("Unknown command. Type config parameter or 'start'.")

    config_payload = {
        "port": port,
        "incremented_port": incremented_port,
        "debug": debug
    }
    with open(config_path, "w") as f:
        json.dump(config_payload, f, indent=4)

    try:
        while True:
            name = input("display as: ").strip()

            # no spaces allowed
            if " " in name:
                print("no spaces")
                continue

            # max length 20
            if len(name) > 20:
                print("less than 20 characters")
                continue

            # must not be empty
            if len(name) == 0:
                print("needs characters :(")
                continue

            break

    except KeyboardInterrupt:
        close_sockets()
        sys.exit()

    encryption_key = get_encryption_key()

    prompt = f"> "

    upd_packet = packet(port, name, discovery_code, encryption_key)
    threading.Thread(target=listen_udp, args=(prompt, name), daemon=True).start()
    threading.Thread(target=server, args=(prompt, name), daemon=True).start()
    threading.Thread(target=send_udp, args=(prompt, name, upd_packet), daemon=True).start()



    send(prompt)
    

if __name__ == "__main__":
    main() 
