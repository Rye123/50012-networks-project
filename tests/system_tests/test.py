#!/usr/bin/python                                                                            
                                                                                             
from time import sleep
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
import subprocess

'''
This system test is to only replicate the syncing of the file content between two peers (hosts).
We are assuming that the crinfo file for the content is already present in both peers in the shared_peernum/crinfo folder.
We will hardcode or manually pass the crinfo file from the uploading peer to the receiving peer as this would technically be done by the server. 
'''
# to create the mininet network environment for this test
class SingleSwitchTopo(Topo):
    "Single switch connected to n hosts."
    def build(self, n=2):
        switch = self.addSwitch('s1')
        # Python's range(N) generates 0..N-1
        for h in range(n):
            host = self.addHost('h%s' % (h + 1))
            self.addLink(host, switch)



def Test():
    '''
    main function to run all tests
    '''
    "Create and test a simple network"
    # create a topology network with 3 nodes, 2 are peers, 1 is the server
    topo = SingleSwitchTopo(n=3)
    # invoke mininet and pass it the topology we have created above
    net = Mininet(topo)
    net.start()
    hosts = net.hosts
    print( "Starting peer file test...")
    h1 = hosts[0]
    h2 = hosts[1]
    h1.setIP('10.0.0.1')
    h2.setIP('10.0.0.2')
    h1.cmd('cd ../../')
    h2.cmd('cd ../../')
    out1 = h1.cmd(f'echo "scan" && echo "sync" | (python3 tests/client_tests/peer_test.py 4 > test.txt) & ')
    out2 = h2.cmd(f'echo "scan" && echo "sync" | (python3 tests/client_tests/peer_test.py 5 > test2.txt) &')
    # h1.sendCmd(f'echo "scan" && echo "sync" | (python3 examples/example_file_peer.py 4 > test.txt) & ')
    # h2.sendCmd(f'echo "scan" && echo "sync" | (python3 examples/example_file_peer.py 5 > test2.txt) &')
    # out1 = h1.waitOutput()
    # out2 = h2.waitOutput()
    print(out1.strip())
    print(out2.strip())
    CLI(net)
    net.stop()

if __name__ == '__main__':
    # Tell mininet to print useful information
    setLogLevel('info')
    Test()