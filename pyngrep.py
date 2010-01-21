from scapy.all import sniff, TCP

def dumppayload(pkt):
    tcp = pkt[TCP]
    if tcp and tcp.payload:
        print tcp.payload

sniff(iface="lo", filter="port 24242", prn=dumppayload)
