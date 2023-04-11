from time import sleep
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
import subprocess
# Create Mininet network with two hosts h1 and h2
class SingleSwitchTopo(Topo):
    "Single switch connected to n hosts."
    def build(self, n=2):
        switch = self.addSwitch('s1')
        # Python's range(N) generates 0..N-1
        for h in range(n):
            host = self.addHost('h%s' % (h + 1))
            self.addLink(host, switch)

topo = SingleSwitchTopo(n=2)
# invoke mininet and pass it the topology we have created above
net = Mininet(topo)
net.start()
hosts = net.hosts
h1 = hosts[0]
h2 = hosts[1]
h1.setIP('10.0.0.1')
h2.setIP('10.0.0.2')
h1.cmd('cd ../../')
h2.cmd('cd ../../')

# Start the Python program on h1 and h2
h1_cmd = 'python3 examples/example_file_peer.py 4'
h2_cmd = 'python3 examples/example_file_peer.py 5'
h1_proc = h1.popen(h1_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
h2_proc = h2.popen(h2_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

# Send alternating inputs to h1 and h2
inputs = ['scan\n', 'sync\n', 'exit\n']
h1_proc.stdin.write(inputs[0].encode())
h1_proc.stdin.flush()
print(h1_proc.stdout.readline().decode())
h2_proc.stdin.write(inputs[0].encode())
h2_proc.stdin.flush()
print(h2_proc.stdout.readline().decode())
h1_proc.kill()
h2_proc.kill()

h1_proc2 = h1.popen(h1_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
h2_proc2 = h2.popen(h2_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

h1_proc2.stdin.write(inputs[1].encode())
h1_proc2.stdin.flush()
print(h1_proc2.stdout.readline().decode())
h2_proc2.stdin.write(inputs[1].encode())
h2_proc2.stdin.flush()
print(h2_proc2.stdout.readline().decode())
h1_proc2.kill()
h2_proc2.kill()

h1_proc3 = h1.popen(h1_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
h2_proc3 = h2.popen(h2_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

h1_proc3.stdin.write(inputs[2].encode())
h1_proc3.stdin.flush()
print(h1_proc3.stdout.readline().decode())
h2_proc3.stdin.write(inputs[2].encode())
h2_proc3.stdin.flush()
print(h2_proc3.stdout.readline().decode())


# Stop the network and processes
h1_proc.kill()
h2_proc.kill()
net.stop()
